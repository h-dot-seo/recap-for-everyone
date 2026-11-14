"""Synthetic artifact cutoff CLI contracts; never real archives."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
import sqlite3
from recaplib.archive import ingest_bytes

ROOT = Path(__file__).resolve().parents[1]

class ImportCheckpointCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root/'archive.sqlite'
        self.cutoff = self.root/'cutoff.json'
        row = dict(conversation_id='PRIVATE_CONVERSATION',message_id='m',role='user',
                   timestamp='unknown',text='Synthetic private text',title='Synthetic')
        ingest_bytes(self.db,'PRIVATE_SOURCE',(json.dumps(row)+'\n').encode())

    def run_cli(self,*args):
        return subprocess.run([sys.executable,str(ROOT/'recap.py'),'--db',str(self.db),*args],
                              capture_output=True)

    def declare(self):
        p=self.run_cli('declare-checkpoint','--source','PRIVATE_SOURCE','--output',str(self.cutoff))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertNotIn(b'PRIVATE_',p.stdout)
        self.assertNotIn(b'Synthetic private text',p.stdout)
        return json.loads(p.stdout)

    def test_id_free_cli_readonly_and_exclusive(self):
        before=self.db.read_bytes(); self.declare()
        p=self.run_cli('changed-since','--source','PRIVATE_SOURCE','--checkpoint',str(self.cutoff))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['status'],'CUTOFF_VERIFIED')
        self.assertNotIn(b'PRIVATE_',p.stdout)
        self.assertEqual(before,self.db.read_bytes())
        raw=self.cutoff.read_bytes()
        p=self.run_cli('declare-checkpoint','--source','PRIVATE_SOURCE','--output',str(self.cutoff))
        self.assertEqual(p.returncode,1);self.assertEqual(raw,self.cutoff.read_bytes())

    def test_unverified_exit_one_with_no_delta(self):
        self.declare()
        with closing(sqlite3.connect(self.db)) as con:
            with con: con.execute("UPDATE messages SET timestamp='tampered'")
        with self.assertRaises(sqlite3.ProgrammingError): con.execute('SELECT 1')
        p=self.run_cli('changed-since','--source','PRIVATE_SOURCE','--checkpoint',str(self.cutoff))
        self.assertEqual(p.returncode,1,p.stderr)
        result=json.loads(p.stdout)
        self.assertEqual(result['status'],'CUTOFF_NOT_VERIFIED');self.assertIsNone(result['delta'])
        self.assertNotIn(b'PRIVATE_',p.stdout)

    def test_text_and_wrong_source_errors(self):
        self.declare()
        p=self.run_cli('changed-since','--source','PRIVATE_SOURCE','--checkpoint',str(self.cutoff),'--text')
        self.assertEqual(p.returncode,0,p.stderr);p.stdout.decode('ascii')
        self.assertNotIn(b'PRIVATE_',p.stdout)
        p=self.run_cli('changed-since','--source','PRIVATE_WRONG','--checkpoint',str(self.cutoff))
        self.assertEqual(p.returncode,1);self.assertFalse(p.stdout)
        self.assertNotIn(b'PRIVATE_',p.stderr)

    def test_documented_workflow(self):
        guide=(ROOT/'docs/IMPORT_CHECKPOINT.md').read_text()
        blocks=guide.split('```sh\n')[1:];self.assertEqual(len(blocks),1)
        outputs=[]
        # Separate workspace because the guide promises a new archive.
        out=self.root/'guide';out.mkdir()
        for line in blocks[0].split('```',1)[0].strip().splitlines():
            args=[a.replace('OUTPUT',str(out)) for a in shlex.split(line)]
            self.assertEqual(args[0],'python');args[0]=sys.executable
            p=subprocess.run(args,cwd=ROOT,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr);outputs.append(json.loads(p.stdout))
        result=outputs[-1]
        self.assertEqual(result['status'],'CUTOFF_VERIFIED')
        self.assertEqual(result['delta']['new_conversations'],6)
        self.assertEqual(result['delta']['has_new_identities'],0)
        self.assertEqual(result['delta']['no_new_identities'],6)
