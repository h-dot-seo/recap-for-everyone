"""Read-only conversation search across current display titles and message text."""
import argparse
import json
import sqlite3
from recap import readonly


def find(db, query, source=None, limit=20):
    terms=query.casefold().split()
    if not terms or len(terms)>20 or not 1 <= limit <= 1000:
        raise ValueError('provide 1..20 search terms and limit 1..1000')
    c=readonly(db)
    try:
        # One read transaction keeps title history and message rows consistent.
        c.execute('BEGIN')
        history={}
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='title_history'").fetchone():
            for row in c.execute('SELECT source,conversation,title,id FROM title_history ORDER BY id'):
                history[(row['source'],row['conversation'])]=(row['title'],row['id'])
        grouped={}
        sql='SELECT * FROM messages'
        params=()
        if source is not None:
            sql+=' WHERE source_id=?'; params=(source,)
        sql+=' ORDER BY source_id,conversation_id,message_pk'
        for row in c.execute(sql,params):
            key=(row['source_id'],row['conversation_id'])
            item=grouped.setdefault(key,dict(source_id=key[0],conversation_id=key[1],
                original_title=row['title'],display_title=history.get(key,(row['title'],0))[0],
                title_revision=history.get(key,('',0))[1],message_count=0,_texts=[],_rows=[]))
            item['message_count']+=1
            item['_texts'].append(row['text'].casefold())
            item['_rows'].append(row)
        results=[]
        for item in grouped.values():
            title=item['display_title'].casefold()
            text='\n'.join(item['_texts'])
            if not all(term in title or term in text for term in terms):
                continue
            item['matched_title']=any(term in title for term in terms)
            item['message_matches']=[dict(message_id=r['message_id'],role=r['role'],
                snippet=r['text'][:240],source_sha256=r['source_sha256'],source_line=r['source_line'])
                for r in item['_rows'] if any(term in r['text'].casefold() for term in terms)][:3]
            del item['_texts']; del item['_rows']
            results.append(item)
        results.sort(key=lambda r:(not r['matched_title'],r['source_id'],r['conversation_id']))
        return dict(matches=results[:limit],total_matches=len(results),truncated=len(results)>limit,
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
