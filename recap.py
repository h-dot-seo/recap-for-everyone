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
    check.add_argument('input'); check.add_argument('--format', choices=['web', 'local', 'local-codex'], required=True)
    check.add_argument('--conversation', help='inspect an explicit conversation selection without writing')
    zip_info = sub.add_parser('inspect-web-zip', help='list conventional conversation JSON member metadata without decompression')
    zip_info.add_argument('input'); zip_info.add_argument('--limit', type=int, default=50); zip_info.add_argument('--offset', type=int, default=0)
    prepare = sub.add_parser('prepare-web-export', help='validate one explicit ZIP JSON member and publish a new no-overwrite local file')
    prepare.add_argument('input'); prepare.add_argument('--member', required=True); prepare.add_argument('--output', required=True)
    prepare.add_argument('--expected-archive-sha256', help='reject a ZIP whose bytes changed since metadata inspection')
    replay = sub.add_parser('replay-local', help='validate and project a narrow completed-turn text grammar')
    replay.add_argument('input')
    branch = sub.add_parser('web-branch', help='read one path from an explicit web export without a database')
    branch.add_argument('input'); branch.add_argument('--conversation', required=True); branch.add_argument('--node')
    branch_title = sub.add_parser('suggest-branch-title', help='suggest a local title from an archived export branch')
    branch_title.add_argument('input'); branch_title.add_argument('--source', required=True)
    branch_title.add_argument('--conversation', required=True); branch_title.add_argument('--node')
    replay_title = sub.add_parser('suggest-replay-title', help='suggest a checked local title from retained projected turns')
    replay_title.add_argument('input'); replay_title.add_argument('--source', required=True)
    replay_title.add_argument('--conversation', required=True)
    for name in ('preview-title', 'apply-title'):
        command = sub.add_parser(name, help='review a proposal' if name == 'preview-title' else 'apply a reviewed local display title')
        command.add_argument('input', help='proposal JSON for preview, reviewed preview JSON for apply')
        if name == 'preview-title':
            command.add_argument('--conversation', help='select exactly one READY item from a title review queue')
            command.add_argument('--title', help='explicit replacement title; reclassified as operator wording')
    state = sub.add_parser('review-state', help='read or explicitly record a local open/skipped/deferred review decision')
    state.add_argument('--source', required=True); state.add_argument('--conversation', required=True)
    state.add_argument('--set', choices=['open', 'skipped', 'deferred'])
    state.add_argument('--expected-state-revision', type=int); state.add_argument('--expected-title-revision', type=int)
    state.add_argument('--expected-content-sha256')
    state.add_argument('--from-queue', help='use the selected saved queue item lease; requires --set and excludes explicit expected flags')
    batch = sub.add_parser('review-titles', help='build a read-only page of local title proposals and collision warnings')
    batch.add_argument('--source', required=True); batch.add_argument('--limit', type=int, default=20); batch.add_argument('--offset', type=int, default=0)
    batch.add_argument('--state', choices=['open', 'skipped', 'deferred'], help='filter by current snapshot-bound review state; scans eligible source content')
    batch.add_argument('--unrenamed-only', action='store_true', help='exclude conversations with any existing local title history')
    transfer = sub.add_parser('title-adapter-dry-run', help='validate a mock-only transfer request without executing')
    transfer.add_argument('input'); transfer.add_argument('plan'); transfer.add_argument('target')
    simulation = sub.add_parser('title-adapter-simulate', help='simulate an explicitly approved title transfer in memory only')
    simulation.add_argument('input'); simulation.add_argument('request'); simulation.add_argument('approval'); simulation.add_argument('target')
    plan = sub.add_parser('export-title-plan', help='export metadata for a manual title change')
    plan.add_argument('input'); plan.add_argument('--format', choices=['web', 'local', 'local-codex'], required=True)
    plan.add_argument('--source', required=True); plan.add_argument('--conversation', required=True)
    check_plan = sub.add_parser('check-title-plan', help='recheck a manual title plan without executing it')
    check_plan.add_argument('input'); check_plan.add_argument('plan')
    export = sub.add_parser('import', help='import an explicitly selected web/local export')
    export.add_argument('input'); export.add_argument('--format', choices=['web', 'local', 'local-codex'], required=True); export.add_argument('--source', required=True)
    export.add_argument('--conversation', help='import only this explicit conversation after validating the whole file')
    listing = sub.add_parser('list', help='list conversations and current display titles')
    listing.add_argument('--source'); listing.add_argument('--limit', type=int, default=50); listing.add_argument('--offset', type=int, default=0)
    find = sub.add_parser('find', help='search current titles and conversation text')
    find.add_argument('query'); find.add_argument('--source'); find.add_argument('--limit', type=int, default=20)
    find.add_argument('--export-sha256', help='restrict message bodies to one original export provenance hash')
    find.add_argument('--include-title-history', action='store_true', help='also search prior local display titles; may reveal old private labels')
    for name in ('show', 'suggest-title', 'title'):
        command = sub.add_parser(name)
        command.add_argument('--source', required=True); command.add_argument('--conversation', required=True)
        if name == 'show':
            command.add_argument('--limit', type=int, help='read at most this many messages (1..1000)')
            command.add_argument('--offset', type=int, default=0, help='message offset; requires --limit')
            command.add_argument('--message', help='read exactly this message ID; excludes --limit/--offset')
        if name == 'title':
            command.add_argument('--set'); command.add_argument('--expected-revision', type=int)
    args = p.parse_args()
    if args.command not in ('inspect', 'web-branch', 'replay-local', 'prepare-web-export', 'inspect-web-zip') and not args.db:
        p.error('--db is required except for inspect, web-branch, replay-local, prepare-web-export and inspect-web-zip')
    try:
        if args.command == 'inspect-web-zip':
            from inspect_web_zip import inspect_web_zip
            result = inspect_web_zip(args.input, args.limit, args.offset)
        elif args.command == 'prepare-web-export':
            from prepare_web_export import prepare_web_export
            result = prepare_web_export(args.input, args.member, args.output, args.expected_archive_sha256)
        elif args.command == 'replay-local':
            from replay_local import reconstruct
            result = reconstruct(args.input)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            if not result['supported']:
                raise SystemExit(1)
            return
        elif args.command == 'review-state':
            from title_review_state import review_state, review_state_from_queue
            if args.from_queue is not None:
                if args.set is None or any(value is not None for value in (args.expected_state_revision, args.expected_title_revision, args.expected_content_sha256)):
                    raise ValueError('--from-queue requires --set and cannot be combined with explicit expected values')
                from strict_json import loads
                queue = loads(Path(args.from_queue).read_text(encoding='utf-8'))
                result = review_state_from_queue(args.db, args.source, args.conversation, args.set, queue)
            else:
                result = review_state(args.db, args.source, args.conversation, args.set, args.expected_state_revision, args.expected_title_revision, args.expected_content_sha256)
        elif args.command == 'review-titles':
            from title_batch import review_queue
            result = review_queue(args.db, args.source, args.limit, args.offset, args.unrenamed_only, args.state)
        elif args.command in ('title-adapter-dry-run', 'title-adapter-simulate'):
            from title_transfer import dry_run, simulate, MockTitleAdapter
            from strict_json import loads
            def document(path):
                return loads(Path(path).read_text(encoding='utf-8'))
            target = document(args.target)
            if args.command == 'title-adapter-dry-run':
                result = dry_run(args.db, args.input, document(args.plan), target)
            else:
                result = simulate(args.db, args.input, document(args.request), document(args.approval), MockTitleAdapter(target))
        elif args.command in ('preview-title', 'apply-title'):
            from title_proposal import preview, apply_preview
            from strict_json import loads
            value = loads(Path(args.input).read_text(encoding='utf-8'))
            if args.command == 'preview-title' and args.conversation is not None:
                from title_batch import select_proposal
                value = select_proposal(value, args.conversation)
            result = preview(args.db, value, args.title) if args.command == 'preview-title' else apply_preview(args.db, value)
        elif args.command == 'suggest-replay-title':
            from replay_title import suggest_replay
            result = suggest_replay(args.db, args.source, args.conversation, args.input)
        elif args.command == 'export-title-plan':
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
                result = inspect_export(args.input, args.format, args.conversation)
            elif args.command == 'import':
                result = import_export(args.db, args.source, args.input, args.format, args.conversation)
            else:
                if args.set is not None and args.expected_revision is None:
                    raise ValueError('--set requires --expected-revision from a title preview')
                result = titles(args.db, args.source, args.conversation, args.set, args.expected_revision)
        elif args.command == 'list':
            from conversation_view import conversations
            result = conversations(args.db, args.source, args.limit, args.offset)
        elif args.command == 'show':
            from conversation_view import conversation
            result = conversation(args.db, args.source, args.conversation, args.limit, args.offset, args.message)
        elif args.command == 'find':
            from conversation_search import find
            result = find(args.db, args.query, args.source, args.limit, args.include_title_history, args.export_sha256)
        else:
            from title_suggestion import suggest
            result = suggest(args.db, args.source, args.conversation)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        p.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=args.command in ('show', 'inspect-web-zip', 'prepare-web-export', 'find', 'inspect', 'import', 'web-branch', 'suggest-branch-title', 'suggest-replay-title', 'preview-title', 'apply-title', 'review-titles', 'review-state', 'title-adapter-dry-run', 'title-adapter-simulate', 'export-title-plan', 'check-title-plan'), indent=2))


if __name__ == '__main__':
    main()
