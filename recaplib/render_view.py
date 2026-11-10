"""Deterministic, inert HTML views of one read-only conversation snapshot."""
import base64
import hashlib
import html
import json
import unicodedata

from recaplib.conversation_view import conversation
from recaplib.document_output import write_bytes

MAX_OUTPUT_BYTES = 16 * 1024 * 1024
STYLE = ('body{max-width:72rem;margin:2rem auto;padding:0 1rem;font-family:sans-serif}'
         'pre{white-space:pre-wrap;overflow-wrap:anywhere;unicode-bidi:isolate}'
         'section{border-top:1px solid #888;margin-top:2rem}'
         '.boundary{border:2px solid #555;padding:1rem}')
BOUNDARY = ('PRIVATE FILE. Local archive rendering, not the original application or a vendor export. '
            'All imported text nodes in archive insertion order, not an active-branch reconstruction. '
            'Display titles are local only. Browser edits are not review artifacts; not a substitute for apply-title. '
            'No archive mutation, model call, network, authentication or approval is established. '
            'Display rule: controls except LF/TAB, format characters except ZWJ/ZWNJ, surrogates and '
            'line/paragraph separators appear as literal Unicode escapes. ZWJ/ZWNJ are preserved. '
            'URLs are plain text. This view is not a byte-exact transcript.')


def _display_chunks(value):
    """Escape bounded chunks before UTF-8 encoding, preserving ordinary Unicode."""
    for offset in range(0, len(value), 4096):
        safe = []
        for char in value[offset:offset + 4096]:
            category = unicodedata.category(char)
            if (category in ('Cc', 'Cf', 'Cs', 'Zl', 'Zp') and
                    char not in ('\n', '\t', '\u200c', '\u200d')):
                code = ord(char)
                safe.append(('\\u%04x' if code <= 0xffff else '\\U%08x') % code)
            else:
                safe.append(char)
        yield html.escape(''.join(safe), quote=True)


class _Document:
    def __init__(self):
        self.raw = bytearray()

    def add(self, text):
        raw = text.encode('utf-8')
        if len(self.raw) + len(raw) > MAX_OUTPUT_BYTES:
            raise ValueError('render exceeds 16 MiB; narrow the message selection')
        self.raw.extend(raw)

    def value(self, value):
        self.add('<pre><bdi>')
        if isinstance(value, str):
            chunks = (value,)
        else:
            chunks = json.JSONEncoder(ensure_ascii=False, allow_nan=False,
                                      sort_keys=True, indent=2).iterencode(value)
        for chunk in chunks:
            for escaped in _display_chunks(chunk):
                self.add(escaped)
        self.add('</bdi></pre>\n')


def view_sha256(view):
    """Canonical show-object hash, not a whole-conversation content fingerprint."""
    digest = hashlib.sha256()
    for chunk in json.JSONEncoder(ensure_ascii=True, allow_nan=False, sort_keys=True,
                                  separators=(',', ':')).iterencode(view):
        digest.update(chunk.encode('ascii'))
    return digest.hexdigest()


def render_html(view):
    document = _Document()
    style_hash = base64.b64encode(hashlib.sha256(STYLE.encode('utf-8')).digest()).decode('ascii')
    policy = ("default-src 'none'; style-src 'sha256-" + style_hash + "'; base-uri 'none'; "
              "form-action 'none'; object-src 'none'; frame-src 'none'")
    document.add('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                 '<meta http-equiv="Content-Security-Policy" content="' + html.escape(policy, quote=True) + '">'
                 '<meta name="referrer" content="no-referrer"><title>Local conversation view</title>'
                 '<style>' + STYLE + '</style></head><body>\n<h1>Local conversation view</h1>')
    document.add('<p class="boundary">' + BOUNDARY + '</p>\n<h2>View metadata</h2>')
    document.value(dict(schema='recap.render.v1', command='render', format='html',
                        view_sha256=view_sha256(view),
                        **{key: value for key, value in view.items() if key != 'messages'}))
    if 'selection' not in view:
        document.add('<p>Selection: full conversation; no message selector.</p>')
    for index, message in enumerate(view['messages'], 1):
        document.add('<section id="m-%04d"><h2>Message %d</h2><h3>Metadata</h3>' % (index, index))
        document.value({key: value for key, value in message.items() if key != 'text'})
        document.add('<h3>Body</h3>')
        document.value(message['text'])
        document.add('</section>\n')
    document.add('<footer><p>' + BOUNDARY + '</p></footer></body></html>\n')
    return bytes(document.raw)


def render_conversation(db, source, conversation_id, output, limit=None, offset=0,
                        message_id=None, around_message_id=None, before=None, after=None):
    view = conversation(db, source, conversation_id, limit, offset, message_id,
                        around_message_id, before, after)
    raw = render_html(view)
    staging = write_bytes(raw, output, '.recap-view-')
    return dict(schema='recap.saved-view.v1', status='SAVED', document_kind='html',
                encoding='UTF-8', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                **staging, scope='new local view only; no archive mutation or approval',
                warning='PRIVATE FILE. No model call, network or authentication. Keep outside public or shared folders. '
                        'Browser edits are not review artifacts; not a substitute for apply-title. '
                        'If staging cleanup failed, the complete output already exists; inspect the leftover file rather than blindly retrying.')
