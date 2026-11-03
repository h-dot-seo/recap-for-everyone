#!/usr/bin/env python3
"""Local-only normalized conversation ingestion and read-only search."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from strict_json import loads

SCHEMA = '''
CREATE TABLE IF NOT EXISTS artifacts (
 source_id TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
 record_count INTEGER NOT NULL, PRIMARY KEY(source_id, sha256));
CREATE TABLE IF NOT EXISTS messages (
 message_pk INTEGER PRIMARY KEY, source_id TEXT NOT NULL,
 conversation_id TEXT NOT NULL, message_id TEXT NOT NULL, role TEXT NOT NULL,
 timestamp TEXT NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL,
 source_sha256 TEXT NOT NULL, source_line INTEGER NOT NULL,
 UNIQUE(source_id, conversation_id, message_id),
 FOREIGN KEY(source_id, source_sha256) REFERENCES artifacts(source_id,sha256));
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
 text, content='messages', content_rowid='message_pk');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
 INSERT INTO messages_fts(rowid,text) VALUES(new.message_pk,new.text); END;
'''


def ingest(db, source, path, provenance=None):
    if not source or not source.strip():
        raise ValueError('source must not be empty')
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    records = []
    for line_no, line in enumerate(raw.decode('utf-8').split('\n'), 1):
        if not line.strip():
            continue
        try:
            row = loads(line)
        except ValueError as error:
            raise ValueError(f'invalid JSON record at line {line_no}') from error
        required = ('conversation_id', 'message_id', 'role', 'timestamp', 'text')
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k] for k in required):
            raise ValueError(f'invalid record at line {line_no}')
        if row['role'] not in ('user', 'assistant', 'system', 'tool'):
            raise ValueError(f'unsupported role at line {line_no}')
        title = row.get('title', '')
        if not isinstance(title, str):
            raise ValueError(f'invalid title at line {line_no}')
        records.append((row, title, line_no))
    conn = sqlite3.connect(db)
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript(SCHEMA)
        inserted = 0
        with conn:
            if provenance is not None:
                conn.execute('CREATE TABLE IF NOT EXISTS export_provenance (source TEXT, conversation TEXT, message TEXT, original_hash TEXT, locator TEXT, parent TEXT, PRIMARY KEY(source,conversation,message,original_hash))')
            conn.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?)',
                         (source, digest, len(raw), len(records)))
            for row, title, line_no in records:
                key = (source, row['conversation_id'], row['message_id'])
                values = (row['role'], row['timestamp'], title, row['text'])
                existing = conn.execute('SELECT role,timestamp,title,text FROM messages '
                                        'WHERE source_id=? AND conversation_id=? AND message_id=?', key).fetchone()
                if existing is not None:
                    if existing != values:
                        raise ValueError(f'conflicting message identity at line {line_no}')
                    continue
                conn.execute('INSERT INTO messages(source_id,conversation_id,message_id,role,timestamp,title,text,source_sha256,source_line) '
                             'VALUES(?,?,?,?,?,?,?,?,?)', (*key, *values, digest, line_no))
                inserted += 1
            if provenance is not None:
                conn.executemany('INSERT OR IGNORE INTO export_provenance VALUES(?,?,?,?,?,?)',
                    [(source, r['conversation_id'], r['message_id'], r['origin_sha256'], r['origin_locator'], r.get('parent_id')) for r in provenance])
        return {'source_sha256': digest, 'records': len(records), 'inserted': inserted}
    finally:
        conn.close()


def readonly(db):
    conn = sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    return conn


def search(db, query, limit=20):
    if not query.strip() or not 1 <= limit <= 1000:
        raise ValueError('query required; limit must be 1..1000')
    match = ' AND '.join('"' + term.replace('"', '""') + '"' for term in query.split())
    conn = readonly(db)
    try:
        return [dict(r) for r in conn.execute('SELECT m.* FROM messages_fts f JOIN messages m '
                    'ON m.message_pk=f.rowid WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts),m.message_pk LIMIT ?',
                    (match, limit))]
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', required=True)
    sub = p.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('ingest'); imp.add_argument('input'); imp.add_argument('--source', required=True)
    find = sub.add_parser('search'); find.add_argument('query'); find.add_argument('--limit', type=int, default=20)
    sub.add_parser('stats')
    args = p.parse_args()
    try:
        if args.command == 'ingest':
            result = ingest(args.db, args.source, args.input)
        elif args.command == 'search':
            result = search(args.db, args.query, args.limit)
        else:
            c = readonly(args.db)
            try:
                result = {'messages': c.execute('SELECT count(*) FROM messages').fetchone()[0],
                          'artifacts': c.execute('SELECT count(*) FROM artifacts').fetchone()[0]}
            finally:
                c.close()
    except (OSError, ValueError, sqlite3.Error) as exc:
        p.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
