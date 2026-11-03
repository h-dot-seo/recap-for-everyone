#!/usr/bin/env python3
"""Local-only archive import, inspection, search and checked title workflows."""
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
            conn.execute('BEGIN IMMEDIATE')
            if provenance is not None:
                conn.execute('CREATE TABLE IF NOT EXISTS export_provenance (source TEXT, conversation TEXT, message TEXT, original_hash TEXT, locator TEXT, parent TEXT, PRIMARY KEY(source,conversation,message,original_hash))')
                occurrence_table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_occurrences'").fetchone()
                conn.execute('CREATE TABLE IF NOT EXISTS export_occurrences (source TEXT, conversation TEXT, message TEXT, original_hash TEXT, locator TEXT, parent TEXT, PRIMARY KEY(source,conversation,message,original_hash,locator))')
                if occurrence_table is None:
                    # Additive upgrade: preserve the legacy table and its schema.
                    conn.execute('INSERT OR IGNORE INTO export_occurrences SELECT source,conversation,message,original_hash,locator,parent FROM export_provenance')
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
                occurrences = [(source, r['conversation_id'], r['message_id'], r['origin_sha256'], r['origin_locator'], r.get('parent_id')) for r in provenance]
                conn.executemany('INSERT OR IGNORE INTO export_provenance VALUES(?,?,?,?,?,?)',
                                 occurrences)
                conn.executemany('INSERT OR IGNORE INTO export_occurrences VALUES(?,?,?,?,?,?)', occurrences)
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
    p.add_argument('--db')
    sub = p.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('ingest'); imp.add_argument('input'); imp.add_argument('--source', required=True)
    find = sub.add_parser('search'); find.add_argument('query'); find.add_argument('--limit', type=int, default=20)
    sub.add_parser('stats')
    check = sub.add_parser('inspect', help='inspect export coverage without a database')
    check.add_argument('input'); check.add_argument('--format', choices=['web', 'local'], required=True)
    branch = sub.add_parser('web-branch', help='read one path from an explicit web export without a database')
    branch.add_argument('input'); branch.add_argument('--conversation', required=True); branch.add_argument('--node')
    branch_title = sub.add_parser('suggest-branch-title', help='suggest a local title from an archived export branch')
    branch_title.add_argument('input'); branch_title.add_argument('--source', required=True)
    branch_title.add_argument('--conversation', required=True); branch_title.add_argument('--node')
    plan = sub.add_parser('export-title-plan', help='export metadata for a manual title change')
    plan.add_argument('input'); plan.add_argument('--format', choices=['web', 'local'], required=True)
    plan.add_argument('--source', required=True); plan.add_argument('--conversation', required=True)
    check_plan = sub.add_parser('check-title-plan', help='recheck a manual title plan without executing it')
    check_plan.add_argument('input'); check_plan.add_argument('plan')
    export = sub.add_parser('import', help='import an explicitly selected web/local export')
    export.add_argument('input'); export.add_argument('--format', choices=['web', 'local'], required=True); export.add_argument('--source', required=True)
    listing = sub.add_parser('list', help='list conversations and current display titles')
    listing.add_argument('--source'); listing.add_argument('--limit', type=int, default=50); listing.add_argument('--offset', type=int, default=0)
    find = sub.add_parser('find', help='search current titles and conversation text')
    find.add_argument('query'); find.add_argument('--source'); find.add_argument('--limit', type=int, default=20)
    for name in ('show', 'suggest-title', 'title'):
        command = sub.add_parser(name)
        command.add_argument('--source', required=True); command.add_argument('--conversation', required=True)
        if name == 'title':
            command.add_argument('--set'); command.add_argument('--expected-revision', type=int)
    args = p.parse_args()
    if args.command not in ('inspect', 'web-branch') and not args.db:
        p.error('--db is required except for inspect and web-branch')
    try:
        if args.command == 'export-title-plan':
            from title_plan import make_plan
            result = make_plan(args.db, args.source, args.conversation, args.input, args.format)
        elif args.command == 'check-title-plan':
            from title_plan import check_plan
            from strict_json import loads
            result = check_plan(args.db, args.input, loads(Path(args.plan).read_text(encoding='utf-8')))
        elif args.command == 'suggest-branch-title':
            from branch_title import suggest_branch
            result = suggest_branch(args.db, args.source, args.conversation, args.input, args.node)
        elif args.command == 'web-branch':
            from web_branch import branch_view
            result = branch_view(args.input, args.conversation, args.node)
        elif args.command == 'ingest':
            result = ingest(args.db, args.source, args.input)
        elif args.command == 'search':
            result = search(args.db, args.query, args.limit)
        elif args.command == 'stats':
            c = readonly(args.db)
            try:
                result = {'messages': c.execute('SELECT count(*) FROM messages').fetchone()[0],
                          'artifacts': c.execute('SELECT count(*) FROM artifacts').fetchone()[0]}
            finally:
                c.close()
        elif args.command in ('inspect', 'import', 'title'):
            # Lazy adapter imports keep the core library free of import cycles.
            from session_workflow import inspect_export, import_export, titles
            if args.command == 'inspect':
                result = inspect_export(args.input, args.format)
            elif args.command == 'import':
                result = import_export(args.db, args.source, args.input, args.format)
            else:
                if args.set is not None and args.expected_revision is None:
                    raise ValueError('--set requires --expected-revision from a title preview')
                result = titles(args.db, args.source, args.conversation, args.set, args.expected_revision)
        elif args.command == 'list':
            from conversation_view import conversations
            result = conversations(args.db, args.source, args.limit, args.offset)
        elif args.command == 'show':
            from conversation_view import conversation
            result = conversation(args.db, args.source, args.conversation)
        elif args.command == 'find':
            from conversation_search import find
            result = find(args.db, args.query, args.source, args.limit)
        else:
            from title_suggestion import suggest
            result = suggest(args.db, args.source, args.conversation)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        p.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=args.command in ('web-branch', 'suggest-branch-title', 'export-title-plan', 'check-title-plan'), indent=2))


if __name__ == '__main__':
    main()
