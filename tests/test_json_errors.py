"""Opt-in caught-error envelopes preserve legacy stderr and result exit paths."""
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
from recaplib import errors
from recaplib.cli_errors import safe_diagnostic

ROOT=Path(__file__).resolve().parents[1]


class JsonErrorTests(unittest.TestCase):
    def invoke(self,args,json_errors=False):
        out,err=io.StringIO(),io.StringIO();status=0
        argv=['recap']+(['--json-errors'] if json_errors else [])+[str(a) for a in args]
        with patch.object(sys,'argv',argv),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            try:recap.main()
            except SystemExit as error:status=error.code
        return status,out.getvalue(),err.getvalue()

    def assert_envelope_pair(self,args,code):
        plain=self.invoke(args)
        encoded=self.invoke(args,True)
        self.assertEqual(plain[:2],(1,''),plain)
        self.assertEqual(encoded[:2],(1,''),encoded)
        value=json.loads(encoded[2])
        self.assertEqual(value,dict(schema='recap.error.v1',code=code,message=plain[2].rstrip('\n'),exit_status=1))
        self.assertEqual(encoded[2].count('\n'),1)
        return value

    def test_typed_errors_are_valueerrors_with_identical_messages(self):
        for kind,code in ((errors.SourceChanged,'SOURCE_CHANGED'),(errors.Stale,'STALE'),
                          (errors.UnknownIdentity,'UNKNOWN_IDENTITY'),(errors.ConflictingIdentity,'CONFLICTING_IDENTITY')):
            error=kind('fixed existing message')
            self.assertIsInstance(error,ValueError)
            self.assertEqual(str(error),'fixed existing message')
            self.assertEqual(errors.error_document(error)['code'],code)
        # No inference from arbitrary exception strings, even identical text.
        for message in ('unknown conversation','conflicting message identity at line 1','stale title preview; preview again before applying'):
            self.assertEqual(errors.error_document(ValueError(message))['code'],'UNCLASSIFIED')

    def test_standard_types_suppress_low_level_private_payloads(self):
        cases=[(FileExistsError(17,'PRIVATE_ERROR','PRIVATE_PATH'),'OUTPUT_EXISTS'),
               (OSError(5,'PRIVATE_ERROR','PRIVATE_PATH'),'FILE_ERROR'),
               (sqlite3.DatabaseError('PRIVATE_SQL_TABLE'),'ARCHIVE_ERROR'),
               (json.JSONDecodeError('PRIVATE_FRAGMENT','PRIVATE_DOCUMENT',1),'UNCLASSIFIED'),
               (UnicodeDecodeError('utf-8',b'\xff',0,1,'PRIVATE_REASON'),'UNCLASSIFIED')]
        for error,code in cases:
            with self.subTest(kind=type(error).__name__),patch.object(recap,'ingest',side_effect=error):
                value=self.assert_envelope_pair(['--db','unused','ingest','unused','--source','synthetic'],code)
                self.assertNotIn('PRIVATE',json.dumps(value))
                self.assertEqual(value['message'],safe_diagnostic(error))
        with patch.object(recap,'ingest',side_effect=ValueError('fixed domain validation')):
            self.assert_envelope_pair(['--db','unused','ingest','unused','--source','synthetic'],'UNCLASSIFIED')

    def test_actual_source_conflict_stale_unknown_and_existing_output(self):
        from tests.test_command_effects import CommandEffectsTests
        fixture=CommandEffectsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.assert_envelope_pair(['--db',fixture.db,'import',fixture.web,'--source','web','--format','web','--expected-export-sha256','0'*64],'SOURCE_CHANGED')
        self.assert_envelope_pair(['--db',fixture.db,'ingest',ROOT/'examples/conversations.jsonl','--source','normalized','--expected-sha256','0'*64],'SOURCE_CHANGED')
        self.assert_envelope_pair(['prepare-web-export',fixture.zip,'--member','conversations.json','--output',fixture.root/'unused.json','--expected-archive-sha256','0'*64],'SOURCE_CHANGED')
        self.assert_envelope_pair(['--db',fixture.db,'title']+fixture.common+['--set','New synthetic title','--expected-revision','0'],'STALE')
        self.assert_envelope_pair(['--db',fixture.db,'show','--source','web','--conversation','unknown'],'UNKNOWN_IDENTITY')
        self.assert_envelope_pair(['--db',fixture.db,'show']+fixture.common+['--message','unknown'],'UNKNOWN_IDENTITY')
        self.assert_envelope_pair(['--db',fixture.db,'show']+fixture.common+['--output',fixture.card],'OUTPUT_EXISTS')
        records=[dict(conversation_id='x',message_id='m',role='user',timestamp='unknown',text=t) for t in ('one','two')]
        path=fixture.root/'conflict.jsonl';path.write_text(''.join(json.dumps(row)+'\n' for row in records),encoding='utf-8')
        absent=fixture.root/'absent.sqlite'
        self.assert_envelope_pair(['--db',absent,'ingest',path,'--source','new'],'CONFLICTING_IDENTITY')
        self.assertFalse(absent.exists())
        # Conflict against an existing DB uses the same explicit class.
        self.assert_envelope_pair(['--db',fixture.db,'import',fixture.conflict,'--source','web','--format','web'],'CONFLICTING_IDENTITY')

    def test_usage_and_result_exit_one_unchanged_and_success_unchanged(self):
        from tests.test_command_effects import CommandEffectsTests
        fixture=CommandEffectsTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        args=['--db',fixture.db,'check-provenance',fixture.stale_card]
        plain=self.invoke(args);encoded=self.invoke(args,True)
        self.assertEqual(plain,encoded)
        self.assertEqual(encoded[0],1);self.assertEqual(encoded[2],'')
        self.assertEqual(json.loads(encoded[1])['status'],'STALE')
        args=['replay-local',fixture.unsupported]
        self.assertEqual(self.invoke(args),self.invoke(args,True))
        self.assertEqual(self.invoke(args,True)[0],1)
        self.assertEqual(self.invoke(['--db',fixture.db,'stats']),self.invoke(['--db',fixture.db,'stats'],True))
        plain=self.invoke(['describe','unknown']);encoded=self.invoke(['describe','unknown'],True)
        self.assertEqual(plain,encoded)
        self.assertEqual(encoded[0],2)
        self.assertTrue(encoded[2].startswith('usage:'))

    def test_unexpected_exception_not_newly_caught_and_standalone_plain(self):
        with patch.object(recap,'ingest',side_effect=RuntimeError('unexpected')):
            with self.assertRaises(RuntimeError):
                self.invoke(['--db','unused','ingest','unused','--source','synthetic'],True)
        from recaplib import title_history
        out,err=io.StringIO(),io.StringIO()
        with patch.object(title_history,'history',side_effect=errors.UnknownIdentity('unknown conversation')),patch.object(sys,'argv',['title_history','--db','unused','--source','s','--conversation','c']),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as result:title_history.main()
        self.assertEqual(result.exception.code,1)
        self.assertEqual(out.getvalue(),'');self.assertEqual(err.getvalue(),'unknown conversation\n')

    def test_published_rebuild_receipt_failure_retains_advisory(self):
        from tests.test_rebuild_archive import RebuildTests
        from recaplib import recovery
        for enabled in (False,True):
            fixture=RebuildTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
            fixture.declare([fixture.step()])
            args=['rebuild-archive',fixture.manifest,'--plan',fixture.plan,'--objects',fixture.objects,'--new-db',fixture.db,'--output',fixture.output]
            with patch.object(recovery,'_publish_new_file',side_effect=OSError('PRIVATE_FAILURE')):
                status,out,err=self.invoke(args,enabled)
            self.assertEqual((status,out),(1,''))
            if enabled:
                document=json.loads(err);self.assertEqual(document['code'],'FILE_ERROR');message=document['message']
            else:message=err.rstrip('\n')
            self.assertEqual(message,'rebuilt database was published; receipt publication failed; database was preserved; inspect the requested new database before retrying')
            self.assertTrue(fixture.db.is_file());self.assertFalse(fixture.output.exists())
            self.assertNotIn(str(fixture.root),err);self.assertNotIn('PRIVATE_FAILURE',err)

    def test_documented_success_and_intentional_failure(self):
        text=(ROOT/'docs/JSON_ERRORS.md').read_text(encoding='utf-8')
        commands=[]
        for block in re.findall(r'```sh\n(.*?)```',text,re.S):
            commands.extend(line for line in block.strip().splitlines() if line and not line.startswith('#'))
        self.assertEqual(len(commands),2)
        with tempfile.TemporaryDirectory() as temporary:
            for index,line in enumerate(commands):
                args=shlex.split(line);args[0]=sys.executable
                args=[temporary+arg[len('OUTPUT'):] if arg.startswith('OUTPUT') else arg for arg in args]
                result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
                self.assertEqual(result.returncode,index,result.stderr)
                if index==0:
                    self.assertEqual(result.stderr,'')
                    self.assertEqual(json.loads(result.stdout)['schema'],'recap.command-catalog.v1')
                else:
                    self.assertEqual(result.stdout,'')
                    self.assertEqual(json.loads(result.stderr)['code'],'ARCHIVE_ERROR')
                    self.assertFalse((Path(temporary)/'missing.sqlite').exists())

    def test_catalog_parser_metadata_reflects_option(self):
        result=self.invoke(['describe'],True)
        self.assertEqual(result[0],0)
        options=json.loads(result[1])['global_options']
        option=next(value for value in options if value['flags']==['--json-errors'])
        self.assertEqual(option['action'],'store_true')
        self.assertFalse(option['default'])


if __name__=='__main__':
    unittest.main()
