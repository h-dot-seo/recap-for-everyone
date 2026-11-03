"""Read-only bounded title review pages; no batch application or model calls."""
import copy
import unicodedata
from recap import readonly
from conversation_view import _inventory
from title_proposal import content_fingerprint
from title_suggestion import excerpt
from title_rules import validate_title
from title_review import assess_title
from title_review_state import state_snapshot

SCHEMA = 'recap.title-review-queue.v1'


def _key(title):
    return ' '.join(unicodedata.normalize('NFKC', title).casefold().split())


def _state_filtered_inventory(connection, source, unrenamed_only, state, limit, offset):
    # Effective state cannot safely be filtered by stored label alone: content
    # may have changed. Scan one conversation at a time in the same read snapshot,
    # retaining only this page's metadata, never all source message bodies.
    page = []
    matched = 0
    scan_offset = 0
    while True:
        chunk = _inventory(connection, source, limit=100, offset=scan_offset, unrenamed_only=unrenamed_only)
        for record in chunk:
            rows = [dict(row) for row in connection.execute(
                'SELECT message_id,role,text FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk',
                (source, record['conversation']))]
            digest = content_fingerprint(rows)
            current = state_snapshot(connection, source, record['conversation'], digest, record['revision'])
            if current['state'] == state:
                if offset <= matched < offset + limit:
                    page.append(record)
                matched += 1
        if len(chunk) < 100:
            return page, matched
        scan_offset += len(chunk)


