"""List explicit export identities and titles without importing message bodies."""
import argparse
import json
from collections import Counter
from pathlib import Path

from session_workflow import _normalize_bytes, _read_export_bytes
from strict_json import loads


def list_export(path, kind, limit=50, offset=0, expected_export_sha256=None):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer in 1..1000')
    if type(offset) is not int or not 0 <= offset <= 2**63 - 1:
        raise ValueError('offset must be an integer in 0..9223372036854775807')
    if kind not in ('web', 'local', 'local-codex'):
        raise ValueError('unsupported format')
    path = Path(path)
    raw = _read_export_bytes(path, expected_export_sha256)
    rows, coverage = _normalize_bytes(raw, path.name, kind, include_report=True)
    if expected_export_sha256 is not None:
        coverage['expected_export_sha256'] = expected_export_sha256
    items = {}

    def register(identity, title=None):
        item = items.setdefault(identity, dict(conversation=identity, original_titles=[],
            metadata_records=0, extracted_messages=0, role_counts={}))
        item['metadata_records'] += 1
        if title is not None and title not in item['original_titles']:
            item['original_titles'].append(title)

    text = raw.decode('utf-8')
    if kind == 'web':
        for record in loads(text):
            register(record.get('id') or record.get('conversation_id'), record.get('title') or '')
    else:
        # Mirror local_parser's universal newlines, not Unicode splitlines.
        for line in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
            if not line.strip():
                continue
            record = loads(line)
            if record.get('type') == 'session_meta':
                payload = record['payload']
                register(payload.get('id') or payload.get('session_id'))
    roles = {}
    for row in rows:
        identity = row['conversation_id']
        roles.setdefault(identity, Counter())[row['role']] += 1
    for identity, item in items.items():
        item['role_counts'] = dict(sorted(roles.get(identity, {}).items()))
        item['extracted_messages'] = sum(item['role_counts'].values())
        item['selection_blocker'] = ('AMBIGUOUS_WEB_ID' if kind == 'web' and item['metadata_records'] > 1
                                     else 'NO_EXTRACTED_TEXT' if not item['extracted_messages'] else None)
        item['selection_supported'] = item['selection_blocker'] is None
    identities = sorted(items)
    selected = [items[key] for key in identities[offset:offset + limit]]
    next_offset = offset + len(selected)
    return dict(format=kind, original_sha256=coverage['original_sha256'],
        original_bytes=len(raw), total_conversations=len(items), conversations=selected,
        selectable_conversations=sum(item['selection_supported'] for item in items.values()),
        limit=limit, offset=offset, next_offset=next_offset if next_offset < len(items) else None,
        order='conversation ID, Unicode code-point order', contains_message_text=False,
        coverage=coverage,
        scope='read-only export inventory; full file parsed; no database access or effective-history reconstruction',
        warning='PRIVATE METADATA: titles and IDs may be sensitive. No message body fields are included; titles are not redacted or verified. Selection support describes parser output, not import authorization or conflict-free database insertion.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('--format', choices=['web', 'local', 'local-codex'], required=True)
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--expected-export-sha256', help='require the same original whole-file hash as an earlier page')
    args = parser.parse_args()
    try:
        result = list_export(args.input, args.format, args.limit, args.offset, args.expected_export_sha256)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
