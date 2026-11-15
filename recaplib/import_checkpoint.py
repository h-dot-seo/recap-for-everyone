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
SCHEMA_V2 = 'recap.import-checkpoint.v2'
MEMBERSHIP_SEMANTICS = ('SHA-256 over compact ASCII JSON arrays [source_id,conversation_id,message_id] followed by LF; no Unicode normalization, case folding or trimming. Sorted unique lowercase hashes select saved accepted identities; the existing nine-field digest verifies their logical rows.')
MAX_CHECKPOINT_BYTES = 64 * 1024 * 1024
MAX_DELTA_BYTES = 8 * 1024 * 1024
DELTA_CATEGORIES = ('new_conversations', 'has_new_identities', 'no_new_identities')
SCOPE = 'one explicit source, all declared artifacts and accepted message identities in one read-only snapshot'
DIGEST_SEMANTICS = ('SHA-256 over compact ASCII JSON arrays [source_id,conversation_id,message_id,role,timestamp,title,text,source_sha256,source_line] followed by LF; ordered by source_id,conversation_id,message_id under SQLite BINARY collation. Local title and review histories are excluded; original message title is included.')
BOUNDARY = ('Unsigned operator-declared artifact cutoff, not authentication, archive UUID, backup, completeness, approval or review completion. Counts concern accepted identities, not export occurrences or conversations changed in the upstream service. Empty sources are allowed and do not establish source existence. No automatic advance or archive mutation.')
PRIVACY = 'PRIVATE: the saved checkpoint contains a source label, artifact hashes and a logical message digest; keep it outside shared locations.'
FIELDS = frozenset(('schema', 'source', 'declared_at', 'artifacts', 'accepted_messages', 'messages_sha256', 'digest_semantics', 'scope', 'boundary', 'archive_mutation', 'remote_mutation', 'contains_message_text'))
FIELDS_V2 = FIELDS | {'identity_sha256s', 'membership_semantics'}
BOUNDARY_V2 = ('Unsigned operator-declared accepted-identity membership cutoff, not authentication, archive UUID, backup, completeness, approval or review completion. Counts concern accepted identities, not export occurrences or upstream changes. Empty sources do not establish source existence. Membership hashes are private, guessable and linkable; collision resistance is assumed, not established. Optional provenance, topology, title and review histories are not verified. No automatic advance or archive mutation.')
PRIVACY_V2 = 'PRIVATE: the saved checkpoint contains a source label, artifact hashes, identity hashes and a logical message digest. Identity hashes can be guessed and linked; keep it outside shared locations.'
ARTIFACT_FIELDS = frozenset(('sha256', 'bytes', 'record_count'))


