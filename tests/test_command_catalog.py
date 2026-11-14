"""CLI contract discovery: read-only metadata, not execution authorization."""
import argparse
import builtins
import contextlib
import io
import json
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import recap
from recaplib import command_catalog as catalog

ROOT=Path(__file__).resolve().parents[1]
EXPECTED=set('''ingest search stats ledger describe-schema inspect list-export inspect-web-zip prepare-web-export replay-local web-branch suggest-branch-title suggest-replay-title suggest-attributed-title preview-title apply-title review-state render-queue review-titles title-adapter-dry-run title-adapter-simulate export-title-plan check-title-plan import check-import export-normalized export-provenance check-provenance declare-review-checkpoint declare-checkpoint changed-since declare-recovery rehearse-recovery rebuild-archive list find show render suggest-title title title-history describe'''.split())


class CommandCatalogTests(unittest.TestCase):
    def invoke(self,*args):
        output=io.StringIO()
        with patch.object(sys,'argv',['recap']+list(args)),contextlib.redirect_stdout(output):
            recap.main()
        return json.loads(output.getvalue())

    def test_exact_command_set_options_and_guides(self):
        parser=recap.build_parser();value=catalog.describe(parser)
        choices=next(a.choices for a in parser._actions if isinstance(a,argparse._SubParsersAction))
        self.assertEqual(set(choices),EXPECTED)
        self.assertEqual({e['command'] for e in value['commands']},EXPECTED)
        for entry in value['commands']:
            with self.subTest(command=entry['command']):
                self.assertTrue((ROOT/entry['guide']).is_file())
                actions=choices[entry['command']]._actions
                self.assertEqual(len(entry['options']),len(actions))
                for option,action in zip(entry['options'],actions):
                    self.assertEqual(option['name'],action.dest)
                    self.assertEqual(option['flags'],action.option_strings)
                    self.assertEqual(option['required'],bool(action.required))
                    self.assertEqual(option['choices'],list(action.choices) if action.choices is not None else None)
                self.assertNotIn('usage',entry)
                self.assertEqual(entry['needs_db'],catalog.needs_db(entry['command']))
        self.assertEqual(value['schema'],'recap.command-catalog.v1')
        self.assertEqual(len(value['standalone']),4)
        self.assertIn('EXTERNAL_NOT_CONFIGURED',value['standalone'][1]['network'])

    def test_no_database_input_or_writes_and_db_ignored(self):
        original=Path.open
        opened=[]
        def only_manifest(path,*args,**kwargs):
            self.assertEqual(path,ROOT/'PUBLICATION_MANIFEST.json')
            self.assertEqual(args,('rb',))
            opened.append(path)
            return original(path,*args,**kwargs)
        with patch.object(sqlite3,'connect',side_effect=AssertionError('DB opened')),patch.object(Path,'open',only_manifest),patch.object(builtins,'open',side_effect=AssertionError('unexpected open')):
            result=self.invoke('--db','PRIVATE_UNOPENED_DB','describe','show')
        self.assertEqual(result['commands'][0]['command'],'show')
        self.assertEqual(len(opened),1)
        self.assertNotIn('PRIVATE_UNOPENED_DB',json.dumps(result))

    def test_manifest_absent_unreadable_malformed_and_valid_label(self):
        for error in (FileNotFoundError('private path'),PermissionError('private path')):
            with patch.object(Path,'open',side_effect=error):
                self.assertIsNone(catalog.describe(recap.build_parser())['release'])
        for raw in (b'bad',b'[]',b'{"release":12}',b'{"release":""}',b'{"release":"a","release":"b"}',b'\xff'):
            with patch.object(Path,'open',return_value=io.BytesIO(raw)):
                self.assertIsNone(catalog.describe(recap.build_parser())['release'])
        with patch.object(Path,'open',return_value=io.BytesIO(b'{"release":"unverified-synthetic"}')):
            self.assertEqual(catalog.describe(recap.build_parser())['release'],'unverified-synthetic')

    def test_effects_conditional_writes_and_result_exits(self):
        entries={e['command']:e for e in catalog.describe(recap.build_parser())['commands']}
        for name in ('title','review-state'):
            self.assertEqual(entries[name]['writes'],dict(default=[],conditional=[dict(flag='--set',writes=['--db'])]))
        self.assertEqual(entries['check-import']['writes']['conditional'],[dict(flag='--delta-output',writes=['--delta-output'])])
        self.assertEqual(entries['show']['output_schema'],None)
        self.assertEqual(entries['show']['output_schema_conditional'][0]['schema'],'recap.saved-document.v1')
        self.assertEqual(entries['stats']['output_schema_conditional'],[dict(when='with --by-source',schema=None)])
        self.assertEqual(set(entries['rebuild-archive']['writes']['default']),{'--new-db','--output'})
        self.assertEqual(entries['rebuild-archive']['needs_db'],'rejected')
        self.assertTrue(any('remain published' in note for note in entries['rebuild-archive']['notes']))
        for name in ('check-provenance','check-import','changed-since','rehearse-recovery','rebuild-archive','replay-local'):
            self.assertIsNotNone(entries[name]['exits']['1']['result_failure'])
        for name in ('inspect','describe','web-branch'):
            self.assertEqual(entries[name]['needs_db'],'ignored')

    def test_unknown_command_and_existing_db_rejections(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as error:
            self.invoke('describe','not-a-command')
        self.assertEqual(error.exception.code,2)
        for command,args,expected in (
            ('render-queue',['queue.json','--output','out'],'render-queue reads a saved JSON file only; do not pass --db'),
            ('rebuild-archive',['manifest','--plan','plan','--objects','objects','--new-db','db','--output','out'],'rebuild-archive creates --new-db only; do not pass --db'),
            ('rehearse-recovery',['manifest','--restored-db','db','--output','out'],'rehearse-recovery opens --restored-db only; do not pass --db')):
            stderr=io.StringIO()
            with contextlib.redirect_stderr(stderr),self.assertRaises(SystemExit) as error:
                self.invoke('--db','unused',command,*args)
            self.assertEqual(error.exception.code,2)
            self.assertTrue(stderr.getvalue().endswith(expected+'\n'))
        with self.assertRaises(ValueError):catalog.describe(recap.build_parser(),'unknown')

    def test_synthetic_default_reads_and_explicit_title_write(self):
        from recaplib.archive import ingest_bytes
        with tempfile.TemporaryDirectory() as temporary:
            db=Path(temporary)/'archive.sqlite'
            ingest_bytes(db,'demo',b'{"conversation_id":"c","message_id":"m","role":"user","timestamp":"unknown","text":"synthetic topic"}\n')
            before=db.read_bytes()
            self.invoke('--db',str(db),'title','--source','demo','--conversation','c')
            self.invoke('--db',str(db),'review-state','--source','demo','--conversation','c')
            self.assertEqual(db.read_bytes(),before)
            self.invoke('--db',str(db),'title','--source','demo','--conversation','c','--set','Synthetic title','--expected-revision','0')
            self.assertNotEqual(db.read_bytes(),before)
            output=Path(temporary)/'saved.json'
            receipt=self.invoke('--db',str(db),'show','--source','demo','--conversation','c','--output',str(output))
            self.assertEqual(receipt['schema'],'recap.saved-document.v1')
            self.assertTrue(output.is_file())

    def test_documented_examples(self):
        guide=(ROOT/'docs/COMMAND_CATALOG.md').read_text(encoding='utf-8')
        block=re.search(r'```sh\n(.*?)```',guide,re.S).group(1)
        results=[]
        for line in block.strip().splitlines():
            args=shlex.split(line);args[0]=sys.executable
            result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            results.append(json.loads(result.stdout))
        self.assertEqual(len(results),3)
        self.assertEqual({e['command'] for e in results[0]['commands']},EXPECTED)
        self.assertEqual(results[1]['commands'][0]['command'],'title')
        self.assertEqual(results[2]['commands'][0]['command'],'rebuild-archive')


if __name__=='__main__':
    unittest.main()
