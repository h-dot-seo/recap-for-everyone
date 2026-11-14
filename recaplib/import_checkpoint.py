"""Unsigned artifact cutoffs for accepted identities, never import completeness."""
import hashlib
import json
from pathlib import Path

from recaplib.archive import readonly
from recaplib.input_files import require_regular_file
from recaplib.recovery import _canonical_line, _publish_new_file, _reject_existing, _validate_declared_at
from recaplib.review_checkpoint import _identity, _hex64
from recaplib.source_text import decode_source
from recaplib.strict_json import loads

SCHEMA = 'recap.import-checkpoint.v1'
MAX_CHECKPOINT_BYTES = 64 * 1024 * 1024
SCOPE = 'one explicit source, all declared artifacts and accepted message identities in one read-only snapshot'
DIGEST_SEMANTICS = ('SHA-256 over compact ASCII JSON arrays [source_id,conversation_id,message_id,role,timestamp,title,text,source_sha256,source_line] followed by LF; ordered by source_id,conversation_id,message_id under SQLite BINARY collation. Local title and review histories are excluded; original message title is included.')
BOUNDARY = ('Unsigned operator-declared artifact cutoff, not authentication, archive UUID, backup, completeness, approval or review completion. Counts concern accepted identities, not export occurrences or conversations changed in the upstream service. Empty sources are allowed and do not establish source existence. No automatic advance or archive mutation.')
PRIVACY = 'PRIVATE: the saved checkpoint contains a source label, artifact hashes and a logical message digest; keep it outside shared locations.'
FIELDS = frozenset(('schema', 'source', 'declared_at', 'artifacts', 'accepted_messages', 'messages_sha256', 'digest_semantics', 'scope', 'boundary', 'archive_mutation', 'remote_mutation', 'contains_message_text'))
ARTIFACT_FIELDS = frozenset(('sha256', 'bytes', 'record_count'))


