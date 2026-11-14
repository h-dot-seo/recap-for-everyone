"""Private, unsigned message metadata cards; no text or publication authority."""
import hashlib
import json
from pathlib import Path

from recaplib.archive import readonly
from recaplib.conversation_view import message_provenance_rows
from recaplib.input_files import require_regular_file
from recaplib.recovery import _publish_new_file, _reject_existing, _validate_declared_at
from recaplib.review_checkpoint import _identity, _hex64
from recaplib.source_text import decode_source
from recaplib.strict_json import loads

SCHEMA = 'recap.message-provenance.v1'
MAX_CARD_BYTES = 64 * 1024 * 1024
DIGEST_SEMANTICS = ('text_sha256 is SHA-256 of exact message text UTF-8 bytes, not of an export file. '
                    'source_sha256 identifies the normalized ingest artifact bytes, whose newline convention can depend on the importing platform; source_line is its one-based physical line. '
                    'export_provenance original_sha256 identifies original export bytes with locator and parent_id anchors. These distinct hash domains are not interchangeable.')
BOUNDARY = ('PRIVATE unsigned metadata card containing source/conversation/message identities, timestamps and export anchors. '
            'Hashes of short or guessable text can disclose its contents through guessing. No text or titles are included. '
            'Matching local metadata does not establish authorship, consent, publication citation suitability, source validity, completeness or retrievability. '
            'No automatic authority, archive mutation, external retrieval or network access.')
FIELDS = frozenset(('schema', 'source', 'conversation', 'message_id', 'role', 'timestamp', 'text_sha256', 'text_utf8_bytes',
                    'source_sha256', 'source_line', 'export_provenance', 'declared_at', 'digest_semantics', 'boundary',
                    'contains_message_text', 'contains_title', 'archive_mutation', 'network_access',
                    'authorship_verified', 'consent_verified', 'publication_citation'))
ANCHOR_FIELDS = frozenset(('original_sha256', 'locator', 'parent_id'))
FLAGS = dict(contains_message_text=False, contains_title=False, archive_mutation=False, network_access=False,
             authorship_verified='NOT_ESTABLISHED', consent_verified='NOT_ESTABLISHED', publication_citation='NOT_ESTABLISHED')


def _encode(value):
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('ascii')


def _text(value):
    if not isinstance(value, str):
        return False
    try:
        value.encode('utf-8')
    except UnicodeError:
        return False
    return True


def _anchor_key(row):
    # SQLite ascending BINARY ordering places NULL before text.
    return tuple((0, '') if row[key] is None else (1, row[key])
                 for key in ('original_sha256', 'locator', 'parent_id'))


def validate_card(value):
    """Return a detached exact bounded document; errors never echo field values."""
    try:
        raw = _encode(value)
        if len(raw) > MAX_CARD_BYTES:
            raise ValueError()
        value = loads(raw.decode('ascii'))
        if not isinstance(value, dict) or set(value) != FIELDS or value['schema'] != SCHEMA:
            raise ValueError()
        if (not _identity(value['source'], source=True) or
                any(not _identity(value[k]) for k in ('conversation', 'message_id')) or
                value['role'] not in ('user', 'assistant', 'system', 'tool') or not _identity(value['timestamp']) or
                not _hex64(value['text_sha256']) or not _hex64(value['source_sha256']) or
                type(value['text_utf8_bytes']) is not int or value['text_utf8_bytes'] < 0 or
                type(value['source_line']) is not int or value['source_line'] < 1):
            raise ValueError()
        _validate_declared_at(value['declared_at'])
        if value['digest_semantics'] != DIGEST_SEMANTICS or value['boundary'] != BOUNDARY:
            raise ValueError()
        for key, expected in FLAGS.items():
            if type(value[key]) is not type(expected) or value[key] != expected:
                raise ValueError()
        if not isinstance(value['export_provenance'], list):
            raise ValueError()
        previous = None
        for row in value['export_provenance']:
            if (not isinstance(row, dict) or set(row) != ANCHOR_FIELDS or not _hex64(row['original_sha256']) or
                    any(row[k] is not None and not _text(row[k]) for k in ('locator', 'parent_id'))):
                raise ValueError()
            key = _anchor_key(row)
            if previous is not None and key <= previous:
                raise ValueError()
            previous = key
        return value
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ValueError('invalid message provenance card: exact bounded v1 fields required') from None


def load_card(path):
    """Read explicit bounded UTF-8 JSON, permitting one initial UTF-8 BOM."""
    try:
        require_regular_file(path, max_bytes=MAX_CARD_BYTES, label='message provenance card', too_large='message provenance card exceeds 64 MiB')
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_CARD_BYTES + 1)
        if len(raw) > MAX_CARD_BYTES:
            raise ValueError()
        return validate_card(loads(decode_source(raw)))
    except (OSError, ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError('message provenance card must be a readable valid v1 document within 64 MiB') from None


def _card(connection, source, conversation, message_id, declared_at):
    row = connection.execute('SELECT role,timestamp,text,source_sha256,source_line FROM messages '
                             'WHERE source_id=? AND conversation_id=? AND message_id=?',
                             (source, conversation, message_id)).fetchone()
    if row is None:
        return None
    if not _text(row['text']):
        raise ValueError('archive message text must be Unicode text')
    text = row['text'].encode('utf-8')
    anchors = message_provenance_rows(connection, source, conversation,
              ' WHERE source_id=? AND conversation_id=? AND message_id=?',
              (source, conversation, message_id), max_bytes=MAX_CARD_BYTES).get(message_id, [])
    return dict(schema=SCHEMA, source=source, conversation=conversation, message_id=message_id,
                role=row['role'], timestamp=row['timestamp'], text_sha256=hashlib.sha256(text).hexdigest(),
                text_utf8_bytes=len(text), source_sha256=row['source_sha256'], source_line=row['source_line'],
                export_provenance=anchors, declared_at=declared_at, digest_semantics=DIGEST_SEMANTICS,
                boundary=BOUNDARY, **FLAGS)


def export_provenance(db, source, conversation, message_id, output, declared_at=None):
    if not _identity(source, source=True) or not _identity(conversation) or not _identity(message_id):
        raise ValueError('source, conversation and message must be nonempty Unicode identities')
    declared_at = _validate_declared_at(declared_at)
    _reject_existing(output)
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        card = _card(connection, source, conversation, message_id, declared_at)
        if card is None:
            raise ValueError('unknown message tuple')
        card = validate_card(card)
    finally:
        connection.close()
    raw = _encode(card)
    publication = _publish_new_file(output, raw, '.recap-message-provenance-')
    return dict(schema='recap.message-provenance-export.v1', status='EXPORTED', card_schema=SCHEMA,
                card_bytes=len(raw), card_sha256=hashlib.sha256(raw).hexdigest(),
                export_provenance_count=len(card['export_provenance']), declared_at=declared_at,
                boundary=BOUNDARY, **FLAGS, **publication)


def check_provenance(db, card):
    """Check exact current metadata, never fetch original exports or assert consent."""
    card = validate_card(card) if isinstance(card, dict) else load_card(card)
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        try:
            current = _card(connection, card['source'], card['conversation'], card['message_id'], card['declared_at'])
        except ValueError:
            # A now-invalid or oversized current message cannot match the valid
            # saved card. Database open/query failures still propagate normally.
            current = None
        matches = current == card
    finally:
        connection.close()
    return dict(schema='recap.message-provenance-check.v1', status='PASS' if matches else 'STALE',
                boundary=BOUNDARY, **FLAGS)
