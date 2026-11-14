#!/usr/bin/env python3
"""Plan a public file inventory; publish only a new outside-tree candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from audit_publication import audit, DENIED_DIRS, DENIED_SUFFIXES, PATTERNS
from recaplib.recovery import _publish_new_file, _reject_existing
from recaplib.strict_json import loads
from verify_manifest import verify, _portable_component

MANIFEST = 'PUBLICATION_MANIFEST.json'
BOUNDARY = ('Read-only public-tree inventory plan, not anonymization, legal review, release authorization or a signature. Existing top-level metadata is preserved except explicitly supplied release/date. Omitted release/date retain existing values; no clock is read. Files must already use LF bytes. Concurrent hostile namespace changes are not defended against; this is not an atomic filesystem snapshot. Manual review remains required. Writing creates only a new candidate outside the tree; it never replaces the publication manifest.')


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe_name(name):
    rel = PurePosixPath(name)
    return (bool(name) and bool(rel.parts) and not rel.is_absolute() and '..' not in rel.parts and
            name == rel.as_posix() and '\\' not in name and ':' not in name and
            all(_portable_component(part) for part in rel.parts) and
            '.git' not in rel.parts and '__pycache__' not in rel.parts)


def _scan(root):
    """Reject special entries before audit can open them; never follow symlinks."""
    rows = []
    folded = set()
    def walk(directory):
        with os.scandir(directory) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
        for entry in ordered:
            path = Path(entry.path)
            relative = path.relative_to(root)
            name = relative.as_posix()
            mode = entry.stat(follow_symlinks=False).st_mode
            if entry.name == '.git' and stat.S_ISDIR(mode):
                continue
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError('symlink or special public-tree entry not allowed')
            if '__pycache__' in relative.parts:
                if stat.S_ISDIR(mode):
                    walk(path)
                    continue
                if path.suffix == '.pyc':
                    continue
                raise ValueError('only generated .pyc files may be excluded under __pycache__')
            if not _safe_name(name) or name.casefold() in folded:
                raise ValueError('unsafe, nonportable or case-colliding public-tree path')
            folded.add(name.casefold())
            if any(part.lower() in DENIED_DIRS for part in relative.parts) or path.name.startswith('.env'):
                raise ValueError('prohibited public-tree asset')
            if stat.S_ISDIR(mode):
                walk(path)
                continue
            if path.suffix.lower() in DENIED_SUFFIXES:
                raise ValueError('prohibited public-tree asset')
            raw = path.read_bytes()
            if b'\r' in raw:
                raise ValueError('CR bytes are not allowed; normalize files explicitly before planning')
            try:
                text = raw.decode('utf-8')
            except UnicodeError:
                raise ValueError('public-tree file must be UTF-8 text') from None
            if any(pattern.search(text) for pattern in PATTERNS.values()):
                raise ValueError('public-tree file failed publication pattern checks')
            if name != MANIFEST:
                rows.append(dict(path=name, bytes=len(raw), sha256=_sha(raw)))
    walk(root)
    return sorted(rows, key=lambda row: row['path'])


def _prepare(root, release=None, date=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('root must be an existing directory')
    for value in (release, date):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError('release and date must be nonempty supplied text')
    rows = _scan(root)
    raw = (root / MANIFEST).read_bytes()
    base = loads(raw.decode('utf-8'))
    if (not isinstance(base, dict) or not isinstance(base.get('files'), list) or
            type(base.get('file_count')) is not int or base['file_count'] != len(base['files'])):
        raise ValueError('invalid base manifest structure')
    previous = {}
    folded = set()
    for row in base['files']:
        if (not isinstance(row, dict) or set(row) != {'path', 'bytes', 'sha256'} or
                not isinstance(row['path'], str) or not _safe_name(row['path']) or row['path'] == MANIFEST or
                row['path'].casefold() in folded or type(row['bytes']) is not int or row['bytes'] < 0 or
                not isinstance(row['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
            raise ValueError('invalid base manifest file entry')
        previous[row['path']] = row
        folded.add(row['path'].casefold())
    candidate = dict(base, file_count=len(rows), files=rows)
    if release is not None:
        candidate['release'] = release
    if date is not None:
        candidate['date'] = date
    if not audit(root)['pass']:
        raise ValueError('publication audit failed')
    if verify(root, manifest=candidate):
        raise ValueError('candidate failed existing manifest verification')
    encoded = _encode(candidate)
    if any(pattern.search(encoded.decode('utf-8')) for pattern in PATTERNS.values()):
        raise ValueError('candidate metadata failed publication pattern checks')
    current = {row['path']: row for row in rows}
    plan = dict(schema='recap.manifest-plan.v1', base_manifest_sha256=_sha(raw),
                candidate_sha256=_sha(encoded), candidate_bytes=len(encoded),
                added=sorted(current.keys() - previous.keys()), removed=sorted(previous.keys() - current.keys()),
                changed=sorted(name for name in current.keys() & previous.keys() if current[name] != previous[name]),
                file_count=len(rows), boundary=BOUNDARY)
    for name in ('added', 'removed', 'changed'):
        plan[name + '_count'] = len(plan[name])
    plan['plan_sha256'] = _sha(_encode(plan))
    return plan, encoded


def plan_manifest(root, release=None, date=None):
    """Return deterministic JSON-ready plan; no files are created or changed."""
    return _prepare(root, release, date)[0]


def build_manifest(root, output, expected_plan_sha256, release=None, date=None):
    """Recompute the plan and exclusively publish a matching outside-tree candidate."""
    root, output = Path(root).resolve(), Path(output)
    if not isinstance(expected_plan_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_plan_sha256):
        raise ValueError('expected plan SHA-256 must be lowercase hexadecimal')
    if output.resolve() == root or root in output.resolve().parents:
        raise ValueError('candidate output must be outside the source tree')
    _reject_existing(output)
    plan, raw = _prepare(root, release, date)
    if plan['plan_sha256'] != expected_plan_sha256:
        raise ValueError('stale or mismatched manifest plan; create and review a new plan')
    # Re-read immediately before publishing. This detects ordinary concurrent edits,
    # not hostile namespace races after the last read (see the explicit boundary).
    again, raw = _prepare(root, release, date)
    if again != plan:
        raise ValueError('source tree changed during planning; create and review a new plan')
    publication = _publish_new_file(output, raw, '.recap-manifest-')
    return dict(schema='recap.manifest-build.v1', status='WRITTEN', plan_sha256=plan['plan_sha256'],
                candidate_sha256=_sha(raw), candidate_bytes=len(raw), boundary=BOUNDARY, **publication)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--release', help='supplied release text; default retains existing metadata')
    parser.add_argument('--date', help='supplied date text; default retains existing metadata (no clock)')
    parser.add_argument('--write', type=Path, metavar='NEW_PATH')
    parser.add_argument('--expected-plan-sha256', metavar='HEX')
    args = parser.parse_args(argv)
    if bool(args.write) != bool(args.expected_plan_sha256):
        parser.error('--write and --expected-plan-sha256 must be supplied together')
    try:
        result = (build_manifest(args.root, args.write, args.expected_plan_sha256, args.release, args.date)
                  if args.write else plan_manifest(args.root, args.release, args.date))
    except (OSError, ValueError, TypeError, RecursionError):
        print(json.dumps(dict(status='ERROR', error='manifest planning or publication failed; check tree, output and expected plan')))
        return 1
    print(_encode(result).decode('utf-8'), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
