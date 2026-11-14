"""Read-only conversation inventory and structured evidence views; no network."""
from recaplib.cli_errors import safe_diagnostic
import argparse
import json
import sqlite3
from recaplib.archive import readonly


def _inventory(connection, source=None, conversation_id=None, limit=50, offset=0, unrenamed_only=False, after_conversation=None):
    if after_conversation is not None and (source is None or not isinstance(after_conversation, str)):
        raise ValueError('conversation continuation requires one explicit source and a text cursor')
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
    if after_conversation is not None:
        filters.append('conversation_id COLLATE BINARY > ?'); params.append(after_conversation)
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


def conversations(db, source=None, limit=50, offset=0, *, order=None, from_date=None, until_date=None):
    if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or not 0 <= offset <= 2**63-1:
        raise ValueError('limit must be 1..1000 and offset must be an integer in 0..9223372036854775807')
    timed = order is not None or from_date is not None or until_date is not None
    if timed:
        from recaplib.timestamps import validate_options
        lower, upper = validate_options(order, from_date, until_date)
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        if timed:
            from recaplib.time_inventory import timed_conversations
            return timed_conversations(connection, source, limit, offset, order, from_date, until_date, lower, upper)
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


def _context_window(connection, source, conversation_id, anchor, before, after):
    """Find a bounded interval in this conversation's archive insertion order."""
    identity = (source, conversation_id)
    row = connection.execute('SELECT message_pk FROM messages WHERE source_id=? '
                             'AND conversation_id=? AND message_id=?', (*identity, anchor)).fetchone()
    if row is None:
        raise ValueError('unknown message in conversation')
    pk = row['message_pk']
    earlier = connection.execute('SELECT message_pk FROM messages WHERE source_id=? '
        'AND conversation_id=? AND message_pk<? ORDER BY message_pk DESC LIMIT ?',
        (*identity, pk, before)).fetchall()
    later = connection.execute('SELECT message_pk FROM messages WHERE source_id=? '
        'AND conversation_id=? AND message_pk>? ORDER BY message_pk LIMIT ?',
        (*identity, pk, after)).fetchall()
    anchor_offset = connection.execute('SELECT COUNT(*) FROM messages WHERE source_id=? '
        'AND conversation_id=? AND message_pk<?', (*identity, pk)).fetchone()[0]
    selection = dict(mode='context', anchor_message_id=anchor, anchor_index=len(earlier),
        anchor_offset=anchor_offset, before=before, after=after,
        returned_before=len(earlier), returned_after=len(later), offset=anchor_offset-len(earlier),
        context_scope='neighbors in archive insertion order; no branch, replay or original-export filter',
        warning='PRIVATE MESSAGE TEXT. Neighbors can include other roles, alternate branches, discarded history or other export versions. Insertion order does not establish a reply or turn relationship. Message-count bounds are not byte limits; separate calls can observe newer state.')
    return (earlier[-1]['message_pk'] if earlier else pk,
            later[-1]['message_pk'] if later else pk, selection)


def message_provenance_rows(connection, source, conversation_id, selection_sql=None, selection_params=(), max_bytes=None):
    """Read the existing deduplicated ledger union in the caller-owned snapshot.

    selection_sql is an internally constructed messages selection, not user SQL.
    Omitting it preserves the full conversation ledger used by unpaged show.
    """
    provenance = {}
    used = 0
    tables = [name for name in ('export_provenance', 'export_occurrences') if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()]
    if tables:
        # Union preserves legacy-only archives and deduplicates backfilled rows.
        # Restrict provenance in SQL too: a one-message view must not buffer
        # the whole conversation's occurrence ledger before discarding it.
        provenance_filter = ' WHERE source=? AND conversation=?'
        provenance_params = (source, conversation_id)
        if selection_sql is not None:
            provenance_filter += ' AND message IN (SELECT message_id FROM messages' + selection_sql + ')'
            provenance_params += selection_params
        query = ' UNION '.join('SELECT message,original_hash,locator,parent FROM ' + name +
                               provenance_filter for name in tables)
        for row in connection.execute(
            query + ' ORDER BY message,original_hash,locator,parent',
            provenance_params * len(tables)):
            entry = dict(original_sha256=row['original_hash'], locator=row['locator'], parent_id=row['parent'])
            if max_bytes is not None:
                try:
                    used += len(json.dumps(entry, ensure_ascii=True).encode('ascii'))
                except (TypeError, ValueError, UnicodeError):
                    raise ValueError('message provenance metadata is not serializable') from None
                if used > max_bytes:
                    raise ValueError('message provenance exceeds the byte limit')
            provenance.setdefault(row['message'], []).append(entry)
    return provenance