def _encode(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('ascii')


def validate_checkpoint(value, expected_source=None):
    """Exact detached v1 validation; diagnostics never echo input values."""
    try:
        raw = _encode(value)
        if len(raw) > MAX_CHECKPOINT_BYTES:
            raise ValueError()
        value = loads(raw.decode('ascii'))
        if not isinstance(value, dict) or set(value) != FIELDS:
            raise ValueError()
        if value['schema'] != SCHEMA or not _identity(value['source'], source=True):
            raise ValueError()
        if expected_source is not None and (not _identity(expected_source, source=True) or value['source'] != expected_source):
            raise ValueError()
        _validate_declared_at(value['declared_at'])
        if (value['digest_semantics'] != DIGEST_SEMANTICS or value['scope'] != SCOPE or value['boundary'] != BOUNDARY or
                any(value[k] is not False for k in ('archive_mutation', 'remote_mutation', 'contains_message_text')) or
                type(value['accepted_messages']) is not int or value['accepted_messages'] < 0 or not _hex64(value['messages_sha256'])):
            raise ValueError()
        if not isinstance(value['artifacts'], list):
            raise ValueError()
        previous = None
        for row in value['artifacts']:
            if (not isinstance(row, dict) or set(row) != ARTIFACT_FIELDS or not _hex64(row['sha256']) or
                    any(type(row[k]) is not int or row[k] < 0 for k in ('bytes', 'record_count')) or
                    previous is not None and row['sha256'] <= previous):
                raise ValueError()
            previous = row['sha256']
        return value
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ValueError('invalid import checkpoint: exact bounded v1 fields and source required') from None


def load_checkpoint(path, expected_source=None):
    try:
        require_regular_file(path, max_bytes=MAX_CHECKPOINT_BYTES, label='import checkpoint', too_large='import checkpoint exceeds 64 MiB')
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_CHECKPOINT_BYTES + 1)
        if len(raw) > MAX_CHECKPOINT_BYTES:
            raise ValueError()
        return validate_checkpoint(loads(decode_source(raw)), expected_source)
    except (OSError, ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError('import checkpoint must be a readable valid v1 document within 64 MiB for this source') from None


def _artifact_rows(connection, source):
    for row in connection.execute('SELECT sha256,bytes,record_count FROM artifacts WHERE source_id=? ORDER BY sha256 COLLATE BINARY', (source,)):
        yield dict(row)


def _message_rows(connection, source):
    return connection.execute('SELECT source_id,conversation_id,message_id,role,timestamp,title,text,source_sha256,source_line FROM messages WHERE source_id=? ORDER BY source_id COLLATE BINARY,conversation_id COLLATE BINARY,message_id COLLATE BINARY', (source,))


def declare_checkpoint(db, source, output, declared_at=None):
    if not _identity(source, source=True):
        raise ValueError('explicit nonempty source required')
    declared_at = _validate_declared_at(declared_at)
    _reject_existing(output)
    connection = readonly(db)
    artifacts, used, count = [], 0, 0
    digest = hashlib.sha256()
    try:
        connection.execute('BEGIN')
        for row in _artifact_rows(connection, source):
            used += len(_encode(row))
            if used > MAX_CHECKPOINT_BYTES:
                raise ValueError('import checkpoint exceeds 64 MiB')
            artifacts.append(row)
        hashes = {row['sha256'] for row in artifacts}
        for row in _message_rows(connection, source):
            if row['source_sha256'] not in hashes:
                raise ValueError('archive message has no declared artifact')
            digest.update(_canonical_line(list(row)))
            count += 1
    finally:
        connection.close()
    value = dict(schema=SCHEMA, source=source, declared_at=declared_at, artifacts=artifacts,
                 accepted_messages=count, messages_sha256=digest.hexdigest(), digest_semantics=DIGEST_SEMANTICS,
                 scope=SCOPE, boundary=BOUNDARY, archive_mutation=False, remote_mutation=False, contains_message_text=False)
    value = validate_checkpoint(value, source)
    raw = _encode(value)
    publication = _publish_new_file(output, raw, '.recap-import-checkpoint-')
    return dict(schema='recap.import-checkpoint-declaration.v1', status='DECLARED', checkpoint_schema=SCHEMA,
                checkpoint_bytes=len(raw), checkpoint_sha256=hashlib.sha256(raw).hexdigest(),
                artifacts=len(artifacts), accepted_messages=count, messages_sha256=digest.hexdigest(),
                declared_at=declared_at, archive_mutation=False, remote_mutation=False, network_access=False,
                contains_message_text=False, scope=SCOPE, boundary=BOUNDARY, warning=PRIVACY, **publication)


def changed_since(db, source, checkpoint):
    """Verify a saved cutoff then summarize disjoint conversation categories.

    checkpoint may be a decoded document or a path. A valid document whose
    declared rows no longer match returns no delta, never guessed change counts.
    """
    if not _identity(source, source=True):
        raise ValueError('explicit nonempty source required')
    checkpoint = validate_checkpoint(checkpoint, source) if isinstance(checkpoint, dict) else load_checkpoint(checkpoint, source)
    declared = {row['sha256']: row for row in checkpoint['artifacts']}
    result = dict(schema='recap.import-changes.v1', status='CUTOFF_NOT_VERIFIED', delta=None,
                  archive_mutation=False, remote_mutation=False, network_access=False, contains_message_text=False,
                  scope=SCOPE, boundary=BOUNDARY)
    connection = readonly(db)
    digest, count = hashlib.sha256(), 0
    delta = dict(new_conversations=0, has_new_identities=0, no_new_identities=0, accepted_after_cutoff_messages=0)
    try:
        connection.execute('BEGIN')
        unseen = set(declared)
        current_hashes = set()
        for row in _artifact_rows(connection, source):
            current_hashes.add(row['sha256'])
            if row['sha256'] in declared:
                if row != declared[row['sha256']]:
                    return result
                unseen.discard(row['sha256'])
        if unseen:
            return result
        previous, old, new = None, False, False
        def finish():
            if previous is not None:
                key = 'has_new_identities' if old and new else 'no_new_identities' if old else 'new_conversations'
                delta[key] += 1
        for row in _message_rows(connection, source):
            if row['source_sha256'] not in current_hashes:
                return result
            if row['conversation_id'] != previous:
                finish()
                previous, old, new = row['conversation_id'], False, False
            if row['source_sha256'] in declared:
                digest.update(_canonical_line(list(row)))
                count += 1
                old = True
            else:
                new = True
                delta['accepted_after_cutoff_messages'] += 1
        finish()
        if count != checkpoint['accepted_messages'] or digest.hexdigest() != checkpoint['messages_sha256']:
            return result
        return dict(result, status='CUTOFF_VERIFIED', delta=delta)
    finally:
        connection.close()
