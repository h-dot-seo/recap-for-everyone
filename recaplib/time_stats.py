"""Read-only per-source stored-message counts and declared timestamp coverage."""
from recaplib.archive import readonly
from recaplib.timestamps import RULE, parse_timestamp, utc_text


def stats_by_source(db):
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        connection.create_function('recap_timestamp_us', 1,
                                   lambda value: parse_timestamp(value)[0], deterministic=True)
        connection.create_function('recap_timestamp_kind', 1,
                                   lambda value: parse_timestamp(value)[1], deterministic=True)
        totals = dict(messages=connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0],
                      artifacts=connection.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0])
        rows = connection.execute('''
            WITH sources AS (SELECT source_id FROM artifacts UNION SELECT source_id FROM messages),
            counts AS (
                SELECT source_id, COUNT(*) messages,
                       COUNT(DISTINCT conversation_id COLLATE BINARY) conversations,
                       MIN(recap_timestamp_us(timestamp)) first,
                       MAX(recap_timestamp_us(timestamp)) last,
                       SUM(recap_timestamp_kind(timestamp)='parsed_iso') parsed_iso,
                       SUM(recap_timestamp_kind(timestamp)='parsed_epoch_seconds') parsed_epoch_seconds,
                       SUM(recap_timestamp_kind(timestamp)='unparsed') unparsed
                FROM messages GROUP BY source_id COLLATE BINARY)
            SELECT s.source_id, c.* FROM sources s LEFT JOIN counts c ON s.source_id=c.source_id
            ORDER BY s.source_id COLLATE BINARY''')
        sources = []
        for row in rows:
            item = dict(source=row['source_id'], first_parsed_utc=utc_text(row['first']),
                        last_parsed_utc=utc_text(row['last']))
            item.update({key: row[key] or 0 for key in
                         ('conversations', 'messages', 'parsed_iso', 'parsed_epoch_seconds', 'unparsed')})
            sources.append(item)
        return dict(**totals, sources=sources,
            timestamp_interpretation=dict(rule=RULE,
                scope='query-time only; stored values unchanged; all stored messages in one read-only snapshot',
                numeric_policy='any 1..11 digit string with optional 1..9 fractional digits is Unix seconds, including date-looking strings',
                precision='fractional seconds truncated to microseconds before UTC offset arithmetic'),
            scope='sources are the union of recorded artifact and message source IDs, in binary order; message counts count stored rows, conversation counts count distinct conversation IDs within each source; artifact-only sources have zero counts and null extrema; scans every stored message',
            warning='Counts describe stored archive rows, not source activity, ingestion attempts, completeness or timestamp authenticity. Unparsed timestamps do not contribute extrema. Source IDs and derived times may be private.')
    finally:
        connection.close()
