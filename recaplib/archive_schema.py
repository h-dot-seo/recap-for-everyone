"""Read-only metadata inventory of the current archive layout, not validation."""
import json
import sqlite3

from recaplib.archive import readonly
from recaplib.recovery import MAX_DETAIL_ITEMS, _fts_rows, _tables

ARCHIVE_TABLES = (
    'artifacts', 'export_conversations', 'export_nodes', 'export_occurrences', 'export_provenance', 'messages',
    'messages_fts', 'title_history', 'title_review_history',
)
LAZY_TABLES = ('export_occurrences', 'export_provenance', 'title_history', 'title_review_history')
SHADOW_TABLES = ('messages_fts_config', 'messages_fts_data', 'messages_fts_docsize', 'messages_fts_idx')
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
BOUNDARY = (
    'Metadata inventory only, not archive validation, authentication, completeness, '
    'FTS consistency or a schema stability promise. Counts reveal archive size; '
    'schema object names and declared column names/types are echoed and may be private. '
    'No message bodies, source labels, titles, paths or SQL definitions are intentionally '
    'read or emitted; arbitrary schema names/types can themselves contain private text. '
    'No archive mutation, model call or network access.'
)


def _legacy_only(connection, tables):
    if 'export_provenance' not in tables:
        return 0
    if 'export_occurrences' not in tables:
        return connection.execute('SELECT COUNT(*) FROM export_provenance').fetchone()[0]
    return connection.execute(
        'SELECT COUNT(*) FROM export_provenance p WHERE NOT EXISTS '
        '(SELECT 1 FROM export_occurrences o WHERE '
        'o.source IS p.source AND o.conversation IS p.conversation AND '
        'o.message IS p.message AND o.original_hash IS p.original_hash AND '
        'o.locator IS p.locator AND o.parent IS p.parent)').fetchone()[0]


def describe_schema(db):
    """Describe one explicit read-only snapshot without creating lazy tables."""
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        tables = _tables(connection)
        missing = [name for name in ('artifacts', 'messages', 'messages_fts') if name not in tables]
        if missing:
            raise ValueError('archive lacks the expected tables: ' + ', '.join(missing))
        # Never fall back to COUNT(*) on the external-content virtual table: it
        # reads messages rather than the index. Absence means not established.
        fts_rows = _fts_rows(connection, tables)[0] if 'messages_fts_docsize' in tables else None
        known = []
        for name in ARCHIVE_TABLES:
            if name not in tables:
                continue
            columns = [dict(name=row['name'], type=row['type'], notnull=bool(row['notnull']), pk=row['pk'])
                       for row in connection.execute('SELECT * FROM pragma_table_info(?) ORDER BY cid', (name,))]
            # Only program-constant recognized table names enter SQL identifiers.
            rows = fts_rows if name == 'messages_fts' else connection.execute(
                'SELECT COUNT(*) FROM "' + name + '"').fetchone()[0]
            known.append(dict(name=name, recognized=True, columns=columns, rows=rows))
        unknown = sorted(tables - set(ARCHIVE_TABLES) - set(SHADOW_TABLES))
        objects = {}
        for kind in ('index', 'trigger'):
            count = connection.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=?', (kind,)).fetchone()[0]
            names = [row[0] for row in connection.execute(
                'SELECT name FROM sqlite_master WHERE type=? ORDER BY name COLLATE BINARY LIMIT ?',
                (kind, MAX_DETAIL_ITEMS))]
            objects[kind + 'es' if kind == 'index' else 'triggers'] = dict(
                names=names, count=count, omitted_count=max(0, count - len(names)))
        result = dict(
            schema='recap.archive-describe.v1', runtime_sqlite_version=sqlite3.sqlite_version,
            user_version=connection.execute('PRAGMA user_version').fetchone()[0],
            tables=known,
            shadow_tables=[dict(name=name, classification='fts5_shadow') for name in SHADOW_TABLES if name in tables],
            unknown_tables=[dict(name=name, recognized=False) for name in unknown[:MAX_DETAIL_ITEMS]],
            unknown_table_count=len(unknown), unknown_tables_omitted=max(0, len(unknown) - MAX_DETAIL_ITEMS),
            ledgers_present={name: name in tables for name in LAZY_TABLES},
            fts_rows=fts_rows, fts_rows_source='messages_fts_docsize' if fts_rows is not None else None,
            legacy_only_provenance_rows=_legacy_only(connection, tables),
            **objects, archive_mutation=False, network_access=False, contains_message_text=False,
            scope='one local read-only metadata snapshot; current layout only', boundary=BOUNDARY)
        if len(json.dumps(result, ensure_ascii=True, indent=2).encode('ascii')) + 1 > MAX_OUTPUT_BYTES:
            raise ValueError('archive schema description exceeds the output byte limit')
        return result
    finally:
        connection.close()
