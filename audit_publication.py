#!/usr/bin/env python3
"""Check a deliberately selected public file set; not an anonymizer or legal audit."""
import json
import re
from pathlib import Path

DENIED_SUFFIXES = {'.sqlite', '.db', '.pdf', '.zip', '.pem', '.key', '.log', '.p12', '.pfx'}
DENIED_DIRS = {'private', 'corpus', 'profiles', 'credentials', 'archives'}
PATTERNS = {
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'github-token': re.compile(r'gh[pousr]_' + r'[A-Za-z0-9]{30,}'),
    'cloud-access-key': re.compile(r'AKIA' + r'[A-Z0-9]{16}'),
    'bearer-token': re.compile(r'Bearer\s+' + r'[A-Za-z0-9._~-]{24,}'),
    'email-address': re.compile(r'[A-Za-z0-9._%+-]+@' + r'[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
}


def audit(root):
    errors = []
    checked = 0
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if any(p in {'.git', '__pycache__'} for p in rel.parts):
            continue
        if path.is_symlink():
            errors.append(f'{rel}: symlink not allowed'); continue
        if not path.is_file():
            continue
        checked += 1
        if path.suffix.lower() in DENIED_SUFFIXES or any(p.lower() in DENIED_DIRS for p in rel.parts) or path.name.startswith('.env'):
            errors.append(f'{rel}: prohibited public asset')
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeError, OSError):
            errors.append(f'{rel}: non-text/unreadable file'); continue
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                errors.append(f'{rel}: possible {name}')
    return {'checked_files': checked, 'pass': not errors, 'errors': errors,
            'scope': 'limited file/type/pattern checks; manual review still required'}


if __name__ == '__main__':
    result = audit(Path(__file__).resolve().parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(int(not result['pass']))
