"""Read matching body excerpts in a single conversation's archive insertion order."""
from recaplib.timestamps import parse_timestamp


def add_message_page_arguments(parser):
    parser.add_argument('--conversation', help='with --source, page matching message bodies in this exact conversation')
    parser.add_argument('--offset', type=int, help='with --conversation, skip this many matching bodies (default 0)')


def body_rows(connection, source, conversation, text_role, export_sha256):
    """Apply the same identity, role and original-export restrictions to both find modes."""
    filters, params, tables = [], [], []
    for column, value in (('source_id', source), ('conversation_id', conversation), ('role', text_role)):
        if value is not None:
            filters.append(column + '=?')
            params.append(value)
    if export_sha256 is not None:
        tables = [table for table in ('export_provenance', 'export_occurrences') if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()]
        checks = ['EXISTS (SELECT 1 FROM ' + table + ' p WHERE p.source=messages.source_id '
                  'AND p.conversation=messages.conversation_id AND p.message=messages.message_id '
                  'AND p.original_hash=?)' for table in tables]
        filters.append('(' + ' OR '.join(checks) + ')' if checks else '0')
        params.extend([export_sha256] * len(tables))
    where = ' WHERE ' + ' AND '.join(filters) if filters else ''
    order = ' ORDER BY source_id COLLATE BINARY,conversation_id COLLATE BINARY,message_pk'
    return connection.execute('SELECT * FROM messages' + where + order, params), tables


def within_window(rows, lower, upper, counts):
    for row in rows:
        instant, kind = parse_timestamp(row['timestamp'])
        counts[kind] += 1
        if instant is not None and (lower is None or lower <= instant) and (upper is None or instant < upper):
            yield row


def message_page(rows, terms, fold, evidence, source, conversation, limit, offset):
    matches = []
    total = 0
    for row in rows:
        text = fold(row['text'])
        if any(term in text for term in terms):
            if total >= offset and len(matches) < limit:
                matches.append(evidence(row, text))
            total += 1
    end = offset + len(matches)
    return dict(schema='recap.matching-messages.v1', source_id=source, conversation_id=conversation,
                message_matches=matches, message_match_count=total, limit=limit, offset=offset,
                next_offset=end if end < total else None, message_order='archive insertion order')
