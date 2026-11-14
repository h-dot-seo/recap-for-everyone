"""Read-only metadata inventory of the current archive layout, not validation."""
import json
from pathlib import Path
import sqlite3
import stat

from recaplib.archive import readonly
from recaplib.recovery import MAX_DETAIL_ITEMS, _fts_rows, _tables

ARCHIVE_TABLES = (
    'artifacts', 'export_conversations', 'export_nodes', 'export_occurrences', 'export_provenance', 'messages',
    'messages_fts', 'original_exports', 'title_history', 'title_review_history',
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


def describe_schema(db, *, observe_storage=False):
    """Describe one explicit read-only snapshot without creating lazy tables."""
    if observe_storage:
        return _observe_storage(db)
    return _inventory(db)


def _inventory(db, opened=None):
    connection = readonly(db)
    try:
        if opened is not None:opened.append(True)
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


STORAGE_SCHEMA = 'recap.archive-storage-observation.v1'
STORAGE_BOUNDARY = (
    'Pre-open filesystem observations and a subsequent read-only metadata inventory, not one '
    'atomic snapshot. Header fields and sidecar kinds/sizes do not establish consistency, '
    'safe copying or backup completeness. No automatic checkpoint, repair or recovery verdict. '
    'The main file is not intentionally written, but SQLite read-only opening may create or '
    'change WAL/SHM sidecars. Main symlinks and nonregular files are refused before header reads; '
    'sidecar symlink targets and contents are not read by the observer. Nonregular sidecars '
    'prevent SQLite opening; subsequent SQLite opening may use regular sidecars. These prechecks do not defend against a hostile concurrent '
    'path namespace. Inventory schema names/types may contain private text; no raw header, '
    'paths, SQL definitions or sidecar content is emitted. No network access.'
)


def _file_kind(mode):
    if stat.S_ISREG(mode):return 'regular'
    if stat.S_ISLNK(mode):return 'symlink'
    if stat.S_ISDIR(mode):return 'directory'
    if stat.S_ISFIFO(mode):return 'fifo'
    if stat.S_ISSOCK(mode):return 'socket'
    if stat.S_ISCHR(mode):return 'character_device'
    if stat.S_ISBLK(mode):return 'block_device'
    return 'other'


def _observe_storage(db):
    # Complete all lstat/header observations before describe_schema opens SQLite.
    path = Path(db)
    pre = dict(main=dict(kind='unknown', bytes=None, header=None), sidecars={})
    result = dict(schema=STORAGE_SCHEMA, status='OBSERVED', pre_open=pre,
                  inventory=None, error=None, snapshot_consistency='NOT_ESTABLISHED',
                  copy_safety='NOT_ESTABLISHED', backup_completeness='NOT_ESTABLISHED',
                  main_file_write_requested=False, sqlite_sidecar_changes_possible=True,
                  network_access=False, boundary=STORAGE_BOUNDARY)
    errors = []
    try:
        info = path.lstat()
    except (OSError, ValueError) as error:
        pre['main']['kind'] = 'absent' if isinstance(error, FileNotFoundError) else 'unavailable'
        errors.append(dict(reason='MAIN_STAT_FAILED', exception_type=type(error).__name__))
    else:
        pre['main'].update(kind=_file_kind(info.st_mode), bytes=info.st_size)
        if not stat.S_ISREG(info.st_mode):
            errors.append(dict(reason='MAIN_NOT_REGULAR', exception_type=None))
        else:
            try:
                with path.open('rb', buffering=0) as stream:
                    raw = stream.read(100)
            except (OSError, ValueError) as error:
                errors.append(dict(reason='HEADER_READ_FAILED', exception_type=type(error).__name__))
            else:
                valid = len(raw) == 100 and raw[:16] == b'SQLite format 3\x00'
                pre['main']['header'] = dict(bytes_read=len(raw), sqlite_signature=valid,
                    read_version=raw[19] if valid else None,
                    write_version=raw[18] if valid else None,
                    user_version=int.from_bytes(raw[60:64], 'big') if valid else None)
    for name in ('wal', 'shm', 'journal'):
        try:
            info = Path(str(path) + '-' + name).lstat()
        except FileNotFoundError:
            pre['sidecars'][name] = dict(kind='absent', bytes=None)
        except (OSError, ValueError) as error:
            pre['sidecars'][name] = dict(kind='unavailable', bytes=None)
            errors.append(dict(reason='SIDECAR_STAT_FAILED', exception_type=type(error).__name__))
        else:
            pre['sidecars'][name] = dict(kind=_file_kind(info.st_mode), bytes=info.st_size)
            if not stat.S_ISREG(info.st_mode):
                errors.append(dict(reason='SIDECAR_NOT_REGULAR', exception_type=None))
    if errors:
        result.update(status='OBSERVATION_ERROR', error=errors[0])
        return result
    opened = []
    try:
        result['inventory'] = _inventory(db, opened)
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as error:
        result.update(status='INVENTORY_ERROR' if opened else 'OPEN_ERROR',
                      error=dict(reason='METADATA_INVENTORY_FAILED' if opened else 'READONLY_OPEN_FAILED',
                                 exception_type=type(error).__name__))
    if len(json.dumps(result, ensure_ascii=True, indent=2).encode('ascii')) + 1 > MAX_OUTPUT_BYTES:
        result.update(status='INVENTORY_ERROR', inventory=None,
                      error=dict(reason='OUTPUT_LIMIT', exception_type=None))
    return result
