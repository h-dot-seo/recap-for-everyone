"""Bounded, inert views of explicitly supplied saved queues; no database reads."""
import base64
import hashlib
import html
import json
from pathlib import Path

from recaplib.document_output import write_bytes
from recaplib.render_view import _Document, STYLE
from recaplib.source_text import decode_source
from recaplib.strict_json import loads

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
ERROR = 'unsupported saved title review queue; regenerate with review-titles'
BOUNDARY = ('PRIVATE FILE. Saved queue view only; not the original application. '
            'Unsigned supplied data, not authentication, freshness, privacy clearance or approval. '
            'No database read, archive mutation, model call or network. '
            'Browser edits are not review artifacts; not a substitute for apply-title. '
            'Use the original saved JSON for a fresh preview-title before explicit application. '
            'Queue order is preserved; collisions and title flags are advisory, not decisions. '
            'Controls except LF/TAB, format characters except ZWJ/ZWNJ, and line/paragraph '
            'separators appear as literal Unicode escapes. ZWJ/ZWNJ are preserved. '
            'URLs are plain text; this display is not reversible or byte-exact.')


def _require(condition):
    if not condition:
        raise ValueError(ERROR)


def _fields(value, required, optional=()):
    _require(isinstance(value, dict) and set(required) <= value.keys() and
             value.keys() <= set(required) | set(optional))


def _integer(value, maximum=2**63-1):
    return type(value) is int and 0 <= value <= maximum


def validate_queue(queue):
    """Validate the saved envelope, identities and display fields, not archive truth."""
    _fields(queue, ('schema source limit offset total_conversations source_total_conversations '
                    'excluded_renamed_conversations excluded_review_state_conversations '
                    'review_state_filter filter next_offset items ready_count unavailable_count '
                    'execution_status remote_mutation semantic_validation scope warning').split(),
            ('proposal_mode', 'supplied_proposals', 'supplied_only', 'excluded_unsupplied_conversations'))
    _require(queue['schema'] == 'recap.title-review-queue.v1')
    for key in ('source', 'filter', 'scope', 'warning'):
        _require(isinstance(queue[key], str) and bool(queue[key]))
    for key in ('limit', 'offset', 'total_conversations', 'source_total_conversations',
                'excluded_renamed_conversations', 'excluded_review_state_conversations',
                'ready_count', 'unavailable_count'):
        _require(_integer(queue[key]))
    _require(1 <= queue['limit'] <= 100 and queue['review_state_filter'] in (None, 'open', 'skipped', 'deferred'))
    _require(queue['execution_status'] == 'NOT_EXECUTED' and queue['remote_mutation'] is False and
             queue['semantic_validation'] == 'NOT_PERFORMED')
    items = queue['items']
    _require(isinstance(items, list) and len(items) <= queue['limit'])
    _require(queue['total_conversations'] <= queue['source_total_conversations'])
    _require(len(items) == min(queue['limit'], max(0, queue['total_conversations'] - queue['offset'])))
    next_offset = queue['offset'] + len(items) if queue['offset'] + len(items) < queue['total_conversations'] else None
    _require(queue['next_offset'] is None if next_offset is None else
             type(queue['next_offset']) is int and queue['next_offset'] == next_offset)
    if 'proposal_mode' in queue or 'supplied_proposals' in queue:
        _require(queue.get('proposal_mode') == 'supplied')
        supplied = queue.get('supplied_proposals')
        _fields(supplied, ('total', 'on_page', 'not_on_page', 'validation_scope'))
        _require(all(_integer(supplied[k], 1000) for k in ('total', 'on_page', 'not_on_page')))
        _require(supplied['on_page'] <= len(items) and supplied['total'] == supplied['on_page'] + supplied['not_on_page'])
        _require(isinstance(supplied['validation_scope'], str))
    if 'supplied_only' in queue or 'excluded_unsupplied_conversations' in queue:
        _require(queue.get('supplied_only') is True and queue.get('proposal_mode') == 'supplied' and
                 _integer(queue.get('excluded_unsupplied_conversations')))
    identities = set()
    ready = 0
    for item in items:
        common = 'conversation review_state current_title current_revision previously_renamed status'.split()
        _require(isinstance(item, dict))
        status = item.get('status')
        _require(status in ('READY', 'UNAVAILABLE'))
        _fields(item, common + (['action', 'proposal', 'title_advisory', 'collisions'] if status == 'READY' else ['reason_code']))
        identity = item['conversation']
        _require(isinstance(identity, str) and identity and identity not in identities)
        identities.add(identity)
        _require(isinstance(item['current_title'], str) and _integer(item['current_revision']))
        _require(type(item['previously_renamed']) is bool and item['previously_renamed'] == (item['current_revision'] > 0))
        state = item['review_state']
        _fields(state, 'state state_revision recorded_state decision_current stale_decision expected_content_sha256 expected_title_revision'.split())
        _require(state['state'] in ('open', 'skipped', 'deferred') and state['recorded_state'] in (None, 'open', 'skipped', 'deferred'))
        _require(_integer(state['state_revision']) and _integer(state['expected_title_revision']) and
                 state['expected_title_revision'] == item['current_revision'])
        _require(type(state['decision_current']) is bool and type(state['stale_decision']) is bool)
        digest = state['expected_content_sha256']
        _require(isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest))
        if status == 'UNAVAILABLE':
            _require(isinstance(item['reason_code'], str) and bool(item['reason_code']))
            continue
        ready += 1
        _require(item['action'] in ('no_change', 'review_rename'))
        proposal = item['proposal']
        _require(isinstance(proposal, dict) and proposal.get('source') == queue['source'] and
                 proposal.get('conversation') == identity and proposal.get('content_sha256') == digest and
                 isinstance(proposal.get('title'), str) and isinstance(proposal.get('provider'), str))
        advisory = item['title_advisory']
        _fields(advisory, 'character_count maximum_characters counting privacy_flags quality_flags assessment scanned_scope matched_values_included generation_metadata_verified warning'.split())
        _require(all(_integer(advisory[k]) for k in ('character_count', 'maximum_characters')))
        _require(all(isinstance(advisory[k], str) for k in ('counting', 'assessment', 'scanned_scope', 'warning')))
        _require(advisory['matched_values_included'] is False and advisory['generation_metadata_verified'] is False)
        for key in ('privacy_flags', 'quality_flags'):
            _require(isinstance(advisory[key], list) and all(isinstance(x, str) for x in advisory[key]))
        collisions = item['collisions']
        _fields(collisions, 'page_proposal_count page_proposal_conversations existing_title_count existing_title_conversations samples_limited_to normalization'.split())
        _require(isinstance(collisions['normalization'], str) and type(collisions['samples_limited_to']) is int and collisions['samples_limited_to'] == 10)
        for prefix in ('page_proposal', 'existing_title'):
            count, samples = collisions[prefix + '_count'], collisions[prefix + '_conversations']
            _require(_integer(count) and isinstance(samples, list) and len(samples) <= min(count, 10) and
                     all(isinstance(x, str) for x in samples))
    _require(queue['ready_count'] == ready and queue['unavailable_count'] == len(items) - ready)


