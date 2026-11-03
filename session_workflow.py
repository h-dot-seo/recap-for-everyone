"""Explicit export adapters and reversible local title organization (no network)."""
import argparse
import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from local_parser import parse_artifact
from recap import ingest, readonly


def normalize(path, kind):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = []
    if kind == 'local':
        parsed = parse_artifact(path, path.name)
        for m in parsed.messages:
            rows.append(dict(conversation_id=m.session_id, message_id=m.message_key,
                             role=m.role, timestamp=m.timestamp_utc or 'unknown', text=m.text,
                             origin_locator=f'line:{m.line_number}'))
    elif kind == 'web':
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, list):
            raise ValueError('web export must be an array of conversations with mapping nodes')
        for conv in data:
            cid = conv.get('id') or conv.get('conversation_id')
            if not isinstance(cid, str) or not cid:
                raise ValueError('conversation ID required')
            for node_id, node in conv['mapping'].items():
                m = node.get('message')
                if not m:
                    continue
                parts = m.get('content', {}).get('parts', [])
                text = '\n'.join(p for p in parts if isinstance(p, str))
                if not text.strip():
                    continue
                rows.append(dict(conversation_id=cid, message_id=node_id,
                                 role=m['author']['role'], timestamp=str(m.get('create_time') or 'unknown'),
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
        result = ingest(db, source, normalized)
    with closing(sqlite3.connect(db)) as c, c:
        c.execute('CREATE TABLE IF NOT EXISTS export_provenance (source TEXT, conversation TEXT, message TEXT, original_hash TEXT, locator TEXT, parent TEXT, PRIMARY KEY(source,conversation,message,original_hash))')
        c.executemany('INSERT OR IGNORE INTO export_provenance VALUES(?,?,?,?,?,?)',
                      [(source, r['conversation_id'], r['message_id'], r['origin_sha256'], r['origin_locator'], r.get('parent_id')) for r in rows])
    return result


def titles(db, source, conversation, title=None):
    c = readonly(db) if title is None else sqlite3.connect(db)
    try:
        messages = c.execute('SELECT role,text,title FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk', (source, conversation)).fetchall()
        if not messages:
            raise ValueError('unknown conversation')
        suggestion = next((' '.join(m[1].split())[:80] for m in messages if m[0] == 'user'), 'Untitled conversation')
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='title_history'").fetchone()
        history = c.execute('SELECT title FROM title_history WHERE source=? AND conversation=? ORDER BY id', (source, conversation)).fetchall() if exists else []
        current = history[-1][0] if history else messages[0][2]
        if title is not None:
            if not title.strip() or len(title) > 200:
                raise ValueError('title must contain 1..200 characters')
            with c:
                c.execute('CREATE TABLE IF NOT EXISTS title_history (id INTEGER PRIMARY KEY, source TEXT, conversation TEXT, previous TEXT, title TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP)')
                c.execute('INSERT INTO title_history(source,conversation,previous,title) VALUES(?,?,?,?)', (source, conversation, current, title))
            current = title
        return dict(display_title=current, suggested_title=suggestion, original_title=messages[0][2], prior_titles=[m[0] for m in history], scope='local display only')
    finally:
        c.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True)
    sub = p.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import'); imp.add_argument('path'); imp.add_argument('--format', choices=['web', 'local'], required=True); imp.add_argument('--source', required=True)
    t = sub.add_parser('title'); t.add_argument('--source', required=True); t.add_argument('--conversation', required=True); t.add_argument('--set')
    a = p.parse_args()
    try:
        result = import_export(a.db, a.source, a.path, a.format) if a.command == 'import' else titles(a.db, a.source, a.conversation, a.set)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as e:
        p.exit(1, str(e) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