def review_queue(db, source, limit=20, offset=0, unrenamed_only=False, review_state_filter=None):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('explicit nonempty source required')
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 2**63-1:
        raise ValueError('limit must be 1..100 and offset must be an integer in 0..9223372036854775807')
    if type(unrenamed_only) is not bool:
        raise ValueError('unrenamed_only must be boolean')
    if review_state_filter is not None and (not isinstance(review_state_filter, str) or review_state_filter not in ('open', 'skipped', 'deferred')):
        raise ValueError('state filter must be open, skipped or deferred')
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        source_total = connection.execute('SELECT count(DISTINCT conversation_id) FROM messages WHERE source_id=?', (source,)).fetchone()[0]
        has_history = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='title_history'").fetchone()
        if unrenamed_only and has_history:
            total = connection.execute('SELECT count(DISTINCT conversation_id) FROM messages m WHERE source_id=? '
                'AND NOT EXISTS (SELECT 1 FROM title_history h WHERE h.source=m.source_id AND h.conversation=m.conversation_id)', (source,)).fetchone()[0]
        else:
            total = source_total
        before_state_filter = total
        if review_state_filter is None:
            inventory = _inventory(connection, source, limit=limit, offset=offset, unrenamed_only=unrenamed_only)
        else:
            inventory, total = _state_filtered_inventory(connection, source, unrenamed_only, review_state_filter, limit, offset)
        items = []
        for record in inventory:
            identity = record['conversation']
            rows = [dict(row) for row in connection.execute(
                'SELECT message_id,role,text FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk',
                (source, identity))]
            digest = content_fingerprint(rows)
            item = dict(conversation=identity, review_state=state_snapshot(connection, source, identity, digest, record['revision']),
                        current_title=record['display_title'],
                        current_revision=record['revision'], previously_renamed=record['revision'] > 0)
            try:
                proposed = excerpt(rows)
                validate_title(proposed['title'])
            except ValueError:
                item.update(status='UNAVAILABLE', reason_code='NO_VALID_LOCAL_EXCERPT')
            else:
                item.update(status='READY', action='no_change' if proposed['title'] == record['display_title'] else 'review_rename',
                            proposal=dict(source=source, conversation=identity, content_sha256=digest,
                                          provider='local-extractive', **proposed))
            if item['status'] == 'READY':
                item['title_advisory'] = assess_title(item['proposal'])
            items.append(item)
        # Candidate collision scope is only this page; do not pretend to generate
        # every other page's proposals. Existing-title checks scan metadata only.
        by_key = {}
        for item in items:
            if item['status'] == 'READY':
                by_key.setdefault(_key(item['proposal']['title']), []).append(item['conversation'])
        existing = {key: [] for key in by_key}
        counts = {key: 0 for key in by_key}
        title = ('COALESCE((SELECT h.title FROM title_history h WHERE h.source=m.source_id AND h.conversation=m.conversation_id ORDER BY h.id DESC LIMIT 1),m.title)'
                 if has_history else 'm.title')
        query = ('SELECT m.conversation_id,' + title + ' AS display_title FROM messages m JOIN '
                 '(SELECT MIN(message_pk) pk FROM messages WHERE source_id=? GROUP BY conversation_id) first '
                 'ON m.message_pk=first.pk ORDER BY m.conversation_id COLLATE BINARY')
        own_matches = set()
        for row in connection.execute(query, (source,)):
            key = _key(row['display_title'])
            if key in existing:
                counts[key] += 1
                # Store at most 11 so excluding self still yields up to 10 samples.
                if len(existing[key]) < 11: existing[key].append(row['conversation_id'])
                if row['conversation_id'] in by_key[key]: own_matches.add(row['conversation_id'])
        for item in items:
            if item['status'] != 'READY': continue
            key = _key(item['proposal']['title']); identity = item['conversation']
            peers = [cid for cid in by_key[key] if cid != identity]
            current = [cid for cid in existing[key] if cid != identity][:10]
            count = counts[key] - int(identity in own_matches)
            item['collisions'] = dict(page_proposal_count=len(peers), page_proposal_conversations=peers[:10],
                                      existing_title_count=count, existing_title_conversations=current,
                                      samples_limited_to=10, normalization='NFKC + casefold + whitespace collapse')
        return dict(schema=SCHEMA, source=source, limit=limit, offset=offset, total_conversations=total,
                    source_total_conversations=source_total, excluded_renamed_conversations=source_total-before_state_filter,
                    excluded_review_state_conversations=before_state_filter-total,
                    review_state_filter=review_state_filter,
                    filter='no local title history' if unrenamed_only else 'all conversations',
                    next_offset=offset+len(items) if offset+len(items) < total else None,
                    items=items, ready_count=sum(item['status'] == 'READY' for item in items),
                    unavailable_count=sum(item['status'] == 'UNAVAILABLE' for item in items),
                    execution_status='NOT_EXECUTED', remote_mutation=False,
                    semantic_validation='NOT_PERFORMED',
                    scope='Raw archive excerpts; all imported web branches/local records, not selected branch or retained replay history.',
                    warning='PRIVATE TITLES AND IDS. Read-only single database snapshot. Collisions are advisory, page proposal comparisons are not global, and this queue is unsigned. Review one proposal before applying.')
    finally:
        connection.close()


def select_queue_item(queue, conversation):
    """Select exactly one untrusted item, including an unavailable suggestion."""
    if not isinstance(queue, dict) or queue.get('schema') != SCHEMA or not isinstance(queue.get('items'), list):
        raise ValueError('unsupported title review queue')
    matches = [item for item in queue['items'] if isinstance(item, dict) and item.get('conversation') == conversation]
    if len(matches) != 1:
        raise ValueError('select exactly one conversation from the queue')
    return copy.deepcopy(matches[0])


def select_proposal(queue, conversation):
    """Select a single untrusted proposal; caller must use normal preview validation."""
    item = select_queue_item(queue, conversation)
    if item.get('status') != 'READY':
        raise ValueError('select exactly one READY conversation from the queue')
    proposal = item.get('proposal')
    if not isinstance(proposal, dict) or proposal.get('source') != queue.get('source') or proposal.get('conversation') != conversation:
        raise ValueError('queue and proposal identities do not match')
    return copy.deepcopy(proposal)
