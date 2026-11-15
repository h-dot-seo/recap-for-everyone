"""Private ID files only after cutoff verification; not review authorization."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
from tests import test_import_checkpoint_core as fixtures
from recaplib import import_checkpoint as cp

ROOT=Path(__file__).resolve().parents[1]
class CheckpointDeltaTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ImportCheckpointTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        _,self.saved=self.f.declare();self.out=self.f.root/'delta.json'
    def changes(self):
        self.f.seed([('private-a','2'),('private-new-z','1'),('private-new-a','1')])
        self.f.seed([('private-a','3'),('private-new-z','2')])
    def test_partition_limits_sorted_ids_and_private_stdout(self):
        self.changes();before=self.f.db.read_bytes();plain=cp.changed_since(self.f.db,self.f.source,self.saved)
        result=cp.changed_since(self.f.db,self.f.source,self.saved,delta_output=self.out,limit=1)
        self.assertEqual(result['delta'],plain['delta']);self.assertNotIn('private',json.dumps({k:v for k,v in result.items() if k!='delta_document'}))
        doc=json.loads(self.out.read_text(encoding='utf-8'))
        self.assertEqual(doc['samples']['new_conversations'],['private-new-a']);self.assertEqual(doc['omitted']['new_conversations'],1)
        self.assertEqual(doc['samples']['has_new_identities'],['private-a']);self.assertEqual(doc['samples']['no_new_identities'],['private-b'])
        self.assertNotIn('private text',self.out.read_text(encoding='utf-8'));self.assertEqual(before,self.f.db.read_bytes())
    def test_invalid_limit_never_opens_archive_or_creates_output(self):
        for limit in (0,-1,1001,True,False,None,1.5,'1'):
            with patch.object(cp,'readonly',side_effect=AssertionError('no DB')):
                with self.subTest(limit=limit),self.assertRaises(ValueError):cp.changed_since(self.f.db,self.f.source,self.saved,delta_output=self.out,limit=limit)
        self.assertFalse(self.out.exists())
    def test_unverified_digest_has_no_file_or_samples(self):
        self.changes();bad=dict(self.saved,messages_sha256='0'*64)
        result=cp.changed_since(self.f.db,self.f.source,bad,delta_output=self.out)
        self.assertEqual(result['status'],'CUTOFF_NOT_VERIFIED');self.assertIsNone(result['delta']);self.assertNotIn('delta_document',result);self.assertFalse(self.out.exists())
    def test_deleted_artifact_no_output(self):
        with closing(sqlite3.connect(self.f.db)) as conn,conn:conn.execute('DELETE FROM artifacts')
        result=cp.changed_since(self.f.db,self.f.source,self.saved,delta_output=self.out)
        self.assertEqual(result['status'],'CUTOFF_NOT_VERIFIED');self.assertFalse(self.out.exists())
    def test_existing_output_is_never_overwritten(self):
        self.out.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):cp.changed_since(self.f.db,self.f.source,self.saved,delta_output=self.out)
        self.assertEqual(self.out.read_bytes(),b'keep')
    def test_late_collision_preserves_competing_output(self):
        original=cp._publish_new_file
        def race(path,raw,prefix):Path(path).write_bytes(b'other');return original(path,raw,prefix)
        with patch.object(cp,'_publish_new_file',race),self.assertRaises(FileExistsError):cp.changed_since(self.f.db,self.f.source,self.saved,delta_output=self.out)
        self.assertEqual(self.out.read_bytes(),b'other');self.assertEqual(list(self.f.root.glob('.recap-*')),[])
    def test_snapshot_verification_precedes_publication(self):
        self.changes();original=cp._publish_new_file;observed=[]
        def publish(path,raw,prefix):
            observed.append(json.loads(raw)['samples'])
            return original(path,raw,prefix)
        with patch.object(cp,'_publish_new_file',publish):cp.changed_since(self.f.db,self.f.source,self.saved,delta_output=self.out)
        self.assertEqual(len(observed),1);self.assertEqual(observed[0]['new_conversations'],['private-new-a','private-new-z'])
    def test_cli_default_bytes_and_optin_does_not_print_ids(self):
        self.changes();args=['--db',str(self.f.db),'changed-since','--source',self.f.source,'--checkpoint',str(self.f.path)]
        a=subprocess.run([sys.executable,'recap.py',*args],cwd=ROOT,capture_output=True)
        b=subprocess.run([sys.executable,'recap.py',*args,'--delta-output',str(self.out),'--limit','1'],cwd=ROOT,capture_output=True)
        self.assertEqual(a.returncode,0,a.stderr);self.assertEqual(b.returncode,0,b.stderr)
        self.assertNotIn(b'private-',a.stdout);self.assertNotIn(b'private-',b.stdout)
        data=json.loads(b.stdout);data.pop('delta_document');self.assertEqual(data,json.loads(a.stdout))
    def test_stdout_failure_after_publish_does_not_remove_saved_file(self):
        import recap
        self.changes();before=self.f.db.read_bytes()
        args=['recap','--db',str(self.f.db),'changed-since','--source',self.f.source,'--checkpoint',str(self.f.path),'--delta-output',str(self.out)]
        with patch.object(sys,'argv',args),patch('builtins.print',side_effect=BrokenPipeError('synthetic closed pipe')):
            with self.assertRaises(BrokenPipeError):recap.main()
        self.assertTrue(self.out.exists());self.assertEqual(json.loads(self.out.read_text(encoding='utf-8'))['status'],'CUTOFF_VERIFIED');self.assertEqual(before,self.f.db.read_bytes())
    def test_document_budget_rejects_before_publication(self):
        self.changes()
        with patch.object(cp,'MAX_DELTA_BYTES',10),self.assertRaises(ValueError):cp.changed_since(self.f.db,self.f.source,self.saved,delta_output=self.out)
        self.assertFalse(self.out.exists());self.assertEqual(list(self.f.root.glob('.recap-*')),[])
    def test_published_guide_manual_followup(self):
        import re,shlex
        blocks=re.findall(r'```sh\n(.*?)```',(ROOT/'docs/CHECKPOINT_DELTA.md').read_text(encoding='utf-8'),re.S);self.assertEqual(len(blocks),1)
        out=self.f.root/'guide';out.mkdir()
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);args[0]=sys.executable
            r=subprocess.run([x.replace('OUTPUT',str(out)) for x in args],cwd=ROOT,capture_output=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
        document=json.loads((out/'delta.json').read_text(encoding='utf-8'))
        self.assertIn('epoch',document['samples']['new_conversations'])
