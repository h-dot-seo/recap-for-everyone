"""Read-only conversation search across current display titles and message text."""
import argparse
import base64
import binascii
import hashlib
import json
import re
import sqlite3
import unicodedata
from recaplib.unicode_search import canonical_fold, canonical_span
from recaplib.archive import readonly
from recaplib.strict_json import loads
from recaplib.timestamps import RULE, parse_timestamp, validate_options


MAX_CURSOR_CHARS = 16384


def _cursor_scope(terms, source, history, export, canonical_unicode=False, text_role=None, from_date=None, until_date=None):
    value = dict(protocol='recap.find.cursor.v1', terms=terms, source=source,
                 include_title_history=history, export_sha256=export)
    if from_date is not None or until_date is not None:
        value.update(from_date=from_date, until_date=until_date, timestamp_rule=RULE)
    if text_role is not None:
        value['text_role'] = text_role
    if canonical_unicode:
        value.update(canonical_unicode='NFC(NFD(text).casefold())',
                     unicode_version=unicodedata.unidata_version)
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':')).encode('ascii')).hexdigest()


def _decode_cursor(token, scope):
    if token is None:
        return None
    try:
        if (not isinstance(token, str) or not 0 < len(token) <= MAX_CURSOR_CHARS or
                not re.fullmatch(r'[A-Za-z0-9_-]+', token)):
            raise ValueError()
        raw = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
        value = loads(raw.decode('utf-8'))
        if (not isinstance(value, dict) or set(value) != {
                'v', 'scope_sha256', 'order_sha256', 'rank', 'source', 'conversation'} or
                type(value['v']) is not int or value['v'] != 1 or
                type(value['rank']) is not int or value['rank'] not in (0, 1, 2) or
                any(not isinstance(value[key], str) or not value[key] for key in ('source', 'conversation')) or
                any(not isinstance(value[key], str) or not re.fullmatch(r'[0-9a-f]{64}', value[key])
                    for key in ('scope_sha256', 'order_sha256')) or value['scope_sha256'] != scope):
            raise ValueError()
        return value
    except (ValueError, TypeError, KeyError, binascii.Error, RecursionError):
        raise ValueError('invalid search cursor or different query/filter scope; restart without a cursor') from None


def _encode_cursor(item, scope, order):
    rank = 0 if item['matched_title'] else 1 if item.get('matched_historical_title') else 2
    value = dict(v=1, scope_sha256=scope, order_sha256=order, rank=rank,
                 source=item['source_id'], conversation=item['conversation_id'])
    token = base64.urlsafe_b64encode(json.dumps(value, sort_keys=True, ensure_ascii=True,
        separators=(',', ':')).encode('ascii')).decode('ascii').rstrip('=')
    return token if len(token) <= MAX_CURSOR_CHARS else None


def _sample_slot(masks, candidate):
    """Choose a bounded streaming coverage improvement, preserving early ties."""
    if len(masks) < 3:
        return len(masks)

    def score(values):
        covered = 0
        for value in values:
            covered |= value
        return covered.bit_count(), sum(value.bit_count() for value in values)

    best = score(masks)
    slot = None
    # On equal improvement, replace the latest existing message first.
    for index in range(len(masks) - 1, -1, -1):
        value = score(masks[:index] + masks[index + 1:] + [candidate])
        if value > best:
            best, slot = value, index
    return slot


def _matching_excerpt(original, folded, terms, width=240, canonical_unicode=False):
    """Return an unchanged source slice around the first transformed literal hit.

    Case folding can expand a character (for example, sharp s to two s's).
    Translate the folded span without retaining an offset array for a long message.
    Offsets are Python string/code-point indices, never byte or UTF-16 offsets.
    """
    hits = [(position, index, term) for index, term in enumerate(terms)
            if (position := folded.find(term)) >= 0]
    position, _, term = min(hits)
    stop = position + len(term)
    if canonical_unicode and not original.isascii():
        start, end = canonical_span(original, position, stop)
    elif original.isascii():
        start, end = position, stop
    else:
        folded_offset = 0
        start = None
        for index, character in enumerate(original):
            folded_offset += len(character.casefold())
            if start is None and folded_offset > position:
                start = index
            if folded_offset >= stop:
                end = index + 1
                break
    # Prefer a little context before the hit, without clipping a fitting match.
    context = min(60, max(0, width - (end - start)))
    snippet_start = max(0, start - context)
    snippet_end = min(len(original), snippet_start + width)
    return dict(snippet=original[snippet_start:snippet_end],
                snippet_start=snippet_start, snippet_end=snippet_end,
                snippet_truncated_before=snippet_start > 0,
                snippet_truncated_after=snippet_end < len(original),
                first_match=dict(term=term, start=start, end=end,
                                 fully_visible=end <= snippet_end))


