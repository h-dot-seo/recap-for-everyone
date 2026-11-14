"""Synthetic serialized-reference parity and removal of redundant decoding."""
import copy
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

from recaplib import archive, session_workflow as workflow

ROOT = Path(__file__).resolve().parents[1]


def tables(db):
    connection = sqlite3.connect(db)
    try:
        names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: sorted(connection.execute('SELECT * FROM "'+name+'"').fetchall(), key=repr) for name in names}
    finally:
        connection.close()


def row(**updates):
    return dict(dict(conversation_id='합성 😀', message_id='m1', role='user', timestamp='unknown',
                     text='Synthetic 한국어\nsecond\rthird\u2028line', title='Synthetic title',
                     origin_sha256='a'*64, origin_locator='line:1', parent_id=None), **updates)


class AdapterSinglePassTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_all_formats_selections_newlines_match_serialized_reference(self):
        fixtures = [('web','web-export.json','synthetic-chat'),('local','local-session.jsonl','synthetic-local'),
                    ('local-codex','source-attributed-session.jsonl','synthetic-attributed')]
        for kind,name,identity in fixtures:
            path=ROOT/'examples'/name
            raw=path.read_bytes()
            for selection in (None,identity):
                for newline in ('lf','crlf'):
                    with self.subTest(kind=kind,selection=selection,newline=newline):
                        suffix=kind+str(selection)+newline
                        old=self.root/(suffix+'-old.sqlite'); new=self.root/(suffix+'-new.sqlite')
                        rows,coverage=workflow._normalize_selected_bytes(raw,name,kind,selection)
                        normalized=workflow._normalized_bytes(rows,'\n' if newline=='lf' else '\r\n')
                        expected=archive.ingest_bytes(old,'demo',normalized,provenance=rows)
                        with patch.object(archive,'loads',side_effect=AssertionError('generated JSON decoded')):
                            actual=workflow.import_export_bytes(new,'demo',raw,name,kind,selection,newline=newline)
                        self.assertEqual({k:v for k,v in actual.items() if k not in ('coverage','replay')},expected)
                        self.assertEqual(actual['coverage'],coverage)
                        self.assertEqual(tables(old),tables(new))
                        self.assertEqual(archive.search(old,'synthetic'),archive.search(new,'synthetic'))

    def test_path_import_one_source_snapshot_no_normalized_decode(self):
        path=ROOT/'examples/web-export.json'
        original=Path.read_bytes
        reads=[]
        def counted(current):
            reads.append(current)
            return original(current)
        with patch.object(Path,'read_bytes',counted),patch.object(archive,'loads',side_effect=AssertionError('generated decode')):
            actual=workflow.import_export(self.root/'new.sqlite','demo',path,'web')
        self.assertEqual(reads,[path])
        rows,report=workflow.normalize(path,'web',include_report=True)
        expected=archive.ingest_bytes(self.root/'old.sqlite','demo',workflow._normalized_bytes(rows),rows)
        self.assertEqual(actual,dict(expected,coverage=report))
        self.assertEqual(tables(self.root/'old.sqlite'),tables(self.root/'new.sqlite'))

    def test_empty_duplicates_unicode_and_physical_lines_reference(self):
        cases=[[],[row()],[row(),row()],[row(),row(message_id='m2',title='second')]]
        for index,rows in enumerate(cases):
            untouched=copy.deepcopy(rows)
            for newline in ('\n','\r\n'):
                suffix=str(index)+str(len(newline));old=self.root/(suffix+'old.sqlite');new=self.root/(suffix+'new.sqlite')
                raw=workflow._normalized_bytes(rows,newline)
                expected=archive.ingest_bytes(old,'demo',raw,rows)
                with patch.object(archive,'loads',side_effect=AssertionError('decode')):
                    actual=archive._ingest_adapter_rows(new,'demo',rows,newline=newline)
                self.assertEqual(actual,expected)
                self.assertEqual(tables(new),tables(old))
                self.assertEqual(rows,untouched)
                repeat=archive._ingest_adapter_rows(new,'demo',rows,newline=newline)
                self.assertEqual(repeat['inserted'],0)

    def test_invalid_shapes_unicode_serializability_and_conflicts_before_connect(self):
        cases=[[None],[row(text='')],[row(title=None)],[row(role='alien')],[row(message_id=1)],
               [row(text='bad\ud800')],[row(ignored={'deep':['bad\ud800']})],[row(ignored=object())],[row(ignored={1:'one','1':'duplicate'})],
               [row(ignored={'nested':[{None:'one','null':'duplicate'}]})],
               [row(),row(text='contradiction')]]
        for index,rows in enumerate(cases):
            db=self.root/(str(index)+'.sqlite')
            with self.subTest(index=index),patch.object(archive.sqlite3,'connect',side_effect=AssertionError('database opened')):
                with self.assertRaises((ValueError,TypeError)):
                    archive._ingest_adapter_rows(db,'demo',rows)
            self.assertFalse(db.exists())

    def test_archive_conflict_rolls_back_artifact_messages_provenance_fts(self):
        db=self.root/'existing.sqlite'
        archive._ingest_adapter_rows(db,'demo',[row()])
        before=tables(db)
        with self.assertRaisesRegex(ValueError,'conflicting message identity at line 2'):
            archive._ingest_adapter_rows(db,'demo',[row(message_id='new',text='flower'),row(text='changed')])
        self.assertEqual(tables(db),before)
        self.assertEqual(archive.search(db,'flower'),[])

    def test_direct_normalized_ingest_still_calls_decoder(self):
        decode=archive.loads
        with patch.object(archive,'loads',wraps=decode) as observed:
            archive.ingest_bytes(self.root/'direct.sqlite','demo',workflow._normalized_bytes([row(),row()]))
        self.assertEqual(observed.call_count,2)

    def test_documented_synthetic_commands(self):
        guide=(ROOT/'docs/ADAPTER_IMPORT_COST.md').read_text(encoding='utf-8')
        block=re.search(r'```sh\n(.*?)```',guide,re.S).group(1)
        results=[]
        for line in block.strip().splitlines():
            args=shlex.split(line)
            args=[str(self.root)+arg[len('OUTPUT'):] if arg.startswith('OUTPUT') else arg for arg in args]
            args[0]=sys.executable
            result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            results.append(json.loads(result.stdout))
        self.assertEqual(len(results),3)
        self.assertGreater(results[0]['inserted'],0)
        self.assertEqual(results[1]['inserted'],0)


if __name__ == '__main__':
    unittest.main()
