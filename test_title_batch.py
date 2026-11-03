"""Synthetic batch review pages, advisory duplicates and one-at-a-time apply."""
import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from recap import ingest
from session_workflow import titles
from title_batch import review_queue, select_proposal
from title_proposal import preview, apply_preview


class TitleBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name)/'archive.sqlite'; self.path = Path(self.tmp.name)/'synthetic.jsonl'
        self.records = [dict(conversation_id=cid,message_id=cid+'-u',role=role,timestamp='synthetic',text=text,title=title)
                        for cid,role,text,title in [('a','user','Ｓｙｎｔｈｅｔｉｃ   topic','New chat'),
                                                  ('b','user','synthetic topic','Other old title'),
                                                  ('c','assistant','Assistant only','SYNTHETIC TOPIC'),
                                                  ('d','user','Distinct synthetic topic','Already reviewed')]]
        self.path.write_text(''.join(json.dumps(r)+'\n' for r in self.records))
        ingest(self.db,'demo',self.path)
        titles(self.db,'demo','d','Reviewed synthetic title',0)

    def test_read_only_queue_collision_counts_and_existing_override(self):
        before = self.db.read_bytes(); queue = review_queue(self.db,'demo',2)
        self.assertEqual(self.db.read_bytes(),before); self.assertEqual(queue['next_offset'],2)
        self.assertEqual(queue['total_conversations'],4)
        for item in queue['items']:
            self.assertEqual(item['collisions']['page_proposal_count'],1)
            self.assertEqual(item['collisions']['existing_title_count'],1)
            self.assertEqual(item['collisions']['existing_title_conversations'],['c'])
        second = review_queue(self.db,'demo',2,2)
        self.assertEqual(second['items'][0]['status'],'UNAVAILABLE')
        self.assertEqual(second['items'][0]['reason_code'],'NO_VALID_LOCAL_EXCERPT')
        self.assertNotIn('proposal',second['items'][0]); self.assertIsNone(second['next_offset'])
        self.assertTrue(second['items'][1]['previously_renamed'])
        self.assertEqual(second['items'][1]['current_title'],'Reviewed synthetic title')

    def test_candidate_collision_scope_is_page_only_and_self_excluded(self):
        titles(self.db,'demo','a','Synthetic Topic',0)
        queue = review_queue(self.db,'demo',1)
        collision = queue['items'][0]['collisions']
        self.assertEqual(collision['page_proposal_count'],0)
        self.assertEqual(collision['existing_title_count'],1)
        self.assertEqual(collision['existing_title_conversations'],['c'])
        empty = review_queue(self.db,'missing',20)
        self.assertEqual(empty['items'],[]); self.assertIsNone(empty['next_offset'])

    def test_select_one_preview_apply_then_stale_content_and_revision_guard(self):
        queue = review_queue(self.db,'demo')
        proposal = select_proposal(queue,'a'); reviewed = preview(self.db,proposal)
        apply_preview(self.db,reviewed)
        with self.assertRaises(ValueError): apply_preview(self.db,reviewed)
        # A saved queue can be re-previewed against current title revision, but
        # changed raw content must invalidate its old content hash.
        self.assertGreater(preview(self.db,proposal)['expected_revision'],reviewed['expected_revision'])
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE messages SET text='Changed synthetic content' WHERE conversation_id='a'");connection.commit()
        with self.assertRaisesRegex(ValueError,'snapshot'): preview(self.db,proposal)
        self.assertEqual(titles(self.db,'demo','b')['revision'],0)

    def test_wrong_selection_identity_and_malformed_queue_rejected(self):
        queue = review_queue(self.db,'demo')
        for cid in ('missing','c'):
            with self.assertRaises(ValueError): select_proposal(queue,cid)
        for bad in (None,[],{},dict(queue,items={}),dict(queue,source='other')):
            with self.assertRaises(ValueError): select_proposal(bad,'a')
        duplicate = copy.deepcopy(queue);duplicate['items'].append(duplicate['items'][0])
        with self.assertRaises(ValueError): select_proposal(duplicate,'a')
        selected = select_proposal(queue,'a');selected['title']='Edited copy'
        self.assertNotEqual(queue['items'][0]['proposal']['title'],selected['title'])

    def test_limits_and_missing_db_fail_without_creation(self):
        for limit,offset in ((0,0),(101,0),(True,0),(1,-1),(1,False)):
            with self.assertRaises(ValueError): review_queue(self.db,'demo',limit,offset)
        missing=Path(self.tmp.name)/'missing.sqlite'
        with self.assertRaises(sqlite3.Error):review_queue(missing,'demo')
        self.assertFalse(missing.exists())

    def test_oversized_offset_is_clean_failure_before_database_access(self):
        import title_batch
        with patch.object(title_batch, 'readonly', side_effect=AssertionError('must validate first')):
            with self.assertRaises(ValueError): review_queue(self.db, 'demo', offset=2**63)
        before = self.db.read_bytes()
        result = subprocess.run([sys.executable, 'recap.py', '--db', str(self.db), 'review-titles',
                                 '--source', 'demo', '--offset', str(2**63)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1); self.assertEqual(result.stdout, '')
        self.assertNotIn('Traceback', result.stderr); self.assertIn('9223372036854775807', result.stderr)
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual(review_queue(self.db, 'demo', offset=2**63-1)['items'], [])

    def test_one_database_snapshot_during_concurrent_title_change(self):
        import title_batch
        with closing(sqlite3.connect(self.db)) as connection: connection.execute('PRAGMA journal_mode=WAL')
        original=title_batch._inventory
        def change_after_inventory(connection,*args,**kwargs):
            records=original(connection,*args,**kwargs)
            titles(self.db,'demo','c','Changed collision title',0)
            return records
        with patch.object(title_batch,'_inventory',change_after_inventory):
            queue=review_queue(self.db,'demo',2)
        self.assertEqual(queue['items'][0]['collisions']['existing_title_conversations'],['c'])
        self.assertEqual(review_queue(self.db,'demo',2)['items'][0]['collisions']['existing_title_count'],0)

    def test_collision_samples_bounded_and_cross_source_excluded(self):
        extra=[dict(conversation_id=f'z{i:02}',message_id='m',role='assistant',timestamp='synthetic',text='Synthetic answer',title='synthetic topic') for i in range(14)]
        self.path.write_text(''.join(json.dumps(r)+'\n' for r in extra))
        ingest(self.db,'demo',self.path);ingest(self.db,'other-source',self.path)
        collision=review_queue(self.db,'demo',1)['items'][0]['collisions']
        self.assertEqual(collision['existing_title_count'],15)
        self.assertEqual(len(collision['existing_title_conversations']),10)

    def test_cli_web_and_local_queue_selection_preview_apply(self):
        db=Path(self.tmp.name)/'workflow.sqlite'
        def call(*args,ok=True):
            result=subprocess.run([sys.executable,'recap.py','--db',str(db),*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0 if ok else 1,result.stderr);self.assertNotIn('Traceback',result.stderr)
            return json.loads(result.stdout) if ok else result
        call('import','examples/web-export.json','--format','web','--source','mixed')
        call('import','examples/rollback-session.jsonl','--format','local-codex','--source','mixed')
        before=db.read_bytes();queue=call('review-titles','--source','mixed')
        self.assertEqual(len(queue['items']),2);self.assertEqual(before,db.read_bytes())
        local=next(item for item in queue['items'] if item['conversation']=='synthetic-rollout')
        self.assertEqual(local['proposal']['title'],'Synthetic question discarded')  # explicitly raw, not replay
        saved=Path(self.tmp.name)/'queue.json';saved.write_text(json.dumps(queue))
        call('apply-title',saved,ok=False)
        reviewed=call('preview-title',saved,'--conversation','synthetic-chat')
        saved.write_text(json.dumps(reviewed));call('apply-title',saved)
        self.assertEqual(call('title','--source','mixed','--conversation','synthetic-chat')['display_title'],'Design a synthetic orchard experiment')
        self.assertEqual(call('title','--source','mixed','--conversation','synthetic-rollout')['revision'],0)
