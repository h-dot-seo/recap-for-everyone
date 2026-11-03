"""Read-only conversation search across current display titles and message text."""
import argparse
import json
import sqlite3
from recap import readonly


def find(db, query, source=None, limit=20):
    if not isinstance(query, str) or type(limit) is not int:
        raise ValueError('query must be text and limit must be an integer')
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
        sql = 'SELECT * FROM messages' 
        params = ()
        if source is not None:
            sql += ' WHERE source_id=?'; params = (source,)
        sql += ' ORDER BY source_id COLLATE BINARY,conversation_id COLLATE BINARY,message_pk'
        # Keep only the current conversation's term flags and first three hits.
        # Two bounded buckets preserve title-first ranking without storing all hits.
        title_hits, text_hits = [], []
        total = 0
        item, key, found = None, None, None

        def finish():
            nonlocal total
            if item is None or not all(found):
                return
            total += 1
            bucket = title_hits if item['matched_title'] else text_hits
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
            item['message_count'] += 1
            text = row['text'].casefold()
            matches = [term in text for term in terms]
            found = [previous or matched for previous, matched in zip(found, matches)]
            if any(matches) and len(item['message_matches']) < 3:
                item['message_matches'].append(dict(message_id=row['message_id'], role=row['role'],
                    snippet=row['text'][:240], source_sha256=row['source_sha256'], source_line=row['source_line']))
        finish()
        return dict(matches=(title_hits + text_hits)[:limit], total_matches=total, truncated=total > limit,
                    semantics='case-insensitive literal substrings; AND across current title and conversation messages')
    finally:
        c.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',required=True); p.add_argument('query'); p.add_argument('--source'); p.add_argument('--limit',type=int,default=20)
    a=p.parse_args()
    try: result=find(a.db,a.query,a.source,a.limit)
    except (ValueError,OSError,sqlite3.Error) as e: p.exit(1,str(e)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
