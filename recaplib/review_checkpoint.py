"""Unsigned, source-scoped view cutoffs; no review decisions or archive writes."""
import hashlib
import json
from pathlib import Path

from recaplib.archive import readonly
from recaplib.conversation_view import _inventory
from recaplib.input_files import require_regular_file
from recaplib.recovery import _canonical_line, _publish_new_file, _reject_existing, _validate_declared_at
from recaplib.source_text import decode_source
from recaplib.strict_json import loads
from recaplib.title_proposal import content_fingerprint

SCHEMA = 'recap.review-checkpoint.v1'
DECLARATION_SCHEMA = 'recap.review-checkpoint-declaration.v1'
MAX_CHECKPOINT_BYTES = 64 * 1024 * 1024
SCOPE = 'all conversations of one explicit source in one read-only archive snapshot'
DIGEST_SEMANTICS = (
    'entries_sha256: SHA-256 over compact ASCII JSON arrays '
    '[conversation, content_sha256, title_revision], each followed by LF, ordered '
    'by conversation under SQLite BINARY collation. content_sha256 uses the existing '
    'title content fingerprint of message_id, role and text in message_pk insertion '
    'order; timestamps, provenance and review state are excluded. title_revision '
    'is the current local title-history row id, including no-op title writes.')
BOUNDARY = (
    'Unsigned private view cutoff, not approval, a skip decision, completed review '
    'or a backup. Digests detect mismatched contents but are not signatures or '
    'authentication. Source identity is not an archive UUID. A rebuilt archive '
    'with another insertion order can differ. The operator alone decides when to '
    'write a new cutoff; no database state or checkpoint is advanced automatically.')
PRIVACY = 'PRIVATE: the saved checkpoint contains source/conversation IDs and content hashes; keep it outside shared locations.'
FIELDS = frozenset(('schema', 'source', 'declared_at', 'entries', 'entries_sha256',
                    'enumerated_conversations', 'review_completion', 'archive_mutation',
                    'remote_mutation', 'contains_message_text', 'digest_semantics', 'scope', 'boundary'))
ENTRY_FIELDS = frozenset(('conversation', 'content_sha256', 'title_revision'))


def _identity(value, source=False):
    if not isinstance(value, str) or not value or source and not value.strip():
        return False
    try:
        value.encode('utf-8')
    except UnicodeError:
        return False
    return True


def _hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _entries_digest(entries):
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_line([entry['conversation'], entry['content_sha256'], entry['title_revision']]))
    return digest.hexdigest()


