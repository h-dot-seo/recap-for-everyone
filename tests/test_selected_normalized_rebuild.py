"""Explicit future replay plan, unchanged manifest generations and retained bytes."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from recaplib import archive as a,rebuild,recovery
from tests import test_selected_normalized_ingest as selected
from tests import test_streamed_ingest as prior


class SelectedRebuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.objects=self.root/'objects';self.objects.mkdir();self.live=self.root/'live.sqlite';self.raw=b'\n'+selected.encoded(selected.fixture())
        self.digest=hashlib.sha256(self.raw).hexdigest();(self.objects/self.digest).write_bytes(self.raw)

    def step(self,conversation,digest=None):
        return dict(source='synthetic',kind='normalized',object_sha256=digest or self.digest,label=None,conversation=conversation,newline='lf')

    def run_plan(self,version,steps,label='recap.rebuild-plan.v2',suffix=''):
        manifest=self.root/f'manifest{version}{suffix}.json';plan=self.root/f'plan{version}{suffix}.json';db=self.root/f'rebuilt{version}{suffix}.sqlite';out=self.root/f'receipt{version}{suffix}.json'
        recovery.declare_recovery(self.live,manifest,'2026-11-15',manifest_version=version)
        plan.write_text(json.dumps(dict(schema=label,steps=steps)))
        return rebuild.rebuild_archive(manifest,plan,self.objects,db,out),db,out

    def test_partial_replay_three_manifest_versions_and_receipt_scope(self):
        a.ingest_bytes(self.live,'synthetic',self.raw,conversation='b');original=self.live.read_bytes()
        for v in (1,2,3):
            r,db,out=self.run_plan(v,[self.step('b')])
            self.assertEqual(r['status'],rebuild.PASSED,r);self.assertEqual(prior.tables(db),prior.tables(self.live))
            self.assertEqual(r['plan']['schema'],'recap.rebuild-plan.v2');self.assertEqual(r['steps'][0]['conversation'],'b')
            self.assertEqual(r['steps'][0]['selection']['selected_messages'],2)
            self.assertEqual((r['steps'][0]['records'],r['steps'][0]['inserted']),(4,2))
            if v>=2:self.assertFalse(r['full_archive_restored'])
            self.assertEqual(json.loads(out.read_bytes())['steps'],r['steps'])
        self.assertEqual(self.live.read_bytes(),original);self.assertFalse(list(self.root.glob('.recap-*')))

    def test_disjoint_and_repeated_steps_then_whole_keep_full_artifact(self):
        for c in ('a','a','b'):a.ingest_bytes(self.live,'synthetic',self.raw,conversation=c)
        r,db,_=self.run_plan(3,[self.step(c) for c in ('a','a','b',None)])
        self.assertEqual(r['status'],rebuild.PASSED,r)
        self.assertEqual([x['inserted'] for x in r['steps']],[2,0,2,0])
        self.assertTrue(all(x['records']==4 for x in r['steps']));self.assertEqual(prior.tables(db),prior.tables(self.live))

    def test_v1_stays_null_only_and_whole_replay_fails_partial_manifest(self):
        a.ingest_bytes(self.live,'synthetic',self.raw,conversation='a')
        with self.assertRaises(ValueError):self.run_plan(1,[self.step('a')],label='recap.rebuild-plan.v1')
        r,db,_=self.run_plan(1,[self.step(None)],label='recap.rebuild-plan.v1',suffix='whole')
        self.assertEqual(r['status'],rebuild.FAILED);self.assertFalse(db.exists());self.assertNotIn('schema',r['plan'])

    def test_missing_selection_fails_without_database_publication(self):
        a.ingest_bytes(self.live,'synthetic',self.raw,conversation='a')
        r,db,out=self.run_plan(3,[self.step('missing')])
        self.assertEqual(r['status'],rebuild.FAILED);self.assertFalse(db.exists());self.assertTrue(out.exists());self.assertFalse(list(self.root.glob('.recap-*')))

    def test_v2_never_allows_normalized_parsing_label(self):
        a.ingest_bytes(self.live,'synthetic',self.raw,conversation='a')
        step=self.step('a');step['label']='invented'
        with self.assertRaises(ValueError):self.run_plan(3,[step])

    def test_distinct_object_order_is_checked_by_message_digest(self):
        other=b'\n'+self.raw;digest=hashlib.sha256(other).hexdigest();(self.objects/digest).write_bytes(other)
        a.ingest_bytes(self.live,'synthetic',self.raw,conversation='a');a.ingest_bytes(self.live,'synthetic',other,conversation='b')
        r,db,_=self.run_plan(3,[self.step('a'),self.step('b',digest)])
        self.assertEqual(r['status'],rebuild.PASSED,r);self.assertEqual(prior.tables(db),prior.tables(self.live))
        r,db,_=self.run_plan(3,[self.step('a',digest),self.step('a'),self.step('b',digest)],suffix='wrong')
        self.assertEqual(r['status'],rebuild.FAILED);self.assertIn('messages_digest',r['failed_checks']);self.assertFalse(db.exists())

    def test_published_selected_guide_executes_without_source_changes(self):
        import re,shlex,subprocess,sys
        root=Path(__file__).resolve().parents[1];out=self.root/'guide';out.mkdir()
        source=root/'examples/time-sample.jsonl';before=source.read_bytes()
        blocks=re.findall(r'```sh\n(.*?)```',(root/'docs/SELECTED_NORMALIZED.md').read_text(encoding='utf-8'),re.S)
        self.assertEqual(len(blocks),1);results=[]
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line.replace('OUTPUT',str(out)));args[0]=sys.executable
            done=subprocess.run(args,cwd=root,capture_output=True,timeout=30)
            self.assertEqual(done.returncode,0,done.stderr)
            if done.stdout:results.append(json.loads(done.stdout))
        self.assertEqual(results[-1]['status'],rebuild.PASSED)
        self.assertEqual(prior.tables(out/'archive.sqlite'),prior.tables(out/'rebuilt.sqlite'))
        self.assertEqual(source.read_bytes(),before)