class _QueueDocument(_Document):
    def add(self, text):
        raw = text.encode('utf-8')
        if len(self.raw) + len(raw) > MAX_OUTPUT_BYTES:
            raise ValueError('queue view exceeds 16 MiB; save a smaller review-titles page')
        self.raw.extend(raw)


def render_queue(input_path, output):
    with Path(input_path).open('rb') as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError('saved queue exceeds 16 MiB; save a smaller review-titles page')
    try:
        queue = loads(decode_source(raw))
        # Reject NaN, infinities and encoder-depth failures without private diagnostics.
        for unused in json.JSONEncoder(allow_nan=False).iterencode(queue):
            pass
        validate_queue(queue)
    except (ValueError, TypeError, RecursionError):
        raise ValueError(ERROR) from None
    document = _QueueDocument()
    style_hash = base64.b64encode(hashlib.sha256(STYLE.encode('utf-8')).digest()).decode('ascii')
    policy = ("default-src 'none'; style-src 'sha256-" + style_hash + "'; base-uri 'none'; "
              "form-action 'none'; object-src 'none'; frame-src 'none'")
    document.add('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
                 '<meta http-equiv="Content-Security-Policy" content="' + html.escape(policy, quote=True) + '">'
                 '<meta name="referrer" content="no-referrer"><title>Saved title review queue</title>'
                 '<style>' + STYLE + '</style></head><body><h1>Saved title review queue</h1>')
    document.add('<p class="boundary">' + BOUNDARY + '</p><h2>Saved file binding</h2>')
    document.value(dict(schema='recap.queue-html.v1', command='render-queue',
                        input_sha256=hashlib.sha256(raw).hexdigest(), input_bytes=len(raw)))
    document.add('<h2>Supplied queue metadata</h2>')
    document.value({key: value for key, value in queue.items() if key != 'items'})
    for index, item in enumerate(queue['items'], 1):
        document.add('<section id="q-%04d"><h2>Queue item %d</h2>' % (index, index))
        document.value(item)
        document.add('</section>\n')
    document.add('<footer><p>' + BOUNDARY + '</p></footer></body></html>\n')
    rendered = bytes(document.raw)
    staging = write_bytes(rendered, output, '.recap-view-')
    return dict(schema='recap.saved-view.v1', status='SAVED', document_kind='html',
                encoding='UTF-8', bytes=len(rendered), sha256=hashlib.sha256(rendered).hexdigest(),
                **staging, scope='new local saved-queue view only; no database read or approval',
                warning='PRIVATE FILE. Keep outside public or shared folders. No model call, network or authentication. '
                        'Browser edits are not review artifacts; not a substitute for apply-title. '
                        'If staging cleanup failed, the complete output already exists; inspect the leftover file rather than blindly retrying.')
