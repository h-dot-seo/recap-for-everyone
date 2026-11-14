"""Explicit identity selection changes the view, never review or collision scope."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes
from recaplib.session_workflow import titles
from recaplib.title_batch import review_queue
from recaplib.title_proposal import snapshot
ROOT=Path(__file__).resolve().parents[1]


class SelectedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'archive.sqlite'
        rows=[dict(conversation_id=cid,message_id=cid+'-m',role='user',timestamp='unknown',title=title,text='Synthetic request '+cid)
              for cid,title in [('a','Old A'),('b','Outside duplicate'),('c','Old C')]]
        ingest_bytes(self.db,'synthetic',(''.join(json.dumps(r)+'\n' for r in rows)).encode())

    def queue(self,**kw):return review_queue(self.db,'synthetic',**kw)

    def proposal(self,cid,title):
        return dict(source='synthetic',conversation=cid,content_sha256=snapshot(self.db,'synthetic',cid)[1],title=title,evidence_message_ids=[cid+'-m'],provider='operator')

    def test_explicit_ids_before_pagination_and_binary_order(self):
        first=self.queue(conversations=['c','a'],limit=1)
        self.assertEqual([i['conversation'] for i in first['items']],['a'])
        self.assertEqual(first['total_conversations'],2);self.assertEqual(first['next_offset'],1)
        self.assertEqual(first['excluded_unselected_conversations'],1)
        second=self.queue(conversations=['c','a'],limit=1,offset=1)
        self.assertEqual([i['conversation'] for i in second['items']],['c'])
        self.assertIsNone(second['next_offset'])

    def test_missing_ids_source_and_default_shape(self):
        missing=self.queue(conversations=['missing'])
        self.assertEqual(missing['items'],[]);self.assertEqual(missing['total_conversations'],0)
        self.assertEqual(missing['selected_conversation_count'],1)
        self.assertNotIn('selected_conversation_count',self.queue())
        self.assertEqual(review_queue(self.db,'different',conversations=['a'])['items'],[])

    def test_invalid_selection_precedes_database_open(self):
        cases=[[],True,'a',['a','a'],[''],[1],['\ud800'],['a']*1001,['x'*(1024*1024+1)]]
        with patch('recaplib.title_batch.readonly',side_effect=AssertionError('validate first')):
            for ids in cases:
                with self.subTest(type=type(ids)),self.assertRaises(ValueError):self.queue(conversations=ids)

    def test_unrenamed_supplied_state_intersection_and_count_partition(self):
        titles(self.db,'synthetic','c','Renamed C',0)
        result=self.queue(conversations=['a','c'],unrenamed_only=True,review_state_filter='open',
                          supplied_proposals=[self.proposal('a','Supplied A')],supplied_only=True)
        self.assertEqual([i['conversation'] for i in result['items']],['a'])
        self.assertEqual(result['source_total_conversations'],sum(result[k] for k in ['excluded_renamed_conversations','excluded_unselected_conversations','excluded_unsupplied_conversations','excluded_review_state_conversations','total_conversations']))
        empty=self.queue(conversations=['a'],supplied_proposals=[],supplied_only=True)
        self.assertEqual(empty['excluded_unsupplied_conversations'],1)
        self.assertEqual(empty['excluded_unselected_conversations'],2)

    def test_existing_title_collisions_outside_selection_remain_visible(self):
        result=self.queue(conversations=['a'],supplied_proposals=[self.proposal('a','Outside duplicate')])
        collision=result['items'][0]['collisions']
        self.assertEqual(collision['existing_title_count'],1)
        self.assertEqual(collision['existing_title_conversations'],['b'])
        self.assertEqual(result['execution_status'],'NOT_EXECUTED')

    def test_excluded_bodies_are_not_loaded(self):
        from recaplib.archive import readonly
        reader=readonly(self.db);queries=[]
        reader.set_trace_callback(queries.append)
        with patch('recaplib.title_batch.readonly',return_value=reader):self.queue(conversations=['a'],review_state_filter='open')
        body_queries=[q for q in queries if 'SELECT message_id,role,text' in q]
        self.assertTrue(body_queries)
        self.assertTrue(all("conversation_id='a'" in q for q in body_queries))

    def test_cli_output_is_read_only_and_matches_api(self):
        before=self.db.read_bytes()
        run=subprocess.run([sys.executable,str(ROOT/'recap.py'),'--db',str(self.db),'review-titles','--source','synthetic','--conversation','c','--conversation','a'],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(run.stdout),self.queue(conversations=['c','a']))
        self.assertEqual(self.db.read_bytes(),before)

    def test_documented_selection_walkthrough(self):
        import re
        import shlex
        block=re.search(r'```sh\n(.*?)```',(ROOT/'docs/SELECTED_TITLE_REVIEW.md').read_text(),re.S).group(1)
        output=self.root/'selection space'
        for line in block.strip().splitlines():
            args=[part.replace('OUTPUT',str(output)) for part in shlex.split(line)]
            if args[0]=='mkdir':Path(args[1]).mkdir();continue
            args[0]=sys.executable
            run=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
        queue=json.loads((output/'selected.json').read_text())
        self.assertEqual(queue['items'][0]['conversation'],'changed')
        self.assertEqual(queue['total_conversations'],2);self.assertEqual(queue['next_offset'],1)

    def test_saved_selected_queue_renders_and_previews(self):
        import copy
        from recaplib.render_queue import render_queue, validate_queue
        from recaplib.title_batch import select_proposal
        from recaplib.title_proposal import preview
        queue=self.queue(conversations=['a'])
        file=self.root/'selected.json';file.write_text(json.dumps(queue),encoding='utf-8')
        render_queue(file,self.root/'selected.html')
        self.assertIn('selection_scope',(self.root/'selected.html').read_text())
        proposal=select_proposal(queue,'a')
        preview(self.db,proposal,proposal['title'])
        for key in ('selected_conversation_count','excluded_unselected_conversations','selection_scope'):
            invalid=copy.deepcopy(queue);del invalid[key]
            with self.assertRaises(ValueError):validate_queue(invalid)
        invalid=copy.deepcopy(queue);invalid['excluded_unselected_conversations']=999
        with self.assertRaises(ValueError):validate_queue(invalid)