def _matching_export_provenance(connection, tables, source, conversation, message, digest):
    query = ' UNION '.join('SELECT locator,parent FROM '+table+
            ' WHERE source=? AND conversation=? AND message=? AND original_hash=?' for table in tables)
    rows = connection.execute(query+' ORDER BY locator,parent', (source, conversation, message, digest)*len(tables))
    samples=[];count=0
    for row in rows:
        count+=1
        if len(samples)<3:
            samples.append(dict(original_sha256=digest,locator=row['locator'],parent_id=row['parent']))
    return samples,count


def find(db, query, source=None, limit=20, include_title_history=False, export_sha256=None, cursor=None, canonical_unicode=False, text_role=None, from_date=None, until_date=None):
    lower, upper = validate_options(None, from_date, until_date)
    window = from_date is not None or until_date is not None
    interpretation_counts = dict(parsed_iso=0, parsed_epoch_seconds=0, unparsed=0)
    if text_role is not None and text_role not in ('user', 'assistant', 'system', 'tool'):
        raise ValueError('text_role must be user, assistant, system or tool')
    if not isinstance(query, str) or type(limit) is not int:
        raise ValueError('query must be text and limit must be an integer')
    if type(canonical_unicode) is not bool:
        raise ValueError('canonical_unicode must be boolean')
    fold = canonical_fold if canonical_unicode else str.casefold
    if type(include_title_history) is not bool:
        raise ValueError('include_title_history must be boolean')
    if export_sha256 is not None and (not isinstance(export_sha256, str) or len(export_sha256) != 64 or any(ch not in '0123456789abcdef' for ch in export_sha256)):
        raise ValueError('export_sha256 must be a lowercase SHA-256 hex digest')
    terms = fold(query).split()
    if not terms or len(terms) > 20 or not 1 <= limit <= 1000:
        raise ValueError('provide 1..20 search terms and limit 1..1000')
    # Repeating a query term must not give it extra evidence-sampling weight.
    terms = list(dict.fromkeys(terms))
    scope = _cursor_scope(terms, source, include_title_history, export_sha256, canonical_unicode, text_role, from_date, until_date)
    after = _decode_cursor(cursor, scope)
    position = (after['rank'], after['source'], after['conversation']) if after is not None else None
    c = readonly(db)
    try:
        c.execute('BEGIN')
        history_exists = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='title_history'"
        ).fetchone()
        history_sql = (
            'SELECT h.source,h.conversation,h.title,h.id FROM title_history h JOIN '
            '(SELECT source,conversation,MAX(id) id FROM title_history '
            + ('WHERE source=? ' if source is not None else '') +
            'GROUP BY source,conversation) latest ON h.id=latest.id '
            'ORDER BY h.source COLLATE BINARY,h.conversation COLLATE BINARY')
        history_rows = iter(c.execute(history_sql, (source,) if source is not None else ())) if history_exists else iter(())
        current_title = next(history_rows, None)
        past_sql = ('SELECT source,conversation,title,id FROM title_history ' +
                    ('WHERE source=? ' if source is not None else '') +
                    'ORDER BY source COLLATE BINARY,conversation COLLATE BINARY,id DESC')
        past_rows = iter(c.execute(past_sql, (source,) if source is not None else ())) if include_title_history and history_exists else iter(())
        past_title = next(past_rows, None)
        sql = 'SELECT * FROM messages'
        params = []; filters = []; provenance_tables = []
        if source is not None:
            filters.append('source_id=?'); params.append(source)
        if text_role is not None:
            filters.append('role=?'); params.append(text_role)
        if export_sha256 is not None:
            provenance_tables = [table for table in ('export_provenance', 'export_occurrences') if c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()]
            checks = ['EXISTS (SELECT 1 FROM '+table+' p WHERE p.source=messages.source_id '
                      'AND p.conversation=messages.conversation_id AND p.message=messages.message_id '
                      'AND p.original_hash=?)' for table in provenance_tables]
            filters.append('('+' OR '.join(checks)+')' if checks else '0')
            params.extend([export_sha256]*len(checks))
        if filters: sql += ' WHERE '+' AND '.join(filters)
        sql += ' ORDER BY source_id COLLATE BINARY,conversation_id COLLATE BINARY,message_pk'
        # Keep only the current conversation's term flags and three body samples.
        # Three bounded buckets preserve title-first ranking without storing all hits.
        title_hits, historical_hits, text_hits = [], [], []
        total = available = 0
        position_seen = after is None
        order_digest = hashlib.sha256()
        item, key, found = None, None, None
        body_mask, sample_masks = 0, []

        def finish():
            nonlocal total, available, position_seen
            if item is None or not all(found):
                return
            sampled_mask = 0
            for mask in sample_masks:
                sampled_mask |= mask
            item['message_matches_truncated'] = item['message_match_count'] > len(item['message_matches'])
            item['message_term_coverage'] = dict(
                matched_terms=[term for index, term in enumerate(terms) if body_mask & (1 << index)],
                sampled_terms=[term for index, term in enumerate(terms) if sampled_mask & (1 << index)],
                unsampled_terms=[term for index, term in enumerate(terms) if (body_mask & ~sampled_mask) & (1 << index)],
                all_matched_terms_sampled=body_mask == sampled_mask)
            total += 1
            rank = 0 if item['matched_title'] else 1 if item.get('matched_historical_title') else 2
            item_position = (rank, item['source_id'], item['conversation_id'])
            order_digest.update(json.dumps(item_position, ensure_ascii=True,
                separators=(',', ':')).encode('ascii') + b'\n')
            if item_position == position:
                position_seen = True
            if position is not None and item_position <= position:
                return
            available += 1
            bucket = title_hits if item['matched_title'] else historical_hits if item.get('matched_historical_title') else text_hits
            if len(bucket) < limit:
                bucket.append(item)

        for row in c.execute(sql, params):
            if window:
                instant, kind = parse_timestamp(row['timestamp'])
                interpretation_counts[kind] += 1
                if instant is None or (lower is not None and instant < lower) or (upper is not None and instant >= upper):
                    continue
            next_key = (row['source_id'], row['conversation_id'])
            if next_key != key:
                finish()
                key = next_key
                original_title = row['title']
                if export_sha256 is not None or text_role is not None or window:
                    original_title = c.execute('SELECT title FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk LIMIT 1', key).fetchone()[0]
                # Merge two ordered cursors rather than scanning title history
                # once per conversation or retaining all overrides in Python.
                while current_title is not None and (current_title['source'], current_title['conversation']) < key:
                    current_title = next(history_rows, None)
                if current_title is not None and (current_title['source'], current_title['conversation']) == key:
                    title, revision = current_title['title'], current_title['id']
                else:
                    title, revision = original_title, 0
                folded_title = fold(title)
                found = [term in folded_title for term in terms]
                item = dict(source_id=key[0], conversation_id=key[1], original_title=original_title,
                            display_title=title, title_revision=revision, message_count=0,
                            matched_title=any(found), message_matches=[], message_match_count=0)
                body_mask, sample_masks = 0, []
                if export_sha256 is not None:
                    item.update(matched_export_sha256=export_sha256, message_count_scope='messages linked to this original export only')
                if text_role is not None:
                    item['message_count_scope'] = 'messages with the requested role' + (' linked to this original export only' if export_sha256 is not None else '')
                if window:
                    item['message_count_scope'] = 'messages inside the UTC time window' + (' with the requested role' if text_role is not None else '') + (' linked to this original export only' if export_sha256 is not None else '')
                if include_title_history:
                    item.update(matched_historical_title=False, historical_title_matches=[],
                                historical_title_match_count=0, historical_title_matches_truncated=False)
                    def match_prior(prior_title, prior_revision, origin):
                        prior_folded = fold(prior_title)
                        matches = [term in prior_folded for term in terms]
                        for index, matched in enumerate(matches):
                            found[index] = found[index] or matched
                        if any(matches):
                            item['matched_historical_title'] = True
                            item['historical_title_match_count'] += 1
                            item['historical_title_matches_truncated'] = item['historical_title_match_count'] > 3
                            if len(item['historical_title_matches']) < 3:
                                item['historical_title_matches'].append(dict(title=prior_title, title_revision=prior_revision, origin=origin))
                    while past_title is not None and (past_title['source'], past_title['conversation']) < key:
                        past_title = next(past_rows, None)
                    while past_title is not None and (past_title['source'], past_title['conversation']) == key:
                        if past_title['id'] != revision:
                            match_prior(past_title['title'], past_title['id'], 'prior_local_override')
                        past_title = next(past_rows, None)
                    if revision > 0:
                        match_prior(original_title, 0, 'archived_original_title')
            item['message_count'] += 1
            text = fold(row['text'])
            matches = [term in text for term in terms]
            found = [previous or matched for previous, matched in zip(found, matches)]
            if any(matches):
                item['message_match_count'] += 1
                mask = sum(1 << index for index, matched in enumerate(matches) if matched)
                body_mask |= mask
                slot = _sample_slot(sample_masks, mask)
                if slot is None:
                    continue
                match = dict(message_id=row['message_id'], role=row['role'],
                             source_sha256=row['source_sha256'], source_line=row['source_line'])
                match.update(_matching_excerpt(row['text'], text, terms, canonical_unicode=canonical_unicode))
                if export_sha256 is not None:
                    samples,count = _matching_export_provenance(c, provenance_tables, key[0], key[1], row['message_id'], export_sha256)
                    match.update(export_provenance=samples, export_provenance_count=count, export_provenance_truncated=count>3)
                if slot < len(sample_masks):
                    del sample_masks[slot]
                    del item['message_matches'][slot]
                # The incoming body is later than every retained sample.
                sample_masks.append(mask)
                item['message_matches'].append(match)
        finish()
        order = order_digest.hexdigest()
        if after is not None and (after['order_sha256'] != order or not position_seen):
            raise ValueError('search result order changed or cursor position is unavailable; restart without a cursor')
        page = (title_hits + historical_hits + text_hits)[:limit]
        remaining = available - len(page)
        next_cursor = _encode_cursor(page[-1], scope, order) if page and remaining else None
        result = dict(matches=page, total_matches=total, truncated=remaining > 0,
                      next_cursor=next_cursor, skipped_matches=total-available, remaining_matches=remaining,
                      pagination_semantics='cursor binds query/filter scope and matching conversation membership/ranking; each page reads fresh evidence in one snapshot; no complete content snapshot is retained between pages',
                      semantics='case-insensitive literal substrings; AND across current title and conversation messages',
                      snippet_semantics='unchanged source slice around the first matching term; at most 240 Unicode code points; zero-based half-open offsets into original message text',
                      message_sample_semantics='at most three bodies selected by streaming distinct literal-term coverage, then summed term coverage, then earliest ties; coverage describes full selected bodies, not necessarily the 240-code-point excerpts; no semantic ranking or globally optimal coverage guarantee')
        if remaining and next_cursor is None:
            result['pagination_blocker'] = 'CURSOR_IDENTITY_TOO_LARGE'
        if include_title_history:
            result.update(semantics='case-insensitive literal substrings; AND across current title, prior local titles and conversation messages',
                          title_history_scope='local archive only; at most three matching prior title records per conversation, newest overrides first then archived original',
                          warning='Prior titles may contain private details deliberately removed from the current display title. No remote titles are queried.')
        if export_sha256 is not None:
            result.update(export_sha256=export_sha256, export_provenance_available=bool(provenance_tables),
                          export_scope='Only message bodies linked by original-export provenance are searched. Current and optional historical titles remain conversation-wide archive metadata, not export-snapshot titles.')
        if text_role is not None:
            result.update(text_role=text_role, role_scope='Only message bodies with this role are searched; titles remain conversation-wide metadata. Conversations must contain a message satisfying all selected message filters.')
        if window:
            result.update(from_date=from_date, until_date=until_date,
                timestamp_interpretation=dict(rule=RULE, **interpretation_counts,
                    scope='query-time only; stored values unchanged; counts cover message rows after source, role and export filters, before the time window',
                    numeric_policy='every 1..11 digit string is Unix seconds, including date-looking values',
                    fraction_policy='fractional-second fields truncated to six digits before UTC offset arithmetic'),
                time_scope='Only message bodies inside the UTC day window are searched; titles remain conversation-wide metadata. Conversations must contain a message satisfying all selected message filters. From is inclusive; until includes the entire UTC day. Unparsed timestamps are excluded; absence is not evidence of no activity. Time filtering scans selected message rows in one read-only snapshot.')
        if canonical_unicode:
            result.update(canonical_unicode=True, unicode_version=unicodedata.unidata_version,
                normalization='NFC(NFD(text).casefold())',
                semantics=result['semantics'].replace('case-insensitive literal substrings', 'canonical caseless NFC literal substrings'),
                snippet_semantics='unchanged source slice around the first hit in normalized search order; at most 240 Unicode code points; zero-based half-open covering offsets into original message text; composition or reordering can include intervening original marks')
        return result
    finally:
        c.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',required=True); p.add_argument('query'); p.add_argument('--source'); p.add_argument('--limit',type=int,default=20)
    p.add_argument('--include-title-history', action='store_true')
    p.add_argument('--export-sha256', help='restrict message bodies to one original export provenance hash')
    p.add_argument('--text-role', choices=['user', 'assistant', 'system', 'tool'], help='restrict message bodies to one role')
    p.add_argument('--cursor', help='continue using the previous result next_cursor with the same query and filters')
    p.add_argument('--canonical-unicode', action='store_true', help='match canonical Unicode equivalents without rewriting evidence')
    p.add_argument('--from', dest='from_date')
    p.add_argument('--until', dest='until_date')
    a=p.parse_args()
    try: result=find(a.db,a.query,a.source,a.limit,a.include_title_history,a.export_sha256,a.cursor,a.canonical_unicode,a.text_role,a.from_date,a.until_date)
    except (ValueError,OSError,sqlite3.Error) as e: p.exit(1,str(e)+'\n')
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__': main()
