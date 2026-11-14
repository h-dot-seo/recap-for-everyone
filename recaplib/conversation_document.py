"""Save the exact read-only conversation view as a new private UTF-8 JSON file."""
import hashlib
import json
from recaplib.conversation_view import conversation, _UNSET_OFFSET
from recaplib.document_output import write_bytes
from recaplib.recovery import _reject_existing

MAX_OUTPUT_BYTES = 16 * 1024 * 1024


def save_conversation(db, source, conversation_id, limit=None, offset=_UNSET_OFFSET, message_id=None,
                      around_message_id=None, before=None, after=None, *, output, branch=False, node=None, export_sha256=None):
    _reject_existing(output)
    value = conversation(db, source, conversation_id, limit, offset, message_id,
                         around_message_id, before, after, branch=branch, node=node, export_sha256=export_sha256)
    raw = bytearray()
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2)
    for chunk in encoder.iterencode(value):
        # Preserve any stored lone surrogate as a JSON escape while keeping
        # ordinary Unicode literal and the physical file valid UTF-8.
        encoded = chunk.encode('utf-8', errors='backslashreplace')
        if len(raw) + len(encoded) + 1 > MAX_OUTPUT_BYTES:
            raise ValueError('conversation JSON exceeds the 16 MiB output limit; select fewer messages')
        raw.extend(encoded)
    raw.extend(b'\n')
    encoded = bytes(raw)
    staging = write_bytes(encoded, output, '.recap-conversation-')
    return dict(schema='recap.saved-document.v1', status='SAVED', document_kind='conversation-json',
                encoding='UTF-8', bytes=len(encoded), sha256=hashlib.sha256(encoded).hexdigest(),
                **staging,
                scope='exact show result from one read-only archive snapshot; selected messages and supplied provenance only; no archive mutation',
                warning='PRIVATE MESSAGE TEXT AND IDS. Derived archive view, not an original application export, backup or authenticity proof. Selection may be partial and branches follow show semantics. Keep outside public/shared folders. If staging cleanup failed, the complete output exists; inspect the leftover file before retrying.')
