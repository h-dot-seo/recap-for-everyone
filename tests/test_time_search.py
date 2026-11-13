"""Synthetic UTC search windows preserve default and cursor contracts."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes
from recaplib.conversation_search import find, _cursor_scope
from recaplib.timestamps import RULE

ROOT = Path(__file__).resolve().parents[1]


class TimeSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/'archive.sqlite'
        rows = [('a','2025-12-31T23:59:59Z','user','outside'),
                ('a','2026-01-01T09:00:00+09:00','assistant','inside'),
                ('a','unknown','user','unparsed'),
                ('b','1767311999.999999999','user','inside'),
                ('c','2026-01-02T00:00:00Z','user','outside'),
                ('d','unknown','user','inside'),
                ('e','20260101','user','inside')]
        content=[dict(conversation_id=c,message_id=str(i),role=role,timestamp=t,
                      title='shared original' if i==0 else 'shared later',text=text)
                 for i,(c,t,role,text) in enumerate(rows)]
        ingest_bytes(self.db,'synthetic', ('\n'.join(map(json.dumps,content))+'\n').encode())

    def window(self,query='inside',**kw):
        return find(self.db,query,from_date='2026-01-01',until_date='2026-01-01',**kw)

    def test_message_filter_boundary_offset_epoch_and_title(self):
        result=self.window(); self.assertEqual([x['conversation_id'] for x in result['matches']],['a','b'])
        self.assertEqual([x['message_count'] for x in result['matches']],[1,1])
        self.assertEqual(result['matches'][0]['original_title'],'shared original')
        self.assertEqual(self.window('outside')['total_matches'],0)
        self.assertEqual(self.window('unparsed')['total_matches'],0)
        self.assertEqual(self.window('original')['total_matches'],1)
        self.assertEqual(result['timestamp_interpretation']['rule'],RULE)
        self.assertEqual([result['timestamp_interpretation'][k] for k in ('parsed_iso','parsed_epoch_seconds','unparsed')],[3,2,2])

    def test_role_and_window_intersection_and_coverage(self):
        result=self.window(text_role='user')
        self.assertEqual([x['conversation_id'] for x in result['matches']],['b'])
        self.assertEqual(result['timestamp_interpretation']['parsed_iso'],2)
        self.assertIn('requested role',result['matches'][0]['message_count_scope'])
        self.assertEqual(self.window(export_sha256='0'*64)['total_matches'],0)

    def test_one_sided_windows_and_date_looking_seconds(self):
        self.assertEqual(find(self.db,'inside',until_date='1970-12-31')['matches'][0]['conversation_id'],'e')
        self.assertEqual(find(self.db,'outside',from_date='2026-01-02')['matches'][0]['conversation_id'],'c')
        self.assertEqual(find(self.db,'inside',from_date='9999-12-31',until_date='9999-12-31')['total_matches'],0)

    def test_validation_precedes_database_access(self):
        with patch('recaplib.conversation_search.readonly') as opening:
            for kw in ({'from_date':'2026-02-30'},{'until_date':'2026-1-01'},
                       {'from_date':'2026-01-02','until_date':'2026-01-01'}, {'from_date':True}):
                with self.subTest(kw=kw),self.assertRaises(ValueError): find('absent','inside',**kw)
            opening.assert_not_called()

    def test_window_cursor_rejects_changed_bounds_or_no_window(self):
        first=self.window(limit=1); token=first['next_cursor']; self.assertIsNotNone(token)
        second=self.window(limit=1,cursor=token)
        self.assertEqual(second['matches'][0]['conversation_id'],'b')
        for kw in ({}, {'from_date':'2026-01-01'}, {'until_date':'2026-01-01'},
                   {'from_date':'2026-01-01','until_date':'2026-01-02'}):
            with self.subTest(kw=kw),self.assertRaises(ValueError): find(self.db,'inside',cursor=token,**kw)

    def test_legacy_cursor_scope_and_output_unchanged(self):
        value=dict(protocol='recap.find.cursor.v1',terms=['inside'],source=None,
                   include_title_history=False,export_sha256=None)
        expected=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode('ascii')).hexdigest()
        self.assertEqual(_cursor_scope(['inside'],None,False,None),expected)
        result=find(self.db,'inside',limit=1)
        self.assertNotIn('timestamp_interpretation',result)
        self.assertNotIn('message_count_scope',result['matches'][0])
        self.assertEqual(find(self.db,'inside',cursor=result['next_cursor'])['skipped_matches'],1)

    def test_read_only_and_cli_parity(self):
        before=self.db.read_bytes()
        args=['--db',str(self.db),'find','inside','--from','2026-01-01','--until','2026-01-01']
        unified=subprocess.run([sys.executable,str(ROOT/'recap.py'),*args],capture_output=True,text=True,check=True)
        standalone=subprocess.run([sys.executable,str(ROOT/'conversation_search.py'),'--db',str(self.db),*args[3:]],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(unified.stdout),json.loads(standalone.stdout))
        self.assertEqual(self.db.read_bytes(),before)

    def test_new_window_membership_invalidates_cursor(self):
        token=self.window(limit=1)['next_cursor']
        row=dict(conversation_id='new',message_id='fresh',role='user',timestamp='2026-01-01T12:00:00Z',title='new',text='inside')
        ingest_bytes(self.db,'synthetic',(json.dumps(row)+'\n').encode())
        with self.assertRaisesRegex(ValueError,'order changed'):
            self.window(cursor=token)

    def test_positive_provenance_role_and_window_intersection(self):
        from recap import ingest
        rows=[dict(conversation_id='linked',message_id=str(i),role=role,timestamp=time,title='linked',text='needle')
              for i,(role,time) in enumerate([('user','2026-01-01T00:00:00Z'),('assistant','2026-01-01T00:00:00Z'),('user','2026-01-02T00:00:00Z')])]
        path=Path(self.temp.name)/'linked.jsonl'
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
        provenance=[dict(**row,origin_sha256='a'*64,origin_locator='synthetic:'+str(i),parent_id=None) for i,row in enumerate(rows)]
        ingest(self.db,'linked-source',path,provenance=provenance)
        result=self.window('needle',text_role='user',export_sha256='a'*64)
        self.assertEqual(result['total_matches'],1)
        self.assertEqual(result['matches'][0]['message_count'],1)
        self.assertEqual(result['matches'][0]['message_matches'][0]['message_id'],'0')
        self.assertEqual(result['timestamp_interpretation']['parsed_iso'],2)
