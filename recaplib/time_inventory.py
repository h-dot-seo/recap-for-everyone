"""Opt-in read-only time listing; default inventory SQL stays separate."""
from recaplib.timestamps import RULE, parse_timestamp, utc_text


def timed_conversations(connection, source, limit, offset, order, from_date, until_date, lower, upper):
    connection.create_function('recap_timestamp_us', 1, lambda value: parse_timestamp(value)[0], deterministic=True)
    connection.create_function('recap_timestamp_kind', 1, lambda value: parse_timestamp(value)[1], deterministic=True)
    where = 'WHERE source_id=?' if source is not None else ''
    params = [source] if source is not None else []
    window, window_params = [], []
    if lower is not None:
        window.append('recap_timestamp_us(timestamp)>=?'); window_params.append(lower)
    if upper is not None:
        window.append('recap_timestamp_us(timestamp)<?'); window_params.append(upper)
    match = ' AND '.join(window) if window else '1'
    # Title reads happen only after SQL pagination. Aggregate timestamps include
    # all messages in each qualifying conversation, not only the window hits.
    grouped = ('SELECT source_id,conversation_id,MIN(message_pk) first_pk,COUNT(*) message_count, '
               'MIN(recap_timestamp_us(timestamp)) first, MAX(recap_timestamp_us(timestamp)) last, '
               'SUM(recap_timestamp_us(timestamp) IS NULL) unparsed, '
               "SUM(recap_timestamp_kind(timestamp)='parsed_iso') parsed_iso, "
               "SUM(recap_timestamp_kind(timestamp)='parsed_epoch_seconds') parsed_epoch_seconds, "
               f'SUM(CASE WHEN {match} THEN 1 ELSE 0 END) window_hits '
               f'FROM messages {where} GROUP BY source_id,conversation_id')
    bound = (*window_params, *params)
    having = ' WHERE window_hits>0' if window else ''
    summary = connection.execute('SELECT COUNT(*) total, '
        'COALESCE(SUM(first IS NULL),0) unordered FROM (' + grouped + ')' + having, bound).fetchone()
    coverage = connection.execute('SELECT COALESCE(SUM(parsed_iso),0) parsed_iso, '
        'COALESCE(SUM(parsed_epoch_seconds),0) parsed_epoch_seconds, COALESCE(SUM(unparsed),0) unparsed, '
        'COALESCE(SUM(first IS NULL),0) unparsed_conversations FROM (' + grouped + ')', bound).fetchone()
    ordering = ('last IS NULL,last DESC,' if order == 'recent' else
                'first IS NULL,first ASC,' if order == 'oldest' else '')
    rows = connection.execute('SELECT * FROM (' + grouped + ')' + having +
        ' ORDER BY ' + ordering + 'source_id COLLATE BINARY,conversation_id COLLATE BINARY LIMIT ? OFFSET ?',
        (*bound, limit, offset))
    history_exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='title_history'").fetchone()
    result = []
    for row in rows:
        original = connection.execute('SELECT title FROM messages WHERE message_pk=?', (row['first_pk'],)).fetchone()[0]
        override = connection.execute('SELECT title,id FROM title_history WHERE source=? AND conversation=? ORDER BY id DESC LIMIT 1',
            (row['source_id'], row['conversation_id'])).fetchone() if history_exists else None
        display, revision = override if override is not None else (original, 0)
        result.append(dict(source=row['source_id'], conversation=row['conversation_id'],
            original_title=original, display_title=display, revision=revision, message_count=row['message_count'],
            first_parsed_utc=utc_text(row['first']), last_parsed_utc=utc_text(row['last']), unparsed_timestamps=row['unparsed']))
    return dict(conversations=result, total=summary['total'], limit=limit, offset=offset,
        order=order or 'binary', from_date=from_date, until_date=until_date,
        unordered_conversations=summary['unordered'],
        excluded_unparsed_conversations=coverage['unparsed_conversations'] if window else 0,
        timestamp_interpretation=dict(rule=RULE, parsed_iso=coverage['parsed_iso'],
            parsed_epoch_seconds=coverage['parsed_epoch_seconds'], unparsed=coverage['unparsed'],
            scope='all messages in the selected source scope before window filtering; query-time only; stored values unchanged',
            numeric_policy='any 1..11 digit string with optional 1..9 fractional digits is Unix seconds, including date-looking strings',
            precision='fractional seconds truncated to microseconds before UTC offset arithmetic'),
        scope='one read-only archive snapshot; scans every message in selected source scope; title lookup only for page rows',
        time_scope='conversation qualifies if any parsed message is within whole UTC days, from inclusive through until inclusive; row counts and extrema include all its messages',
        warning='Absence from a time window is not evidence of no activity. Unparsed values are not guessed; numeric strings follow the declared epoch rule. Titles and identifiers may be private.')
