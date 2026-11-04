"""Read-only conversation search across current display titles and message text."""
import argparse
import json
import sqlite3
from recap import readonly


def _matching_excerpt(original, folded, terms, width=240):
    """Return an unchanged source slice around the first literal casefold hit.

    Case folding can expand a character (for example, sharp s to two s's).
    Translate the folded span without retaining an offset array for a long message.
    Offsets are Python string/code-point indices, never byte or UTF-16 offsets.
    """
    hits = [(position, index, term) for index, term in enumerate(terms)
            if (position := folded.find(term)) >= 0]
    position, _, term = min(hits)
    stop = position + len(term)
    if original.isascii():
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


def find(db, query, source=None, limit=20, include_title_history=False, export_sha256=None):
    if not isinstance(query, str) or type(limit) is not int:
        raise ValueError('query must be text and limit must be an integer')
    if type(include_title_history) is not bool:
        raise ValueError('include_title_history must be boolean')
    if export_sha256 is not None and (not isinstance(export_sha256, str) or len(export_sha256) != 64 or any(ch not in '0123456789abcdef' for ch in export_sha256)):
        raise ValueError('export_sha256 must be a lowercase SHA-256 hex digest')
    terms = query.casefold().split()
    if not terms or len(terms) > 20 or not 1 <= limit <= 1000:
        raise ValueError('provide 1..20 search terms and limit 1..1000')
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
        # Keep only the current conversation's term flags and first three hits.
        # Three bounded buckets preserve title-first ranking without storing all hits.
        title_hits, historical_hits, text_hits = [], [], []
        total = 0
        item, key, found = None, None, None

        def finish():
            nonlocal total
            if item is None or not all(found):
                return
            total += 1
            bucket = title_hits if item['matched_title'] else historical_hits if item.get('matched_historical_title') else text_hits
            if len(bucket) < limit:
                bucket.append(item)

        for row in c.execute(sql, params):
            next_key = (row['source_id'], row['conversation_id'])
            if next_key != key:
                finish()
                key = next_key
                original_title = row['title']
                if export_sha256 is not None:
                    original_title = c.execute('SELECT title FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk LIMIT 1', key).fetchone()[0]
                # Merge two ordered cursors rather than scanning title history
                # once per conversation or retaining all overrides in Python.
                while current_title is not None and (current_title['source'], current_title['conversation']) < key:
                    current_title = next(history_rows, None)
                if current_title is not None and (current_title['source'], current_title['conversation']) == key:
                    title, revision = current_title['title'], current_title['id']
                else:
                    title, revision = original_title, 0
                folded_title = title.casefold()
                found = [term in folded_title for term in terms]
                item = dict(source_id=key[0], conversation_id=key[1], original_title=original_title,
                            display_title=title, title_revision=revision, message_count=0,
                            matched_title=any(found), message_matches=[])
                if export_sha256 is not None:
                    item.update(matched_export_sha256=export_sha256, message_count_scope='messages linked to this original export only')
                if include_title_history:
                    item.update(matched_historical_title=False, historical_title_matches=[],
                                historical_title_match_count=0, historical_title_matches_truncated=False)
                    def match_prior(prior_title, prior_revision, origin):
                        matches = [term in prior_title.casefold() for term in terms]
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
            text = row['text'].casefold()
            matches = [term in text for term in terms]
            found = [previous or matched for previous, matched in zip(found, matches)]
            if any(matches) and len(item['message_matches']) < 3:
                match = dict(message_id=row['message_id'], role=row['role'],
                             source_sha256=row['source_sha256'], source_line=row['source_line'])
                match.update(_matching_excerpt(row['text'], text, terms))
                if export_sha256 is not None:
                    samples,count = _matching_export_provenance(c, provenance_tables, key[0], key[1], row['message_id'], export_sha256)
                    match.update(export_provenance=samples, export_provenance_count=count, export_provenance_truncated=count>3)
                item['message_matches'].append(match)
        finish()
        result = dict(matches=(title_hits + historical_hits + text_hits)[:limit], total_matches=total, truncated=total > limit,
                      semantics='case-insensitive literal substrings; AND across current title and conversation messages',
                      snippet_semantics='unchanged source slice around the first matching term; at most 240 Unicode code points; zero-based half-open offsets into original message text')
        if include_title_history:
            result.update(semantics='case-insensitive literal substrings; AND across current title, prior local titles and conversation messages',
                          title_history_scope='local archive only; at most three matching prior title records per conversation, newest overrides first then archived original',
                          warning='Prior titles may contain private details deliberately removed from the current display title. No remote titles are queried.')
        if export_sha256 is not None:
            result.update(export_sha256=export_sha256, export_provenance_available=bool(provenance_tables),
                          export_scope='Only message bodies linked by original-export provenance are searched. Current and optional historical titles remain conversation-wide archive metadata, not export-snapshot titles.')
        return result
    finally:
        c.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',required=True); p.add_argument('query'); p.add_argument('--source'); p.add_argument('--limit',type=int,default=20)
    p.add_argument('--include-title-history', action='store_true')
    p.add_argument('--export-sha256', help='restrict message bodies to one original export provenance hash')
    a=p.parse_args()
    try: result=find(a.db,a.query,a.source,a.limit,a.include_title_history,a.export_sha256)
    except (ValueError,OSError,sqlite3.Error) as e: p.exit(1,str(e)+'\n')
    print(json.dumps(result,ensure_ascii=True,indent=2))


if __name__=='__main__': main()
