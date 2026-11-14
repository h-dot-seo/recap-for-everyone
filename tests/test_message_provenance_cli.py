"""Synthetic detached message locator CLI contracts."""
import hashlib
import json
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from recaplib.archive import ingest_bytes
from recaplib.session_workflow import titles

ROOT=Path(__file__).resolve().parents[1]

class MessageProvenanceCliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'archive.sqlite';self.card=self.root/'card.json'
        raw=json.dumps(dict(conversation_id='PRIVATE_CONVERSATION',message_id='PRIVATE_MESSAGE',role='user',
                            timestamp='unknown',title='PRIVATE_TITLE',text='PRIVATE_BODY')).encode()+b'\n'
        ingest_bytes(self.db,'PRIVATE_SOURCE',raw)

    def cli(self,*args):
        return subprocess.run([sys.executable,str(ROOT/'recap.py'),'--db',str(self.db),*map(str,args)],capture_output=True)

    def export(self):
        p=self.cli('export-provenance','--source','PRIVATE_SOURCE','--conversation','PRIVATE_CONVERSATION',
                   '--message','PRIVATE_MESSAGE','--output',self.card)
        self.assertEqual(p.returncode,0,p.stderr);self.assertNotIn(b'PRIVATE_',p.stdout)
        self.assertNotIn(b'PRIVATE_BODY',self.card.read_bytes());self.assertNotIn(b'PRIVATE_TITLE',self.card.read_bytes())
        return json.loads(p.stdout)

    def test_private_file_receipt_recheck_and_title_changes(self):
        before=self.db.read_bytes();receipt=self.export();raw=self.card.read_bytes()
        p=self.cli('check-provenance',self.card)
        self.assertEqual(p.returncode,0,p.stderr);self.assertNotIn(b'PRIVATE_',p.stdout)
        self.assertEqual(before,self.db.read_bytes())
        titles(self.db,'PRIVATE_SOURCE','PRIVATE_CONVERSATION','Different private display title',0)
        p=self.cli('check-provenance',self.card,'--text')
        self.assertEqual(p.returncode,0,p.stderr);self.assertNotIn(b'PRIVATE_',p.stdout)
        self.assertEqual(raw,self.card.read_bytes())
        p=self.cli('export-provenance','--source','PRIVATE_SOURCE','--conversation','PRIVATE_CONVERSATION',
                   '--message','PRIVATE_MESSAGE','--output',self.card)
        self.assertEqual(p.returncode,1);self.assertEqual(raw,self.card.read_bytes())

    def test_stale_and_malformed_leave_originals_unchanged(self):
        self.export()
        with closing(sqlite3.connect(self.db)) as con:
            with con:con.execute("UPDATE messages SET timestamp='changed'")
        with self.assertRaises(sqlite3.ProgrammingError):con.execute('SELECT 1')
        before=self.db.read_bytes();raw=self.card.read_bytes()
        p=self.cli('check-provenance',self.card)
        self.assertEqual(p.returncode,1,p.stderr);self.assertTrue(p.stdout);self.assertFalse(p.stderr)
        self.assertNotIn(b'PRIVATE_',p.stdout);self.assertEqual(before,self.db.read_bytes());self.assertEqual(raw,self.card.read_bytes())
        self.card.write_bytes(b'{"PRIVATE_MARKER":')
        p=self.cli('check-provenance',self.card)
        self.assertEqual(p.returncode,1);self.assertFalse(p.stdout);self.assertNotIn(b'PRIVATE_',p.stderr)

    def test_documented_workflow(self):
        out=self.root/'guide';out.mkdir()
        guide=(ROOT/'docs/MESSAGE_PROVENANCE.md').read_text();blocks=guide.split('```sh\n')[1:]
        self.assertEqual(len(blocks),1)
        for line in blocks[0].split('```',1)[0].strip().splitlines():
            args=[a.replace('OUTPUT',out.as_posix()) for a in shlex.split(line)]
            self.assertEqual(args[0],'python');args[0]=sys.executable
            p=subprocess.run(args,cwd=ROOT,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr);json.loads(p.stdout)
        card=json.loads((out/'message-card.json').read_text())
        self.assertEqual(card['export_provenance'][0]['parent_id'],'m1')
        self.assertNotIn(b'Design a synthetic orchard experiment',(out/'message-card.json').read_bytes())
