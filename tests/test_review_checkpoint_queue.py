"""A private snapshot cutoff is a view, never a decision or collision scope."""
import json
from contextlib import closing
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes
from recaplib.session_workflow import titles
from recaplib.title_proposal import snapshot
from recaplib.title_batch import review_queue
from recaplib.review_checkpoint import declare_review_checkpoint
from recaplib.render_queue import validate_queue, render_queue

ROOT = Path(__file__).resolve().parents[1]

class CheckpointQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.db = self.root/'archive.sqlite'; self.cp = self.root/'checkpoint.json'
        self.add('a', 'a1'); self.add('b', 'b1'); self.add('c', 'c1')

    def add(self, cid, mid):
        row = dict(conversation_id=cid, message_id=mid, role='user', timestamp='unknown',
                   title='Synthetic '+cid, text='Fictional request '+mid)
        ingest_bytes(self.db, 'synthetic', (json.dumps(row)+'\n').encode())

    def declare(self):
        declare_review_checkpoint(self.db, 'synthetic', self.cp, '2026-01-01')

    def queue(self, **kw):
        return review_queue(self.db, 'synthetic', checkpoint=self.cp, **kw)

    def proposal(self, cid):
        return dict(source='synthetic', conversation=cid, content_sha256=snapshot(self.db,'synthetic',cid)[1],
                    title='Synthetic b', evidence_message_ids=[cid+'1'], provider='operator')

    def test_unchanged_default_and_new_content_title_counts(self):
        before = review_queue(self.db,'synthetic'); self.declare()
        self.assertEqual(before, review_queue(self.db,'synthetic'))
        self.assertEqual(self.queue()['total_conversations'],0)
        self.add('a','a2'); titles(self.db,'synthetic','a','Renamed A',0)
        titles(self.db,'synthetic','b','Renamed B',0); self.add('d','d1')
        result=self.queue(limit=2)
        self.assertEqual([i['conversation'] for i in result['items']],['a','b'])
        self.assertEqual(result['next_offset'],2)
        self.assertEqual([i['conversation'] for i in self.queue(offset=2)['items']],['d'])
        c=result['checkpoint_comparison']
        self.assertEqual([c[k] for k in ('new','changed_content','changed_title','unchanged','missing_from_archive')],[1,1,2,1,0])
        self.assertEqual(result['excluded_checkpoint_conversations'],1)
        validate_queue(result)

    def test_previously_renamed_then_grown_visible_without_unrenamed(self):
        titles(self.db,'synthetic','a','Prior A',0); self.declare(); self.add('a','a2')
        self.assertEqual([x['conversation'] for x in self.queue()['items']],['a'])
        q=self.queue(unrenamed_only=True)
        self.assertEqual(q['items'],[]); self.assertEqual(q['excluded_renamed_conversations'],1)
        self.assertEqual(q['excluded_checkpoint_conversations'],2)
        self.assertEqual(q['checkpoint_comparison']['changed_content'],1) # whole source, not filtered

    def test_intersection_partition_and_global_collisions(self):
        self.declare(); self.add('a','a2'); self.add('c','c2'); self.add('d','d1')
        q=self.queue(conversations=['a','c'],supplied_proposals=[self.proposal('a')],supplied_only=True,review_state_filter='open')
        self.assertEqual([x['conversation'] for x in q['items']],['a'])
        self.assertEqual(q['items'][0]['collisions']['existing_title_conversations'],['b'])
        keys=['excluded_renamed_conversations','excluded_checkpoint_conversations','excluded_unselected_conversations','excluded_unsupplied_conversations','excluded_review_state_conversations','total_conversations']
        self.assertEqual(sum(q[k] for k in keys),q['source_total_conversations'])
        validate_queue(q)

    def test_missing_other_source_and_invalid_before_database(self):
        self.declare()
        with closing(sqlite3.connect(self.db)) as con:
            with con:
                con.execute("DELETE FROM messages WHERE conversation_id='b'")
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")
        self.assertEqual(self.queue()['checkpoint_comparison']['missing_from_archive'],1)
        with patch('recaplib.title_batch.readonly',side_effect=AssertionError('not opened')):
            with self.assertRaises(ValueError):review_queue(self.db,'other',checkpoint=self.cp)
            self.cp.write_text('{"private":"not a checkpoint"}')
            with self.assertRaises(ValueError):self.queue()

    def test_single_snapshot_and_immutable_database(self):
        self.declare(); self.add('a','a2'); before=self.db.read_bytes()
        from recaplib.archive import readonly
        traces=[]
        def traced(db):
            con=readonly(db); con.set_trace_callback(traces.append); return con
        with patch('recaplib.title_batch.readonly',side_effect=traced) as opened:self.queue()
        self.assertEqual(opened.call_count,1); self.assertEqual(traces.count('BEGIN'),1)
        self.assertEqual(before,self.db.read_bytes())

    def test_saved_queue_render_and_preview(self):
        self.declare(); self.add('a','a2')
        q=self.queue(); path=self.root/'queue.json';path.write_text(json.dumps(q))
        rendered=render_queue(path,self.root/'queue.html')
        self.assertTrue((self.root/'queue.html').is_file())
        p=subprocess.run([sys.executable,str(ROOT/'recap.py'),'--db',str(self.db),'preview-title',str(path),'--conversation','a'],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['proposal']['conversation'],'a')
        q['excluded_checkpoint_conversations']+=1
        with self.assertRaises(ValueError):validate_queue(q)

    def test_declaration_cli_id_free_receipt_and_text(self):
        p=subprocess.run([sys.executable,str(ROOT/'recap.py'),'--db',str(self.db),'declare-review-checkpoint','--source','synthetic','--output',str(self.cp)],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        receipt=json.loads(p.stdout)
        self.assertNotIn('source',receipt);self.assertNotIn('entries',receipt)
        p=subprocess.run([sys.executable,str(ROOT/'recap.py'),'--db',str(self.db),'declare-review-checkpoint','--source','synthetic','--output',str(self.root/'second.json'),'--text'],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr); self.assertIn(b'Review view checkpoint',p.stdout)

    def test_documented_workflow(self):
        guide=(ROOT/'docs/REVIEW_CHECKPOINT.md').read_text()
        blocks=guide.split('```sh\n')[1:];self.assertEqual(len(blocks),1)
        results=[]
        for line in blocks[0].split('```',1)[0].strip().splitlines():
            args=[a.replace('OUTPUT',str(self.root)) for a in shlex.split(line)]
            self.assertEqual(args[0],'python');args[0]=sys.executable
            p=subprocess.run(args,cwd=ROOT,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr); results.append(json.loads(p.stdout))
        self.assertEqual(results[-1]['checkpoint_comparison']['new'],6)
        self.assertEqual(results[-1]['total_conversations'],6)
