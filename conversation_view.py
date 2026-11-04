"""Read-only conversation inventory and structured evidence views; no network."""
import argparse
import json
import sqlite3
from recap import readonly


def _inventory(connection, source=None, conversation_id=None, limit=50, offset=0, unrenamed_only=False):
    history_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='title_history'"
    ).fetchone()
    filters, params = [], []
    if unrenamed_only and history_exists:
        filters.append('NOT EXISTS (SELECT 1 FROM title_history h WHERE h.source=messages.source_id AND h.conversation=messages.conversation_id)')
    if source is not None:
        filters.append('source_id=?'); params.append(source)
    if conversation_id is not None:
        filters.append('conversation_id=?'); params.append(conversation_id)
    where = 'WHERE ' + ' AND '.join(filters) if filters else ''
    # Paginate in SQLite before constructing Python rows or looking up titles.
    rows = connection.execute(
        'SELECT source_id,conversation_id,MIN(message_pk) first_pk,COUNT(*) message_count '
        f'FROM messages {where} GROUP BY source_id,conversation_id '
        'ORDER BY source_id COLLATE BINARY,conversation_id COLLATE BINARY LIMIT ? OFFSET ?',
        (*params, limit, offset))
    result = []
    for row in rows:
        original = connection.execute('SELECT title FROM messages WHERE message_pk=?',
                                      (row['first_pk'],)).fetchone()[0]
        override = connection.execute(
            'SELECT title,id FROM title_history WHERE source=? AND conversation=? '
            'ORDER BY id DESC LIMIT 1', (row['source_id'], row['conversation_id'])
        ).fetchone() if history_exists else None
        display, revision = override if override is not None else (original, 0)
        result.append(dict(source=row['source_id'], conversation=row['conversation_id'],
                           original_title=original, display_title=display, revision=revision,
                           message_count=row['message_count']))
    return result


def conversations(db, source=None, limit=50, offset=0):
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or not 0 <= offset <= 2**63-1:
        raise ValueError('limit must be 1..1000 and offset must be an integer in 0..9223372036854775807')
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        rows = _inventory(connection, source, limit=limit, offset=offset)
        where = 'WHERE source_id=?' if source is not None else ''
        total = connection.execute(
            'SELECT COUNT(*) FROM (SELECT 1 FROM messages ' + where +
            ' GROUP BY source_id,conversation_id)', (source,) if source is not None else ()
        ).fetchone()[0]
        return dict(conversations=rows, total=total,
                    limit=limit, offset=offset, scope='local archive only')
    finally:
        connection.close()


def conversation(db, source, conversation_id, limit=None, offset=0, message_id=None):
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 1000):
        raise ValueError('message limit must be an integer in 1..1000')
    if type(offset) is not int or not 0 <= offset <= 2**63-1:
        raise ValueError('message offset must be an integer in 0..9223372036854775807')
    if limit is None and offset:
        raise ValueError('message offset requires an explicit limit')
    if message_id is not None and (not isinstance(message_id, str) or not message_id):
        raise ValueError('message ID must be nonempty text')
    if message_id is not None and (limit is not None or offset):
        raise ValueError('select an exact message or a message page, not both')
    connection = readonly(db)
    try:
        # Metadata, overrides and messages must describe one SQLite read snapshot.
        connection.execute('BEGIN')
        rows = _inventory(connection, source, conversation_id, limit=1)
        summary = rows[0] if rows else None
        if summary is None:
            raise ValueError('unknown conversation')
        selection_sql = ' WHERE source_id=? AND conversation_id=?'
        selection_params = (source, conversation_id)
        if message_id is not None:
            selection_sql += ' AND message_id=?'
            selection_params += (message_id,)
        selection_sql += ' ORDER BY message_pk'
        if limit is not None:
            selection_sql += ' LIMIT ? OFFSET ?'
            selection_params += (limit, offset)
        messages = [dict(row) for row in connection.execute(
            'SELECT message_id,role,timestamp,text,title AS original_title,'
            'source_sha256,source_line FROM messages' + selection_sql, selection_params)]
        if message_id is not None and not messages:
            raise ValueError('unknown message in conversation')
        provenance = {}
        tables = [name for name in ('export_provenance', 'export_occurrences') if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()]
        if tables and messages:
            # Union preserves legacy-only archives and deduplicates backfilled rows.
            # Restrict provenance in SQL too: a one-message view must not buffer
            # the whole conversation's occurrence ledger before discarding it.
            provenance_filter = ' WHERE source=? AND conversation=?'
            provenance_params = (source, conversation_id)
            if limit is not None or message_id is not None:
                provenance_filter += ' AND message IN (SELECT message_id FROM messages' + selection_sql + ')'
                provenance_params += selection_params
            query = ' UNION '.join('SELECT message,original_hash,locator,parent FROM ' + name +
                                   provenance_filter for name in tables)
            for row in connection.execute(
                query + ' ORDER BY message,original_hash,locator,parent',
                provenance_params * len(tables)):
                provenance.setdefault(row['message'], []).append(dict(
                    original_sha256=row['original_hash'], locator=row['locator'], parent_id=row['parent']))
        for message in messages:
            message['export_provenance'] = provenance.get(message['message_id'], [])
        result = dict(**summary, messages=messages, message_order='archive insertion order',
                      branch_scope='all imported text nodes; not an active-branch reconstruction',
                      scope='local archive only')
        if message_id is not None:
            result['selection'] = dict(mode='message', message_id=message_id, returned_messages=1)
        elif limit is not None:
            next_offset = offset + len(messages)
            result['selection'] = dict(mode='page', limit=limit, offset=offset,
                                       returned_messages=len(messages),
                                       next_offset=next_offset if next_offset < summary['message_count'] else None)
        return result
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    listing = sub.add_parser('list')
    listing.add_argument('--source')
    listing.add_argument('--limit', type=int, default=50)
    listing.add_argument('--offset', type=int, default=0)
    show = sub.add_parser('show')
    show.add_argument('--source', required=True)
    show.add_argument('--conversation', required=True)
    show.add_argument('--limit', type=int, help='read at most this many messages (1..1000)')
    show.add_argument('--offset', type=int, default=0, help='message offset; requires --limit')
    show.add_argument('--message', help='read exactly this message ID; excludes --limit/--offset')
    args = parser.parse_args()
    try:
        result = (conversations(args.db, args.source, args.limit, args.offset)
                  if args.command == 'list' else conversation(args.db, args.source, args.conversation,
                                                             args.limit, args.offset, args.message))
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
