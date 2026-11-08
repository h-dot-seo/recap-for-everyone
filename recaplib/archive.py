"""Archive core shared by recap.py and the recaplib modules: schema, normalized JSONL ingest, read-only connections and FTS search."""
import hashlib
import sqlite3
from pathlib import Path
from recaplib.strict_json import loads
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


def ingest(db, source, path, provenance=None):
    _validate_source(source)
    return ingest_bytes(db, source, Path(path).read_bytes(), provenance)


def ingest_bytes(db, source, raw, provenance=None):
    """Validate and ingest one immutable normalized JSONL byte snapshot.

    Uses the same transaction, identity and provenance rules as file ingestion.
    This writes the explicitly selected SQLite archive, not a temporary input file.
    """
    _validate_source(source)
    if not isinstance(raw, bytes):
        raise ValueError('normalized input must be immutable bytes')
    digest = hashlib.sha256(raw).hexdigest()
    records = []
    incoming = {}
    for line_no, line in enumerate(physical_lines(raw), 1):
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
        key = (row['conversation_id'], row['message_id'])
        values = (row['role'], row['timestamp'], title, row['text'])
        if key in incoming and incoming[key] != values:
            # Input-only contradictions must not create an empty archive/schema.
            # Archive comparisons still run under the write lock below.
            raise ValueError(f'conflicting message identity at line {line_no}')
        incoming[key] = values
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
        result = {'source_sha256': digest, 'records': len(records), 'inserted': inserted}
        if raw.startswith(BOM_UTF8):
            result['utf8_bom_present'] = True
        return result
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
