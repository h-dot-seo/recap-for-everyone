"""24+ synthetic sessions: revisit deferred work using current effective state."""
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
from recaplib.session_workflow import import_export,titles
from recaplib.title_batch import review_queue
from recaplib.title_review_state import review_state
from tests.test_title_queue_workflow import synthetic_exports


class ReviewStateFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name);self.db=self.directory/'archive.sqlite'
        self.web,self.local=synthetic_exports(self.directory)
        import_export(self.db,'demo',self.web,'web');import_export(self.db,'demo',self.local,'local-codex')

    def decide(self,cid,state):
        lease=review_state(self.db,'demo',cid)
        return review_state(self.db,'demo',cid,state,lease['state_revision'],lease['expected_title_revision'],lease['expected_content_sha256'])

    def queue(self,state,**kwargs):return review_queue(self.db,'demo',review_state_filter=state,**kwargs)

    def test_defer_skip_paginate_and_reopen_in_twenty_four_session_flow(self):
        raw=[self.web.read_bytes(),self.local.read_bytes()]
        for cid in ('local-00','web-00'):self.decide(cid,'skipped')
        for cid in ('local-01','web-01','web-02'):self.decide(cid,'deferred')
        before=self.db.read_bytes()
        queue=self.queue('open',limit=100)
        self.assertEqual(queue['total_conversations'],19);self.assertEqual(queue['source_total_conversations'],24)
        self.assertEqual(queue['excluded_review_state_conversations'],5);self.assertEqual(queue['excluded_renamed_conversations'],0)
        self.assertFalse(any(i['review_state']['state']!='open' for i in queue['items']))
        first=self.queue('deferred',limit=2);second=self.queue('deferred',limit=2,offset=first['next_offset'])
        self.assertEqual([i['conversation'] for i in first['items']+second['items']],['local-01','web-01','web-02'])
        self.assertIsNone(second['next_offset']);self.assertEqual(before,self.db.read_bytes())
        self.decide('web-01','open')
        self.assertEqual(self.queue('open')['total_conversations'],20)
        self.assertEqual(self.queue('deferred')['total_conversations'],2)
        self.assertEqual(raw,[self.web.read_bytes(),self.local.read_bytes()])
        self.assertEqual(titles(self.db,'demo','web-01')['revision'],0)

    def test_changed_content_or_title_moves_stale_decisions_to_open(self):
        self.decide('local-00','skipped');self.decide('local-01','deferred')
        titles(self.db,'demo','local-00','Changed synthetic title',0)
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE messages SET text='New synthetic text' WHERE conversation_id='local-01'");c.commit()
        open_queue=self.queue('open',limit=100)
        for cid in ('local-00','local-01'):
            item=next(i for i in open_queue['items'] if i['conversation']==cid)
            self.assertTrue(item['review_state']['stale_decision'])
        self.assertEqual(self.queue('deferred')['total_conversations'],0)
        self.assertEqual(self.queue('skipped')['total_conversations'],0)
        combined=self.queue('open',limit=100,unrenamed_only=True)
        self.assertEqual(combined['total_conversations'],23)
        self.assertEqual(combined['excluded_renamed_conversations'],1)
        self.assertEqual(combined['excluded_review_state_conversations'],0)

    def test_current_collision_titles_include_other_states_and_renamed(self):
        titles(self.db,'demo','local-00','Repeated synthetic planning topic',0)
        self.decide('local-00','skipped')
        candidate=next(i for i in self.queue('open',limit=100,unrenamed_only=True)['items'] if i['conversation']=='local-01')
        self.assertEqual(candidate['collisions']['existing_title_conversations'],['local-00'])
        self.assertEqual(candidate['collisions']['existing_title_count'],1)

    def test_chunk_boundary_exact_counts_and_offset_after_filtering(self):
        path=self.directory/'more.jsonl'
        path.write_text(''.join(json.dumps(dict(conversation_id=f'z-{i:03}',message_id='u',role='user',timestamp='synthetic',text='Synthetic topic '+str(i),title='New chat'))+'\n' for i in range(181)))
        ingest(self.db,'demo',path)
        self.decide('z-100','deferred');self.decide('z-180','deferred')
        page=self.queue('deferred',limit=1,offset=1)
        self.assertEqual(page['source_total_conversations'],205);self.assertEqual(page['total_conversations'],2)
        self.assertEqual(page['items'][0]['conversation'],'z-180');self.assertIsNone(page['next_offset'])

    def test_snapshot_during_concurrent_reopen_and_invalid_filter_before_db(self):
        from recaplib import title_batch
        self.decide('local-00','deferred')
        with closing(sqlite3.connect(self.db)) as c:c.execute('PRAGMA journal_mode=WAL')
        original=title_batch._inventory;changed=[]
        def reopen_after_inventory(connection,*args,**kwargs):
            records=original(connection,*args,**kwargs)
            if not changed:self.decide('local-00','open');changed.append(True)
            return records
        with patch.object(title_batch,'_inventory',reopen_after_inventory):queue=self.queue('deferred')
        self.assertEqual(queue['total_conversations'],1)
        self.assertEqual(queue['items'][0]['review_state']['state'],'deferred')
        self.assertEqual(self.queue('deferred')['total_conversations'],0)
        with patch.object(title_batch,'readonly',side_effect=AssertionError('must validate first')):
            for state in ([],True,'all','done'):
                with self.assertRaises(ValueError):self.queue(state)

    def test_cli_revisit_deferred_then_explicit_reopen_without_title_change(self):
        self.decide('web-04','deferred')
        def call(*args):
            result=subprocess.run([sys.executable,'recap.py','--db',str(self.db),*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
        queue=call('review-titles','--source','demo','--state','deferred')
        self.assertEqual([i['conversation'] for i in queue['items']],['web-04'])
        lease=queue['items'][0]['review_state']
        call('review-state','--source','demo','--conversation','web-04','--set','open',
             '--expected-state-revision',lease['state_revision'],'--expected-title-revision',lease['expected_title_revision'],
             '--expected-content-sha256',lease['expected_content_sha256'])
        self.assertEqual(call('review-titles','--source','demo','--state','deferred')['total_conversations'],0)
        self.assertEqual(call('find','invented','--source','demo')['total_matches'],1)
        self.assertEqual(call('title','--source','demo','--conversation','web-04')['revision'],0)

    def test_missing_history_means_open_and_unknown_source_stays_empty(self):
        self.assertEqual(self.queue('open',limit=100)['total_conversations'],24)
        self.assertEqual(self.queue('skipped')['total_conversations'],0)
        self.assertEqual(review_queue(self.db,'missing',review_state_filter='open')['items'],[])
        self.assertEqual(self.queue('open',offset=2**63-1)['items'],[])