def _encode(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('ascii')


def validate_checkpoint(value, expected_source=None):
    """Validate exact v1 structure and digest; return a detached value, not authority."""
    try:
        if expected_source is not None and not _identity(expected_source, source=True):
            raise ValueError()
        raw = _encode(value)
        if len(raw) > MAX_CHECKPOINT_BYTES:
            raise ValueError()
        value = loads(raw.decode('ascii'))
        if not isinstance(value, dict) or set(value) != FIELDS:
            raise ValueError()
        if value['schema'] != SCHEMA or not _identity(value['source'], source=True):
            raise ValueError()
        if expected_source is not None and value['source'] != expected_source:
            raise ValueError()
        _validate_declared_at(value['declared_at'])
        if (value['review_completion'] != 'NOT_ESTABLISHED' or
                any(type(value[key]) is not bool or value[key] is not False
                    for key in ('archive_mutation', 'remote_mutation', 'contains_message_text')) or
                value['digest_semantics'] != DIGEST_SEMANTICS or value['scope'] != SCOPE or
                value['boundary'] != BOUNDARY):
            raise ValueError()
        entries = value['entries']
        if (not isinstance(entries, list) or type(value['enumerated_conversations']) is not int or
                value['enumerated_conversations'] != len(entries) or not _hex64(value['entries_sha256'])):
            raise ValueError()
        previous = None
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS:
                raise ValueError()
            identity = entry['conversation']
            if (not _identity(identity) or previous is not None and identity <= previous or
                    not _hex64(entry['content_sha256']) or type(entry['title_revision']) is not int or
                    entry['title_revision'] < 0):
                raise ValueError()
            previous = identity
        if value['entries_sha256'] != _entries_digest(entries):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ValueError('invalid review checkpoint: exact v1 fields, source, bounded data and digest required') from None


def load_checkpoint(path, expected_source=None):
    """Read an explicit bounded UTF-8 checkpoint, allowing one initial BOM."""
    try:
        require_regular_file(path, max_bytes=MAX_CHECKPOINT_BYTES, label='review checkpoint',
                             too_large='review checkpoint exceeds the 64 MiB limit')
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_CHECKPOINT_BYTES + 1)
        if len(raw) > MAX_CHECKPOINT_BYTES:
            raise ValueError()
        value = loads(decode_source(raw))
        return validate_checkpoint(value, expected_source)
    except (OSError, ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError('review checkpoint must be a readable valid v1 document within 64 MiB for this source') from None


def entry_for_record(connection, source, record):
    """Use the caller's existing snapshot; do not begin, close or mutate it."""
    rows = [dict(row) for row in connection.execute(
        'SELECT message_id,role,text FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk',
        (source, record['conversation']))]
    return dict(conversation=record['conversation'], content_sha256=content_fingerprint(rows),
                title_revision=record['revision'])


def _entries(connection, source):
    after = None
    while True:
        page = _inventory(connection, source, limit=100, after_conversation=after)
        for record in page:
            yield entry_for_record(connection, source, record)
        if len(page) < 100:
            break
        after = page[-1]['conversation']


def classify_entry(current, previous=None):
    """Content and title change counts can overlap; new is a separate category."""
    is_new = previous is None
    content = not is_new and current['content_sha256'] != previous['content_sha256']
    title = not is_new and current['title_revision'] != previous['title_revision']
    return dict(new=is_new, changed_content=content, changed_title=title,
                unchanged=not (is_new or content or title))


def compare_snapshot(connection, source, checkpoint):
    """Return (changed ID set, counts) over the entire source in caller's snapshot."""
    if not _identity(source, source=True):
        raise ValueError('explicit nonempty source required')
    checkpoint = validate_checkpoint(checkpoint, source)
    previous = {entry['conversation']: entry for entry in checkpoint['entries']}
    unseen = set(previous)
    changed = set()
    counts = dict(new=0, changed_content=0, changed_title=0, unchanged=0,
                  missing_from_archive=0, checkpoint_entries_sha256=checkpoint['entries_sha256'],
                  scope='entire source before other filters')
    for current in _entries(connection, source):
        identity = current['conversation']
        flags = classify_entry(current, previous.get(identity))
        for name, flag in flags.items():
            counts[name] += int(flag)
        if not flags['unchanged']:
            changed.add(identity)
        unseen.discard(identity)
    counts['missing_from_archive'] = len(unseen)
    return changed, counts


def declare_review_checkpoint(db, source, output, declared_at=None):
    """Exclusively save a source-wide cutoff, never a review or database decision."""
    if not _identity(source, source=True):
        raise ValueError('explicit nonempty source required')
    declared_at = _validate_declared_at(declared_at)
    _reject_existing(output)
    connection = readonly(db)
    entries = []
    used = 0
    try:
        connection.execute('BEGIN')
        for entry in _entries(connection, source):
            # A cheap lower bound stops unbounded accumulation before final pretty
            # serialization. The final full document must independently fit too.
            used += len(_canonical_line([entry['conversation'], entry['content_sha256'], entry['title_revision']]))
            if used > MAX_CHECKPOINT_BYTES:
                raise ValueError('review checkpoint exceeds the 64 MiB limit')
            entries.append(entry)
    finally:
        connection.close()
    checkpoint = dict(schema=SCHEMA, source=source, declared_at=declared_at, entries=entries,
                      entries_sha256=_entries_digest(entries), enumerated_conversations=len(entries),
                      review_completion='NOT_ESTABLISHED', archive_mutation=False, remote_mutation=False,
                      contains_message_text=False, digest_semantics=DIGEST_SEMANTICS, scope=SCOPE, boundary=BOUNDARY)
    # Refuse malformed data from an edited archive rather than publishing a
    # checkpoint that our own reader would reject.
    validate_checkpoint(checkpoint, source)
    raw = _encode(checkpoint)
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise ValueError('review checkpoint exceeds the 64 MiB limit')
    publication = _publish_new_file(output, raw, '.recap-review-checkpoint-')
    return dict(schema=DECLARATION_SCHEMA, status='DECLARED', checkpoint_schema=SCHEMA,
                checkpoint_bytes=len(raw), checkpoint_sha256=hashlib.sha256(raw).hexdigest(),
                entries_sha256=checkpoint['entries_sha256'], enumerated_conversations=len(entries),
                declared_at=declared_at, review_completion='NOT_ESTABLISHED', archive_mutation=False,
                remote_mutation=False, contains_message_text=False, network_access=False,
                scope=SCOPE, boundary=BOUNDARY, warning=PRIVACY, **publication)
