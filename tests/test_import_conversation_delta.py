"""Mechanical conversation deltas never infer activity or authorize imports."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes
from recaplib.import_check import check_import
ROOT=Path(__file__).resolve().parents[1]


def row(cid,mid='m',title='synthetic',text='invented'):
    return dict(conversation_id=cid,message_id=mid,title=title,text=text,role='user',timestamp='unknown')


def encoded(rows):return ''.join(json.dumps(r)+'\n' for r in rows).encode()


class ImportDeltaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'archive.sqlite';self.input=self.root/'incoming.jsonl'
        ingest_bytes(self.db,'synthetic',encoded([row(c) for c in ['changed','same','conflict','archive-only']]))

    def check(self,rows,**kw):
        self.input.write_bytes(encoded(rows))
        return check_import(self.db,'synthetic',self.input,'normalized',**kw)

    def test_four_mutually_exclusive_categories_and_private_stdout(self):
        rows=[row('new-private'),row('changed'),row('changed','new'),row('same'),row('conflict',title='different')]
        result=self.check(rows);d=result['conversation_delta']
        self.assertEqual(d['conversations'],4)
        self.assertEqual(d['counts'],dict(conflicting=1,new=1,has_new_identities=1,no_new_identities=1))
        self.assertTrue(result['conflicts_found'])
        for cid in ['new-private','changed','same','conflict','archive-only']:
            self.assertNotIn('"'+cid+'"',json.dumps(result))

    def test_repeated_input_conflict_overrides_new_and_existing(self):
        result=self.check([row('new'),row('new',text='different'),row('same'),row('same',text='different'),row('same','new')])
        self.assertEqual(result['conversation_delta']['counts'],dict(conflicting=2,new=0,has_new_identities=0,no_new_identities=0))
        repeated=self.check([row('new'),row('new')])
        self.assertEqual(repeated['conversation_delta']['counts']['new'],1)
        self.assertEqual(repeated['repeated_input']['identical'],1)

    def test_bounded_sorted_exclusive_file_and_hash(self):
        output=self.root/'delta.json';before=self.db.read_bytes()
        result=self.check([row('z'),row('A'),row('a')],limit=2,delta_output=output)
        raw=output.read_bytes();doc=json.loads(raw)
        self.assertEqual(doc['samples']['new'],['A','a']);self.assertEqual(doc['omitted']['new'],1)
        self.assertEqual(result['delta_document']['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertFalse(doc['contains_message_text']);self.assertEqual(self.db.read_bytes(),before)
        with patch('recaplib.import_check.inspect_normalized',side_effect=AssertionError('preflight first')):
            with self.assertRaises(FileExistsError):check_import(self.db,'synthetic',self.input,'normalized',delta_output=output)
        self.assertEqual(output.read_bytes(),raw)

    def test_selection_and_source_scope(self):
        self.input.write_bytes(encoded([row('same'),row('new')]))
        with self.assertRaisesRegex(ValueError,'does not support conversation selection'):
            check_import(self.db,'synthetic',self.input,'normalized',conversation='same')
        with patch('recaplib.import_check.normalize',return_value=([row('same')],{})):
            result=check_import(self.db,'synthetic',self.input,'web',conversation='same')
        self.assertEqual(result['conversation_delta']['conversations'],1)
        self.assertEqual(result['conversation_delta']['counts']['no_new_identities'],1)
        result=check_import(self.db,'other-source',self.input,'normalized')
        self.assertEqual(result['conversation_delta']['counts']['new'],2)

    def test_document_byte_bound_no_output(self):
        output=self.root/'no.json'
        with patch('recaplib.import_check.MAX_DELTA_BYTES',1):
            with self.assertRaisesRegex(ValueError,'byte limit'):self.check([row('new')],delta_output=output)
        self.assertFalse(output.exists())
        self.assertFalse(any(p.name.startswith('.recap-import-delta-') for p in self.root.iterdir()))

    def test_conflict_cli_exit_contract_and_standalone_parity(self):
        self.input.write_bytes(encoded([row('conflict',title='different')]))
        common=['--db',str(self.db)]
        arguments=[str(self.input),'--source','synthetic','--format','normalized']
        outputs=[]
        for script,prefix in [('recap.py',['check-import']),('import_check.py',[])]:
            output=self.root/(script+'.json')
            run=subprocess.run([sys.executable,str(ROOT/script),*common,*prefix,*arguments,'--delta-output',str(output)],capture_output=True,text=True)
            self.assertEqual(run.returncode,1,run.stderr);self.assertEqual(run.stderr,'')
            outputs.append(json.loads(run.stdout));self.assertTrue(output.exists())
        self.assertEqual(outputs[0],outputs[1])

    def test_counts_and_identity_checks_use_one_snapshot(self):
        from recaplib.archive import readonly
        with closing(sqlite3.connect(self.db)) as c:c.execute('PRAGMA journal_mode=WAL')
        reader=readonly(self.db)
        class Interleaved:
            def __getattr__(proxy,name):return getattr(reader,name)
            def execute(proxy,sql,*args):
                result=reader.execute(sql,*args)
                if sql.startswith('SELECT conversation_id FROM messages'):
                    ingest_bytes(self.db,'synthetic',encoded([row('later')]))
                return result
        with patch('recaplib.import_check.readonly',return_value=Interleaved()):
            result=self.check([row('later')])
        self.assertEqual(result['conversation_delta']['counts']['new'],1)
        self.assertEqual(result['archive_comparison']['new'],1)
        self.assertEqual(self.check([row('later')])['conversation_delta']['counts']['no_new_identities'],1)

    def test_documented_walkthrough(self):
        import re
        import shlex
        guide=(ROOT/'docs/REIMPORT_DELTA.md').read_text()
        block=re.search(r'```sh\n(.*?)```',guide,re.S).group(1)
        output=self.root/'walkthrough space'
        for line in block.strip().splitlines():
            args=shlex.split(line)
            args=[arg.replace('OUTPUT',str(output)) for arg in args]
            if args[0]=='mkdir':Path(args[1]).mkdir();continue
            args[0]=sys.executable
            run=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(run.returncode,1 if 'check-import' in args else 0,run.stderr)
        document=json.loads((output/'delta.json').read_text())
        self.assertEqual(document['conversation_delta']['counts'],dict(conflicting=1,new=1,has_new_identities=1,no_new_identities=1))