def _encode(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('ascii')


def _identity_sha256(source, conversation, message):
    return hashlib.sha256(_canonical_line([source, conversation, message])).hexdigest()


def validate_checkpoint(value, expected_source=None):
    """Exact detached versioned validation; diagnostics never echo input values."""
    v2 = isinstance(value, dict) and value.get('schema') == SCHEMA_V2
    try:
        raw = _encode(value)
        if len(raw) > MAX_CHECKPOINT_BYTES:
            raise ValueError()
        value = loads(raw.decode('ascii'))
        if not isinstance(value, dict):
            raise ValueError()
        v2 = value.get('schema') == SCHEMA_V2
        if set(value) != (FIELDS_V2 if v2 else FIELDS):
            raise ValueError()
        if value['schema'] not in (SCHEMA, SCHEMA_V2) or not _identity(value['source'], source=True):
            raise ValueError()
        if expected_source is not None and (not _identity(expected_source, source=True) or value['source'] != expected_source):
            raise ValueError()
        _validate_declared_at(value['declared_at'])
        if (value['digest_semantics'] != DIGEST_SEMANTICS or value['scope'] != SCOPE or value['boundary'] != (BOUNDARY_V2 if v2 else BOUNDARY) or
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
        if v2:
            tokens = value['identity_sha256s']
            if (value['membership_semantics'] != MEMBERSHIP_SEMANTICS or
                    not isinstance(tokens, list) or len(tokens) != value['accepted_messages']):
                raise ValueError()
            previous = None
            for token in tokens:
                if not _hex64(token) or previous is not None and token <= previous:
                    raise ValueError()
                previous = token
        return value
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        if v2:
            raise ValueError('invalid import checkpoint: exact bounded v2 fields and source required') from None
        raise ValueError('invalid import checkpoint: exact bounded v1 fields and source required') from None


def load_checkpoint(path, expected_source=None):
    v2 = False
    try:
        require_regular_file(path, max_bytes=MAX_CHECKPOINT_BYTES, label='import checkpoint', too_large='import checkpoint exceeds 64 MiB')
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_CHECKPOINT_BYTES + 1)
        if len(raw) > MAX_CHECKPOINT_BYTES:
            raise ValueError()
        value = loads(decode_source(raw))
        v2 = isinstance(value, dict) and value.get('schema') == SCHEMA_V2
        return validate_checkpoint(value, expected_source)
    except (OSError, ValueError, TypeError, RecursionError, UnicodeError):
        if v2:
            raise ValueError('import checkpoint must be a readable valid v2 document within 64 MiB for this source') from None
        raise ValueError('import checkpoint must be a readable valid v1 document within 64 MiB for this source') from None


def _artifact_rows(connection, source):
    for row in connection.execute('SELECT sha256,bytes,record_count FROM artifacts WHERE source_id=? ORDER BY sha256 COLLATE BINARY', (source,)):
        yield dict(row)


def _message_rows(connection, source):
    return connection.execute('SELECT source_id,conversation_id,message_id,role,timestamp,title,text,source_sha256,source_line FROM messages WHERE source_id=? ORDER BY source_id COLLATE BINARY,conversation_id COLLATE BINARY,message_id COLLATE BINARY', (source,))


def declare_checkpoint(db, source, output, declared_at=None, *, checkpoint_version=1):
    if type(checkpoint_version) is not int or checkpoint_version not in (1, 2):
        raise ValueError('checkpoint version must be 1 or 2')
    v2 = checkpoint_version == 2
    if not _identity(source, source=True):
        raise ValueError('explicit nonempty source required')
    declared_at = _validate_declared_at(declared_at)
    _reject_existing(output)
    connection = readonly(db)
    artifacts, used, count = [], 0, 0
    digest = hashlib.sha256()
    tokens = set() if v2 else None
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
            if v2:
                # Early conservative token accounting, followed by exact encoded-size admission.
                used += 72
                if used > MAX_CHECKPOINT_BYTES:
                    raise ValueError('import checkpoint exceeds 64 MiB')
                token = _identity_sha256(row['source_id'], row['conversation_id'], row['message_id'])
                if token in tokens:
                    raise ValueError('duplicate import checkpoint identity digest')
                tokens.add(token)
            digest.update(_canonical_line(list(row)))
            count += 1
    finally:
        connection.close()
    value = dict(schema=SCHEMA, source=source, declared_at=declared_at, artifacts=artifacts,
                 accepted_messages=count, messages_sha256=digest.hexdigest(), digest_semantics=DIGEST_SEMANTICS,
                 scope=SCOPE, boundary=BOUNDARY, archive_mutation=False, remote_mutation=False, contains_message_text=False)
    if v2:
        value.update(schema=SCHEMA_V2, boundary=BOUNDARY_V2,
                     membership_semantics=MEMBERSHIP_SEMANTICS, identity_sha256s=sorted(tokens))
    value = validate_checkpoint(value, source)
    raw = _encode(value)
    publication = _publish_new_file(output, raw, '.recap-import-checkpoint-')
    result = dict(schema='recap.import-checkpoint-declaration.v1', status='DECLARED', checkpoint_schema=SCHEMA,
                checkpoint_bytes=len(raw), checkpoint_sha256=hashlib.sha256(raw).hexdigest(),
                artifacts=len(artifacts), accepted_messages=count, messages_sha256=digest.hexdigest(),
                declared_at=declared_at, archive_mutation=False, remote_mutation=False, network_access=False,
                contains_message_text=False, scope=SCOPE, boundary=BOUNDARY, warning=PRIVACY, **publication)
    if v2:
        result.update(schema='recap.import-checkpoint-declaration.v2', checkpoint_schema=SCHEMA_V2,
                      membership_semantics=MEMBERSHIP_SEMANTICS, boundary=BOUNDARY_V2, warning=PRIVACY_V2)
    return result


def changed_since(db, source, checkpoint, *, delta_output=None, limit=20):
    """Verify a saved cutoff then summarize disjoint conversation categories.

    checkpoint may be a decoded document or a path. A valid document whose
    declared rows no longer match returns no delta, never guessed change counts.
    """
    if not _identity(source, source=True):
        raise ValueError('explicit nonempty source required')
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer in 1..1000')
    if delta_output is not None:
        _reject_existing(delta_output)
    checkpoint = validate_checkpoint(checkpoint, source) if isinstance(checkpoint, dict) else load_checkpoint(checkpoint, source)
    v2 = checkpoint['schema'] == SCHEMA_V2
    membership = set(checkpoint['identity_sha256s']) if v2 else None
    seen_old = set() if v2 else None
    declared = {row['sha256']: row for row in checkpoint['artifacts']}
    result = dict(schema='recap.import-changes.v1', status='CUTOFF_NOT_VERIFIED', delta=None,
                  archive_mutation=False, remote_mutation=False, network_access=False, contains_message_text=False,
                  scope=SCOPE, boundary=BOUNDARY)
    if v2:
        result.update(schema='recap.import-changes.v2', checkpoint_schema=SCHEMA_V2,
                      membership_semantics=MEMBERSHIP_SEMANTICS, boundary=BOUNDARY_V2)
    connection = readonly(db)
    digest, count = hashlib.sha256(), 0
    samples = {name: [] for name in DELTA_CATEGORIES}
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
                if delta_output is not None and len(samples[key]) < limit:
                    samples[key].append(previous)
        for row in _message_rows(connection, source):
            if row['source_sha256'] not in current_hashes:
                return result
            if row['conversation_id'] != previous:
                finish()
                previous, old, new = row['conversation_id'], False, False
            if v2:
                token = _identity_sha256(row['source_id'], row['conversation_id'], row['message_id'])
                is_old = token in membership
                if is_old:
                    if token in seen_old:
                        return result
                    seen_old.add(token)
            else:
                is_old = row['source_sha256'] in declared
            if is_old:
                digest.update(_canonical_line(list(row)))
                count += 1
                old = True
            else:
                new = True
                delta['accepted_after_cutoff_messages'] += 1
        finish()
        if v2 and seen_old != membership:
            return result
        if count != checkpoint['accepted_messages'] or digest.hexdigest() != checkpoint['messages_sha256']:
            return result
        result = dict(result, status='CUTOFF_VERIFIED', delta=delta)
    finally:
        connection.close()
    if delta_output is not None:
        document = dict(schema='recap.import-changes-delta.v1', source=source,
                        status=result['status'], delta=delta, sample_limit_per_category=limit,
                        samples=samples, omitted={name: delta[name]-len(samples[name]) for name in DELTA_CATEGORIES},
                        archive_mutation=False, remote_mutation=False, network_access=False,
                        contains_message_text=False, scope=SCOPE, boundary=BOUNDARY,
                        warning='PRIVATE CONVERSATION IDS. Bounded samples from one verified cutoff comparison, not review approval, completeness or automatic checkpoint advancement.')
        if v2:
            document.update(schema='recap.import-changes-delta.v2', checkpoint_schema=SCHEMA_V2,
                            membership_semantics=MEMBERSHIP_SEMANTICS, boundary=BOUNDARY_V2)
        raw = (json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2)+'\n').encode('ascii')
        if len(raw) > MAX_DELTA_BYTES:
            raise ValueError('delta document exceeds byte limit; reduce --limit')
        publication = _publish_new_file(delta_output, raw, '.recap-import-changes-')
        result['delta_document'] = dict(schema=document['schema'], bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(), **publication,
            warning='Private conversation IDs were written to the explicitly selected new file. File publication precedes stdout delivery; a stdout failure does not remove the published file.')
    return result
