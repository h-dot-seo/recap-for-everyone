"""Archive core shared by recap.py and the recaplib modules: schema, normalized JSONL ingest, read-only connections and FTS search."""
from recaplib.errors import ConflictingIdentity, SourceChanged
import hashlib
import io
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from recaplib.strict_json import loads
from recaplib.sqlite_safety import protect_readonly
from recaplib.source_text import BOM_UTF8, physical_lines

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


def _validate_source(source):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('source must be nonempty text')
    # Source labels come from argv/API values, outside the JSON decoder's Unicode
    # checks. SQLite cannot encode surrogates; reject them before schema creation
    # or source reads rather than leaving an empty archive after a bad label.
    if any(0xd800 <= ord(character) <= 0xdfff for character in source):
        raise ValueError('source must contain valid Unicode text')


def _validate_record(row, line_no):
    """Shared normalized row shape validation after Unicode-safe decoding/encoding."""
    required = ('conversation_id', 'message_id', 'role', 'timestamp', 'text')
    if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k] for k in required):
        raise ValueError(f'invalid record at line {line_no}')
    if row['role'] not in ('user', 'assistant', 'system', 'tool'):
        raise ValueError(f'unsupported role at line {line_no}')
    title = row.get('title', '')
    if not isinstance(title, str):
        raise ValueError(f'invalid title at line {line_no}')
    return row, title, line_no


def _normalized_records(raw):
    """Yield structurally valid records in physical order, without admission checks."""
    if not isinstance(raw, bytes):
        raise ValueError('normalized input must be immutable bytes')
    for line_no, line in enumerate(physical_lines(raw), 1):
        if not line.strip():
            continue
        try:
            row = loads(line)
        except ValueError as error:
            raise ValueError(f'invalid JSON record at line {line_no}') from error
        yield _validate_record(row, line_no)


def validate_normalized(raw):
    """Return (record tuples, text-free coverage) for one normalized byte snapshot.

    Tuples are (decoded row, effective title, physical line). Rows contain private
    content; coverage omits it. Repeated identity conflicts are counted, not raised.
    This structural inspection is not archive admission or import authorization.
    """
    records = list(_normalized_records(raw))
    seen, titles = {}, {}
    repeated = dict(identical=0, conflicting=0)
    unknown = whitespace = missing_titles = 0
    known = {'conversation_id', 'message_id', 'role', 'timestamp', 'text', 'title'}
    for row, title, _ in records:
        key = (row['conversation_id'], row['message_id'])
        values = (row['role'], row['timestamp'], title, row['text'])
        if key in seen:
            repeated['identical' if seen[key] == values else 'conflicting'] += 1
        else:
            seen[key] = values
        titles.setdefault(row['conversation_id'], set()).add(title)
        unknown += bool(set(row) - known)
        whitespace += not row['text'].strip()
        missing_titles += 'title' not in row
    warnings = []
    if not records:
        warnings.append('No records; ingest still creates an empty artifact.')
    if unknown:
        warnings.append('Unknown members are accepted and ignored, including supplied origin fields.')
    if whitespace:
        warnings.append('Whitespace-only text is accepted unchanged.')
    varied_titles = sum(len(values) > 1 for values in titles.values())
    if varied_titles:
        warnings.append('Titles differ within a conversation; the first inserted message supplies its original display title.')
    if repeated['conflicting']:
        warnings.append('Conflicting repeated identities will block ingest; inspection is not admission.')
    report = dict(format='normalized', original_sha256=hashlib.sha256(raw).hexdigest(),
        original_bytes=len(raw), records=len(records), unique_identities=len(seen),
        conversations=len(titles), role_counts=dict(sorted(Counter(row['role'] for row, _, _ in records).items())),
        repeated_input=repeated, records_with_ignored_members=unknown,
        whitespace_only_text_records=whitespace, records_without_title=missing_titles,
        conversations_with_multiple_titles=varied_titles, contains_message_text=False,
        limitations='Structural inspection only, not archive admission. Input order and supplied timestamp strings are retained. Ingest records normalized artifact hash/physical line, not original-export provenance.',
        warnings=warnings)
    if raw.startswith(BOM_UTF8):
        report['utf8_bom_present'] = True
    return records, report


def _check_expected_sha256(raw, expected_sha256):
    if expected_sha256 is not None:
        if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or
                any(ch not in '0123456789abcdef' for ch in expected_sha256)):
            raise ValueError('expected hash must be a lowercase SHA-256 hex digest')
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise SourceChanged('normalized input changed after inspection; inspect again')


def ingest(db, source, path, provenance=None, *, expected_sha256=None):
    _validate_source(source)
    return ingest_bytes(db, source, Path(path).read_bytes(), provenance, expected_sha256=expected_sha256)


