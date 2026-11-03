"""Read-only conversation inventory and structured evidence views; no network."""
import argparse
import json
import sqlite3
from recap import readonly


def _inventory(connection, source=None, conversation_id=None, limit=50, offset=0):
    filters, params = [], []
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
    history_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='title_history'"
    ).fetchone()
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
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
        raise ValueError('limit must be 1..1000 and offset must be nonnegative integers')
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


def conversation(db, source, conversation_id):
    connection = readonly(db)
    try:
        # Metadata, overrides and messages must describe one SQLite read snapshot.
        connection.execute('BEGIN')
        rows = _inventory(connection, source, conversation_id, limit=1)
        summary = rows[0] if rows else None
        if summary is None:
            raise ValueError('unknown conversation')
        messages = [dict(row) for row in connection.execute(
            'SELECT message_id,role,timestamp,text,title AS original_title,'
            'source_sha256,source_line FROM messages WHERE source_id=? AND conversation_id=? '
            'ORDER BY message_pk', (source, conversation_id))]
        provenance = {}
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_provenance'"
        ).fetchone()
        if exists:
            for row in connection.execute(
                'SELECT message,original_hash,locator,parent FROM export_provenance '
                'WHERE source=? AND conversation=? ORDER BY message,original_hash,locator,parent',
                (source, conversation_id)):
                provenance.setdefault(row['message'], []).append(dict(
                    original_sha256=row['original_hash'], locator=row['locator'], parent_id=row['parent']))
        for message in messages:
            message['export_provenance'] = provenance.get(message['message_id'], [])
        return dict(**summary, messages=messages, message_order='archive insertion order',
                    branch_scope='all imported text nodes; not an active-branch reconstruction',
                    scope='local archive only')
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
    args = parser.parse_args()
    try:
        result = (conversations(args.db, args.source, args.limit, args.offset)
                  if args.command == 'list' else conversation(args.db, args.source, args.conversation))
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
