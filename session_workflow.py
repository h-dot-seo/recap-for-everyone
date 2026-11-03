"""Explicit export adapters and reversible local title organization (no network)."""
import argparse
import hashlib
import json
import math
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from local_parser import parse_artifact
from recap import ingest, readonly


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('web export contains a duplicate JSON object key')
        result[key] = value
    return result


def _validate_mapping(mapping):
    for node_id, node in mapping.items():
        if not isinstance(node_id, str) or not node_id or not isinstance(node, dict):
            raise ValueError('mapping nodes require nonempty IDs and object values')
        parent = node.get('parent')
        if parent is not None and (not isinstance(parent, str) or parent not in mapping):
            raise ValueError('mapping parent must reference an existing node')
    # Iterative parent walks avoid recursion limits on long, valid conversations.
    complete = set()
    for node_id in mapping:
        path = set()
        current = node_id
        while current is not None and current not in complete:
            if current in path:
                raise ValueError('mapping parent graph must not contain cycles')
            path.add(current)
            current = mapping[current].get('parent')
        complete.update(path)


def normalize(path, kind):
    path = Path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = []
    if kind == 'local':
        # Parse the same byte snapshot that was hashed, even if the source changes.
        with tempfile.TemporaryDirectory() as tmp:
            frozen = Path(tmp) / 'session.jsonl'
            frozen.write_bytes(raw)
            parsed = parse_artifact(frozen, path.name)
        for m in parsed.messages:
            rows.append(dict(conversation_id=m.session_id, message_id=m.message_key,
                             role=m.role, timestamp=m.timestamp_utc or 'unknown', text=m.text,
                             origin_locator=f'line:{m.line_number}'))
    elif kind == 'web':
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
        if not isinstance(data, list):
            raise ValueError('web export must be an array of conversations with mapping nodes')
        for conv in data:
            if not isinstance(conv, dict) or not isinstance(conv.get('mapping'), dict):
                raise ValueError('conversation must contain a mapping object')
            cid = conv.get('id') or conv.get('conversation_id')
            if not isinstance(cid, str) or not cid:
                raise ValueError('conversation ID required')
            _validate_mapping(conv['mapping'])
            for node_id, node in conv['mapping'].items():
                m = node.get('message')
                if m is None:
                    continue
                if not isinstance(m, dict) or not isinstance(m.get('content'), dict):
                    raise ValueError('message content must be an object')
                author = m.get('author')
                if not isinstance(author, dict) or author.get('role') not in ('user', 'assistant', 'system', 'tool'):
                    raise ValueError('message author must contain a supported role')
                timestamp = m.get('create_time')
                if timestamp is not None and (timestamp == '' or isinstance(timestamp, bool) or
                        not isinstance(timestamp, (str, int, float)) or
                        isinstance(timestamp, float) and not math.isfinite(timestamp)):
                    raise ValueError('message create_time must be text or a finite number')
                parts = m.get('content', {}).get('parts', [])
                if not isinstance(parts, list):
                    raise ValueError('message content parts must be an array')
                text = '\n'.join(p for p in parts if isinstance(p, str))
                if not text.strip():
                    continue
                rows.append(dict(conversation_id=cid, message_id=node_id,
                                 role=author['role'], timestamp='unknown' if timestamp is None else str(timestamp),
                                 text=text, title=conv.get('title') or '',
                                 parent_id=node.get('parent'), origin_locator=f'mapping:{node_id}'))
    else:
        raise ValueError('unsupported format')
    for row in rows:
        row['origin_sha256'] = digest
    return rows


def import_export(db, source, path, kind):
    rows = normalize(path, kind)
    # Keep original hash/locator/branch metadata in a companion provenance table.
    with tempfile.TemporaryDirectory() as tmp:
        normalized = Path(tmp) / 'normalized.jsonl'
        normalized.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
        result = ingest(db, source, normalized, provenance=rows)
    return result


def titles(db, source, conversation, title=None, expected_revision=None, expected_content_sha256=None):
    c = readonly(db) if title is None else sqlite3.connect(db)
    try:
        if title is not None:
            c.execute('BEGIN IMMEDIATE')
        if expected_content_sha256 is not None:
            content = [dict(zip(('message_id','role','text'), r)) for r in c.execute(
                'SELECT message_id,role,text FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk', (source, conversation))]
            digest = hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if digest != expected_content_sha256:
                raise ValueError('conversation changed after proposal generation')
        messages = c.execute('SELECT role,text,title FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk', (source, conversation)).fetchall()
        if not messages:
            raise ValueError('unknown conversation')
        suggestion = next((' '.join(m[1].split())[:80] for m in messages if m[0] == 'user'), 'Untitled conversation')
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='title_history'").fetchone()
        history = c.execute('SELECT title,id FROM title_history WHERE source=? AND conversation=? ORDER BY id', (source, conversation)).fetchall() if exists else []
        revision = history[-1][1] if history else 0
        current = history[-1][0] if history else messages[0][2]
        if title is not None:
            if expected_revision is not None and expected_revision != revision:
                raise ValueError('stale title preview; preview again before applying')
            if not title.strip() or len(title) > 200:
                raise ValueError('title must contain 1..200 characters')
            with c:
                c.execute('CREATE TABLE IF NOT EXISTS title_history (id INTEGER PRIMARY KEY, source TEXT, conversation TEXT, previous TEXT, title TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP)')
                revision = c.execute('INSERT INTO title_history(source,conversation,previous,title) VALUES(?,?,?,?)', (source, conversation, current, title)).lastrowid
            current = title
        return dict(display_title=current, suggested_title=suggestion, revision=revision, original_title=messages[0][2], prior_titles=[m[0] for m in history], scope='local display only')
    finally:
        c.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True)
    sub = p.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import'); imp.add_argument('path'); imp.add_argument('--format', choices=['web', 'local'], required=True); imp.add_argument('--source', required=True)
    t = sub.add_parser('title'); t.add_argument('--source', required=True); t.add_argument('--conversation', required=True); t.add_argument('--set')
    t.add_argument('--expected-revision', type=int)
    a = p.parse_args()
    try:
        if a.command == 'title' and a.set is not None and a.expected_revision is None:
            raise ValueError('--set requires --expected-revision from a title preview')
        result = import_export(a.db, a.source, a.path, a.format) if a.command == 'import' else titles(a.db, a.source, a.conversation, a.set, a.expected_revision)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as e:
        p.exit(1, str(e) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
