"""Skip only off-page excerpt construction, not matching or database reads."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes
from recaplib import conversation_search as search
from recaplib.session_workflow import titles


class ExcerptBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'synthetic.sqlite'
        rows=[]
        for rank in range(3):
            for i in range(4):
                cid=f'{rank}-{i}'
                for j in range(3):
                    rows.append(dict(conversation_id=cid,message_id=str(j),role='user',timestamp='2026-01-01',title='orchard' if rank<2 else 'other',text='Straße e\u0301 '+('orchard fruit' if j%2 else 'orchard seed')))
        ingest_bytes(self.db,'synthetic',('\n'.join(json.dumps(r) for r in rows)+'\n').encode())
        for i in range(4):titles(self.db,'synthetic',f'1-{i}','new title',0)

    def observed(self,**kwargs):
        with patch.object(search,'_matching_excerpt',wraps=search._matching_excerpt) as helper:
            result=search.find(self.db,'orchard',include_title_history=True,**kwargs)
        return result,helper.call_count

    def test_each_page_matches_full_evidence_and_counts_with_fewer_excerpts(self):
        before=self.db.read_bytes();full,full_calls=self.observed(limit=1000)
        self.assertEqual(full_calls,36);self.assertEqual(full['total_matches'],12)
        cursor=None;items=[];calls=[]
        while True:
            result,count=self.observed(limit=1,cursor=cursor);calls.append(count)
            self.assertEqual(result['total_matches'],12);items+=result['matches']
            cursor=result['next_cursor']
            if cursor is None:break
        self.assertEqual(items,full['matches']);self.assertEqual(calls[0],9)
        self.assertEqual(calls[-1],3);self.assertTrue(all(n<full_calls for n in calls))
        self.assertEqual(self.db.read_bytes(),before)

    def test_unicode_and_multi_term_samples_keep_source_offsets(self):
        for canonical in (False,True):
            for query in ('strasse orchard','fruit seed','é orchard' if canonical else 'e\u0301 orchard'):
                whole=search.find(self.db,query,limit=1000,canonical_unicode=canonical)
                first=search.find(self.db,query,limit=1,canonical_unicode=canonical)
                self.assertEqual(first['matches'],whole['matches'][:1]);self.assertEqual(first['total_matches'],whole['total_matches'])
                for match in first['matches'][0]['message_matches']:
                    self.assertTrue(match['first_match']['fully_visible'])

    def test_miss_and_title_only_still_scan_full_match_counts(self):
        with patch.object(search,'_matching_excerpt',wraps=search._matching_excerpt) as helper:
            miss=search.find(self.db,'absent',limit=1)
            title=search.find(self.db,'new title',limit=1)
        self.assertEqual(miss['total_matches'],0);self.assertEqual(title['total_matches'],4)
        self.assertEqual(title['matches'][0]['message_matches'],[]);self.assertEqual(helper.call_count,0)

    def test_invalid_limit_still_rejects_before_database(self):
        with patch.object(search,'readonly',side_effect=AssertionError('no DB')):
            with self.assertRaises(ValueError):search.find(self.db,'orchard',limit=0)

    def test_hidden_provenance_query_errors_are_not_suppressed(self):
        # Supply synthetic provenance in a separate fixture via the regular API.
        db=Path(self.tmp.name)/'provenance.sqlite';rows=[];origins=[]
        for cid in ('a','b'):
            rows.append(dict(conversation_id=cid,message_id='m',role='user',timestamp='synthetic',text='orchard'))
            origins.append(dict(conversation_id=cid,message_id='m',origin_sha256='a'*64,origin_locator='m',parent_id=None))
        ingest_bytes(db,'synthetic',('\n'.join(json.dumps(r) for r in rows)+'\n').encode(),provenance=origins)
        real=search._matching_export_provenance;seen=[]
        def query(conn,tables,source,cid,*args):
            seen.append(cid)
            if cid=='b':raise sqlite3.OperationalError('synthetic hidden query fault')
            return real(conn,tables,source,cid,*args)
        with patch.object(search,'_matching_export_provenance',query):
            with self.assertRaisesRegex(sqlite3.OperationalError,'synthetic hidden query fault'):
                search.find(db,'orchard',limit=1,export_sha256='a'*64)
        self.assertEqual(seen,['a','b'])

    def test_small_page_keeps_the_same_sql_scan(self):
        real=search.readonly;traces=[];connections=[]
        for limit in (1,1000):
            trace=[]
            def opened(*args,**kwargs):
                conn=real(*args,**kwargs);conn.set_trace_callback(trace.append);connections.append(conn);return conn
            with patch.object(search,'readonly',opened):search.find(self.db,'orchard',limit=limit,include_title_history=True)
            traces.append(trace)
        self.assertEqual(traces[0],traces[1])
        for conn in connections:
            with self.assertRaises(sqlite3.ProgrammingError):conn.execute('SELECT 1')