def conversation(db, source, conversation_id, limit=None, offset=0, message_id=None,
                 around_message_id=None, before=None, after=None):
    if (not isinstance(source, str) or not source.strip() or
            not isinstance(conversation_id, str) or not conversation_id):
        raise ValueError('source and conversation must be nonempty text identities')
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
    if around_message_id is None:
        if before is not None or after is not None:
            raise ValueError('before and after require an around-message selection')
    else:
        if not isinstance(around_message_id, str) or not around_message_id:
            raise ValueError('around-message ID must be nonempty text')
        if message_id is not None or limit is not None or offset:
            raise ValueError('select around-message context, an exact message or a page, not multiple modes')
        before = 2 if before is None else before
        after = 2 if after is None else after
        if any(type(value) is not int or not 0 <= value <= 50 for value in (before, after)):
            raise ValueError('before and after must be integers in 0..50')
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
        context = None
        if message_id is not None:
            selection_sql += ' AND message_id=?'
            selection_params += (message_id,)
        elif around_message_id is not None:
            lower, upper, context = _context_window(connection, source, conversation_id,
                                                    around_message_id, before, after)
            selection_sql += ' AND message_pk BETWEEN ? AND ?'
            selection_params += (lower, upper)
        selection_sql += ' ORDER BY message_pk'
        if limit is not None:
            selection_sql += ' LIMIT ? OFFSET ?'
            selection_params += (limit, offset)
        messages = [dict(row) for row in connection.execute(
            'SELECT message_id,role,timestamp,text,title AS original_title,'
            'source_sha256,source_line FROM messages' + selection_sql, selection_params)]
        if message_id is not None and not messages:
            raise ValueError('unknown message in conversation')
        provenance = message_provenance_rows(
            connection, source, conversation_id,
            selection_sql if limit is not None or message_id is not None or context is not None else None,
            selection_params) if messages else {}
        for message in messages:
            message['export_provenance'] = provenance.get(message['message_id'], [])
        result = dict(**summary, messages=messages, message_order='archive insertion order',
                      branch_scope='all imported text nodes; not an active-branch reconstruction',
                      scope='local archive only')
        if context is not None:
            next_offset = context['offset'] + len(messages)
            context.update(returned_messages=len(messages), omitted_before=context['offset'],
                           omitted_after=summary['message_count']-next_offset,
                           next_offset=next_offset if next_offset < summary['message_count'] else None)
            result['selection'] = context
        elif message_id is not None:
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
    listing.add_argument('--order', choices=['recent', 'oldest'])
    listing.add_argument('--from', dest='from_date')
    listing.add_argument('--until', dest='until_date')
    show = sub.add_parser('show')
    show.add_argument('--output', help='save exact show JSON to a new private UTF-8 file; print receipt only')
    show.add_argument('--source', required=True)
    show.add_argument('--conversation', required=True)
    show.add_argument('--limit', type=int, help='read at most this many messages (1..1000)')
    show.add_argument('--offset', type=int, default=0, help='message offset; requires --limit')
    show.add_argument('--message', help='read exactly this message ID; excludes --limit/--offset')
    show.add_argument('--around-message', help='read bounded raw archive neighbors around this exact message ID')
    show.add_argument('--before', type=int, help='earlier archive neighbors, 0..50; default 2 with --around-message')
    show.add_argument('--after', type=int, help='later archive neighbors, 0..50; default 2 with --around-message')
    args = parser.parse_args()
    try:
        if args.command == 'list':
            result = conversations(args.db, args.source, args.limit, args.offset,
                                   order=args.order, from_date=args.from_date, until_date=args.until_date)
        elif args.output is not None:
            from recaplib.conversation_document import save_conversation
            result = save_conversation(args.db, args.source, args.conversation, args.limit, args.offset,
                                       args.message, args.around_message, args.before, args.after, output=args.output)
        else:
            result = conversation(args.db, args.source, args.conversation, args.limit, args.offset,
                                  args.message, args.around_message, args.before, args.after)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, safe_diagnostic(exc) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
