"""Verify the published file manifest against checkout bytes (LF-normalized)."""
import hashlib
import json
from pathlib import Path


def verify(root):
    manifest=json.loads((root/'PUBLICATION_MANIFEST.json').read_text(encoding='utf-8'))
    errors=[]
    seen=set()
    for row in manifest['files']:
        relative=Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:
            errors.append('unsafe manifest path'); continue
        if row['path'] in seen:
            errors.append('duplicate manifest path')
        seen.add(row['path'])
        path=root/relative
        if not path.is_file():
            errors.append(row['path']+': missing'); continue
        raw=path.read_bytes()
        if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:
            errors.append(row['path']+': size/hash mismatch')
    if manifest['file_count']!=len(seen): errors.append('file count mismatch')
    return errors


if __name__=='__main__':
    errors=verify(Path(__file__).resolve().parent)
    print(json.dumps(dict(valid=not errors,errors=errors)))
    raise SystemExit(bool(errors))
