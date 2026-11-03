"""Read-only conversation search across current display titles and message text."""
import argparse
import json
import sqlite3
from recap import readonly


def find(db, query, source=None, limit=20, include_title_history=False):
    if not isinstance(query, str) or type(limit) is not int:
        raise ValueError('query must be text and limit must be an integer')
    if type(include_title_history) is not bool:
        raise ValueError('include_title_history must be boolean')
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
        params = ()
        if source is not None:
            sql += ' WHERE source_id=?'; params = (source,)
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
                # Merge two ordered cursors rather than scanning title history
                # once per conversation or retaining all overrides in Python.
                while current_title is not None and (current_title['source'], current_title['conversation']) < key:
                    current_title = next(history_rows, None)
                if current_title is not None and (current_title['source'], current_title['conversation']) == key:
                    title, revision = current_title['title'], current_title['id']
                else:
                    title, revision = row['title'], 0
                folded_title = title.casefold()
                found = [term in folded_title for term in terms]
                item = dict(source_id=key[0], conversation_id=key[1], original_title=row['title'],
                            display_title=title, title_revision=revision, message_count=0,
                            matched_title=any(found), message_matches=[])
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
                        match_prior(row['title'], 0, 'archived_original_title')
            item['message_count'] += 1
            text = row['text'].casefold()
            matches = [term in text for term in terms]
            found = [previous or matched for previous, matched in zip(found, matches)]
            if any(matches) and len(item['message_matches']) < 3:
                item['message_matches'].append(dict(message_id=row['message_id'], role=row['role'],
                    snippet=row['text'][:240], source_sha256=row['source_sha256'], source_line=row['source_line']))
        finish()
        result = dict(matches=(title_hits + historical_hits + text_hits)[:limit], total_matches=total, truncated=total > limit,
                      semantics='case-insensitive literal substrings; AND across current title and conversation messages')
        if include_title_history:
            result.update(semantics='case-insensitive literal substrings; AND across current title, prior local titles and conversation messages',
                          title_history_scope='local archive only; at most three matching prior title records per conversation, newest overrides first then archived original',
                          warning='Prior titles may contain private details deliberately removed from the current display title. No remote titles are queried.')
        return result
    finally:
        c.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',required=True); p.add_argument('query'); p.add_argument('--source'); p.add_argument('--limit',type=int,default=20)
    p.add_argument('--include-title-history', action='store_true')
    a=p.parse_args()
    try: result=find(a.db,a.query,a.source,a.limit,a.include_title_history)
    except (ValueError,OSError,sqlite3.Error) as e: p.exit(1,str(e)+'\n')
    print(json.dumps(result,ensure_ascii=a.include_title_history,indent=2))


if __name__=='__main__': main()
