"""Verify the published file manifest against checkout bytes (LF-normalized)."""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from recaplib.strict_json import loads


def _portable_component(part):
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'}
    stem = part.split('.')[0].upper()
    return (not part.endswith(('.', ' ')) and
            not any(ord(ch) < 32 or ch in '<>:"|?*' for ch in part) and
            stem not in reserved and not re.fullmatch(r'(COM|LPT)[1-9¹²³]', stem))


def verify(root):
    root = Path(root)
    if (root/'PUBLICATION_MANIFEST.json').is_symlink():
        return ['manifest symlink not allowed']
    try:
        manifest=loads((root/'PUBLICATION_MANIFEST.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return ['manifest is missing, unreadable or invalid JSON']
    if (not isinstance(manifest, dict) or not isinstance(manifest.get('files'), list) or
            type(manifest.get('file_count')) is not int):
        return ['invalid manifest structure']
    errors=[]
    seen=set()
    casefolded=set()
    for row in manifest['files']:
        if not isinstance(row, dict) or not isinstance(row.get('path'), str):
            errors.append('invalid manifest entry'); continue
        name = row['path']
        relative=PurePosixPath(name)
        if (not name or not relative.parts or relative.is_absolute() or '..' in relative.parts or
                name != relative.as_posix() or '\\' in name or ':' in name or
                not all(_portable_component(part) for part in relative.parts) or
                '.git' in relative.parts or '__pycache__' in relative.parts or
                name == 'PUBLICATION_MANIFEST.json'):
            errors.append('unsafe manifest path'); continue
        if name.casefold() in casefolded:
            errors.append('duplicate manifest path')
        seen.add(name)
        casefolded.add(name.casefold())
        if (type(row.get('bytes')) is not int or row['bytes'] < 0 or
                not isinstance(row.get('sha256'), str) or
                not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
            errors.append(name+': invalid size/hash metadata'); continue
        path=root/relative
        if any((root/Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts)+1)):
            errors.append(name+': symlink not allowed'); continue
        if not path.is_file():
            errors.append(name+': missing'); continue
        try:
            raw=path.read_bytes()
        except OSError:
            errors.append(name+': unreadable'); continue
        if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:
            errors.append(name+': size/hash mismatch')
    if manifest['file_count']!=len(seen): errors.append('file count mismatch')
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if '.git' in relative.parts:
            continue
        if path.is_symlink():
            errors.append(relative.as_posix()+': symlink not allowed'); continue
        if not path.is_file():
            continue
        if '__pycache__' in relative.parts and path.suffix == '.pyc':
            continue
        name = relative.as_posix()
        if name != 'PUBLICATION_MANIFEST.json' and name not in seen:
            errors.append(name+': unexpected file outside manifest')
    return errors


if __name__=='__main__':
    errors=verify(Path(__file__).resolve().parent)
    print(json.dumps(dict(valid=not errors,errors=errors)))
    raise SystemExit(bool(errors))