def ingest_bytes(db, source, raw, provenance=None, *, expected_sha256=None):
    """Validate and ingest one immutable normalized JSONL byte snapshot.

    Uses the same transaction, identity and provenance rules as file ingestion.
    This writes the explicitly selected SQLite archive, not a temporary input file.
    """
    _validate_source(source)
    if not isinstance(raw, bytes):
        raise ValueError('normalized input must be immutable bytes')
    _check_expected_sha256(raw, expected_sha256)
    records = _admit_incoming(_normalized_records(raw))
    return _write_records(db, source, raw, records, provenance)


def _normalized_bytes(rows, newline=None):
    # Preserve the historical Path.write_text newline translation and exact JSON
    # key ordering. Encoding also rejects non-Unicode strings anywhere in rows.
    with io.BytesIO() as buffer:
        with io.TextIOWrapper(buffer, encoding='utf-8', newline=newline) as text:
            text.write(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
            text.flush()
            return buffer.getvalue()


def _check_encoded_keys(row, line_no):
    """Retain strict JSON duplicate-key rejection after encoder key coercion.

    Real adapter rows use string keys. This also checks nested ignored members
    so the private fast path cannot admit a dict that strict byte ingest rejects.
    Serialization already checked cycles and unsupported key/value types.
    """
    pending = [row]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            seen = set()
            for key, value in item.items():
                encoded_key = key if isinstance(key, str) else json.dumps(key)
                if encoded_key in seen:
                    raise ValueError(f'invalid JSON record at line {line_no}')
                seen.add(encoded_key)
                pending.append(value)
        elif isinstance(item, (list, tuple)):
            pending.extend(item)


def _validate_origin(origin):
    if origin is None:return None
    if not isinstance(origin,dict) or set(origin)!={'format','original_sha256','original_bytes','selected_conversation'}:
        raise ValueError('original export metadata must contain exactly the declared fields')
    value=dict(origin)
    if (value['format'] not in ('web','local','local-codex') or
            not isinstance(value['original_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',value['original_sha256']) or
            type(value['original_bytes']) is not int or not 0<=value['original_bytes']<=2**63-1 or
            not isinstance(value['selected_conversation'],str)):
        raise ValueError('original export metadata is malformed')
    try:value['selected_conversation'].encode('utf-8')
    except UnicodeError:raise ValueError('original export selection must be valid Unicode text') from None
    return value


def _ingest_adapter_rows(db, source, rows, *, newline=None, topology=None, origin=None):
    """Private validated adapter path: own serialization, never accept paired raw.

    JSON encoding still validates serializability/Unicode of every value. Stored
    fields retain the shared normalized row checks; conflicts are checked before
    opening SQLite. One generated JSON record occupies one physical line, even
    when string data contains newlines. The rows are not decoded a second time.
    """
    _validate_source(source)
    origin=_validate_origin(origin)
    rows = list(rows)
    raw = _normalized_bytes(rows, newline)
    for line_no, row in enumerate(rows, 1):
        _check_encoded_keys(row, line_no)
    records = _admit_incoming(_validate_record(row, line_no) for line_no, row in enumerate(rows, 1))
    if origin is not None and any(row.get('origin_sha256')!=origin['original_sha256'] or
            origin['selected_conversation'] and row['conversation_id']!=origin['selected_conversation'] for row in rows):
        raise ValueError('original export metadata does not match adapter rows')
    return _write_records(db, source, raw, records, rows, topology, origin)


def _admit_incoming(candidates):
    records = []
    incoming = {}
    for row, title, line_no in candidates:
        key = (row['conversation_id'], row['message_id'])
        values = (row['role'], row['timestamp'], title, row['text'])
        if key in incoming and incoming[key] != values:
            # Input-only contradictions must not create an empty archive/schema.
            # Archive comparisons still run under the write lock below.
            raise ConflictingIdentity(f'conflicting message identity at line {line_no}')
        incoming[key] = values
        records.append((row, title, line_no))
    return records


def _write_records(db, source, raw, records, provenance, topology=None, origin=None):
    """Shared transaction writer; callers finish validation before entering."""
    digest = hashlib.sha256(raw).hexdigest()
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
            if origin is not None:
                conn.execute("CREATE TABLE IF NOT EXISTS original_exports (source TEXT NOT NULL, original_sha256 TEXT NOT NULL, original_bytes INTEGER NOT NULL, format TEXT NOT NULL, selected_conversation TEXT NOT NULL, normalized_sha256 TEXT NOT NULL, extracted_messages INTEGER NOT NULL, PRIMARY KEY(source,original_sha256,format,selected_conversation,normalized_sha256))")
                # Match the declared identity and required-column contract without
                # depending on physical column order or repairing foreign tables.
                columns={row[1]:(row[2].upper(),row[3],row[5]) for row in conn.execute('PRAGMA table_xinfo(original_exports)')}
                expected={'source':('TEXT',1,1),'original_sha256':('TEXT',1,2),
                          'original_bytes':('INTEGER',1,0),'format':('TEXT',1,3),
                          'selected_conversation':('TEXT',1,4),'normalized_sha256':('TEXT',1,5),
                          'extracted_messages':('INTEGER',1,0)}
                if columns!=expected:raise ValueError('original export ledger layout is incompatible; no automatic repair')
                key=(source,origin['original_sha256'],origin['format'],origin['selected_conversation'],digest)
                old=conn.execute('SELECT original_bytes,extracted_messages FROM original_exports WHERE source=? AND original_sha256=? AND format=? AND selected_conversation=? AND normalized_sha256=?',key).fetchone()
                if old is not None and old!=(origin['original_bytes'],len(records)):
                    raise ConflictingIdentity('conflicting original export metadata')
                conn.execute('INSERT OR IGNORE INTO original_exports(source,original_sha256,original_bytes,format,selected_conversation,normalized_sha256,extracted_messages) VALUES(?,?,?,?,?,?,?)',
                    (source,origin['original_sha256'],origin['original_bytes'],origin['format'],origin['selected_conversation'],digest,len(records)))
                written=conn.execute('SELECT original_bytes,extracted_messages FROM original_exports WHERE source=? AND original_sha256=? AND format=? AND selected_conversation=? AND normalized_sha256=?',key).fetchone()
                if written!=(origin['original_bytes'],len(records)):
                    raise ConflictingIdentity('original export metadata was not recorded; transaction rejected')
            if topology is not None:
                conn.execute('CREATE TABLE IF NOT EXISTS export_nodes (source TEXT, conversation TEXT, original_hash TEXT, node TEXT, parent TEXT, ordinal INTEGER, has_text INTEGER, PRIMARY KEY(source,conversation,original_hash,node))')
                conn.execute('CREATE TABLE IF NOT EXISTS export_conversations (source TEXT, conversation TEXT, original_hash TEXT, current_node TEXT, current_node_state TEXT, mapping_nodes INTEGER, PRIMARY KEY(source,conversation,original_hash))')
                counts={}
                for graph in topology:
                    key=(graph['conversation'],graph['original_hash'])
                    counts[key]=counts.get(key,0)+1
                for graph in topology:
                    cid,digest_key=graph['conversation'],graph['original_hash']
                    ambiguous=counts[(cid,digest_key)]!=1
                    conn.execute('INSERT OR IGNORE INTO export_conversations VALUES(?,?,?,?,?,?)',
                        (source,cid,digest_key,None if ambiguous else graph['current_node'],
                         'ambiguous' if ambiguous else graph['current_node_state'],0 if ambiguous else len(graph['nodes'])))
                    if not ambiguous:
                        conn.executemany('INSERT OR IGNORE INTO export_nodes VALUES(?,?,?,?,?,?,?)',
                            [(source,cid,digest_key,node,parent,ordinal,has_text) for node,parent,ordinal,has_text in graph['nodes']])
            conn.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?)',
                         (source, digest, len(raw), len(records)))
            for row, title, line_no in records:
                key = (source, row['conversation_id'], row['message_id'])
                values = (row['role'], row['timestamp'], title, row['text'])
                existing = conn.execute('SELECT role,timestamp,title,text FROM messages '
                                        'WHERE source_id=? AND conversation_id=? AND message_id=?', key).fetchone()
                if existing is not None:
                    if existing != values:
                        raise ConflictingIdentity(f'conflicting message identity at line {line_no}')
                    continue
                conn.execute('INSERT INTO messages(source_id,conversation_id,message_id,role,timestamp,title,text,source_sha256,source_line) '
                             'VALUES(?,?,?,?,?,?,?,?,?)', (*key, *values, digest, line_no))
                inserted += 1
            if provenance is not None:
                occurrences = [(source, r['conversation_id'], r['message_id'], r['origin_sha256'], r['origin_locator'], r.get('parent_id')) for r in provenance]
                conn.executemany('INSERT OR IGNORE INTO export_provenance VALUES(?,?,?,?,?,?)',
                                 occurrences)
                conn.executemany('INSERT OR IGNORE INTO export_occurrences VALUES(?,?,?,?,?,?)', occurrences)
        result = {'source_sha256': digest, 'records': len(records), 'inserted': inserted}
        if raw.startswith(BOM_UTF8):
            result['utf8_bom_present'] = True
        return result
    finally:
        conn.close()


def readonly(db):
    conn = sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        protect_readonly(conn)
    except Exception:
        conn.close()
        raise
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
