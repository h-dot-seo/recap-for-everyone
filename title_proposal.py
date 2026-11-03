"""Validate externally supplied title proposals; this module calls no model."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from recap import readonly
from session_workflow import titles
from strict_json import loads
from title_rules import validate_title


def content_fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def snapshot(db, source, conversation):
    c = readonly(db)
    try:
        rows = [dict(r) for r in c.execute(
            'SELECT message_id,role,text FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk',
            (source, conversation))]
    finally:
        c.close()
    if not rows:
        raise ValueError('unknown conversation')
    digest = content_fingerprint(rows)
    return rows, digest


def preview(db, proposal):
    source, conversation = proposal['source'], proposal['conversation']
    rows, digest = snapshot(db, source, conversation)
    if proposal.get('content_sha256') != digest:
        raise ValueError('proposal refers to a different conversation snapshot')
    title = proposal['title']
    validate_title(title)
    ids = proposal.get('evidence_message_ids')
    users = {r['message_id'] for r in rows if r['role'] == 'user'}
    if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in users for i in ids):
        raise ValueError('title evidence must reference user messages in this conversation')
    if proposal.get('provider') not in ('operator', 'external-adapter', 'synthetic-mock', 'local-extractive'):
        raise ValueError('explicit proposal provider required')
    current = titles(db, source, conversation)
    return dict(proposal=proposal, previous_title=current['display_title'], expected_revision=current['revision'],
                semantic_validation='NOT_PERFORMED', remote_mutation=False)


def apply_preview(db, reviewed):
    if not isinstance(reviewed, dict) or type(reviewed.get('expected_revision')) is not int or reviewed['expected_revision'] < 0:
        raise ValueError('reviewed preview requires a nonnegative integer expected_revision')
    proposal = reviewed['proposal']
    # Revalidate the content fingerprint immediately before writing the title.
    preview(db, proposal)
    return titles(db, proposal['source'], proposal['conversation'], proposal['title'], reviewed['expected_revision'], proposal['content_sha256'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True)
    s = p.add_subparsers(dest='command', required=True)
    export = s.add_parser('snapshot'); export.add_argument('--source', required=True); export.add_argument('--conversation', required=True)
    for name in ('preview', 'apply'):
        s.add_parser(name).add_argument('input', type=Path)
    a = p.parse_args()
    try:
        if a.command == 'snapshot':
            rows, digest = snapshot(a.db, a.source, a.conversation)
            result = dict(source=a.source, conversation=a.conversation, content_sha256=digest, messages=rows,
                          warning='Private local content; no external transmission is performed')
        else:
            value = loads(a.input.read_text(encoding='utf-8'))
            result = preview(a.db, value) if a.command == 'preview' else apply_preview(a.db, value)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as e:
        p.exit(1, str(e) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
