"""Every public standalone product parser: real-process opt-in parity."""
import contextlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import shutil
import sqlite3
import sys
import unittest
from unittest.mock import patch

from tests import test_command_effects as fixtures
from tests.test_command_effects import tree_bytes
from recaplib import errors

ROOT=Path(__file__).resolve().parents[1]
NAMES=('attributed_title','branch_title','conversation_search','conversation_view',
       'export_inventory','import_check','recovery','replay_local','replay_title',
       'session_workflow','title_adapter','title_history','title_plan','title_proposal',
       'title_suggestion','web_branch')


class StandaloneJsonErrorsTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.CommandEffectsTests();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f=self.fixture

    def call(self,name,args,enabled=False):
        return subprocess.run([sys.executable,str(ROOT/(name+'.py'))]+
            (['--json-errors'] if enabled else [])+[str(a) for a in args],
            cwd=ROOT,capture_output=True,timeout=30)

    def cases(self):
        f=self.f;db=['--db',f.db];web=['--source','web','--conversation','synthetic-chat']
        return {
            'attributed_title':db+[f.attributed,'--source','attributed','--conversation','synthetic-attributed'],
            'branch_title':db+[f.web,'--node','m2']+web,
            'conversation_search':db+['synthetic'],
            'conversation_view':db+['show']+web,
            'export_inventory':[f.web,'--format','web'],
            'import_check':db+[f.web,'--source','web','--format','web'],
            'recovery':['declare','--db',f.db,'--output',f.root/'declaration.json'],
            'replay_local':[f.replay],
            'replay_title':db+[f.replay,'--source','replay','--conversation','synthetic-rollout'],
            'session_workflow':['inspect',f.web,'--format','web'],
            'title_adapter':db+web+['prepare'],
            'title_history':db+web,
            'title_plan':db+['export',f.web,'--format','web']+web,
            'title_proposal':db+['snapshot']+web,
            'title_suggestion':db+web,
            'web_branch':[f.web,'--conversation','synthetic-chat','--node','m2'],
        }

    def test_every_parser_success_stdout_and_existing_tree_preserved(self):
        cases=self.cases();self.assertEqual(set(cases),set(NAMES))
        for name,args in cases.items():
            with self.subTest(name=name):
                before=tree_bytes(self.f.root)
                plain=self.call(name,args)
                self.assertEqual(plain.returncode,0,plain.stderr);self.assertEqual(plain.stderr,b'')
                json.loads(plain.stdout)
                if name=='recovery':
                    first=(self.f.root/'declaration.json').read_bytes()
                    args=list(args);args[-1]=self.f.root/'declaration-optin.json'
                encoded=self.call(name,args,True)
                self.assertEqual((encoded.returncode,encoded.stdout,encoded.stderr),(0,plain.stdout,b''))
                if name=='recovery':
                    self.assertEqual(first,(self.f.root/'declaration-optin.json').read_bytes())
                    # These two explicitly requested files are the only effects.
                    after=tree_bytes(self.f.root)
                    self.assertEqual(set(after)-set(before),{'declaration.json','declaration-optin.json'})
                    for key,value in before.items():self.assertEqual(after[key],value)
                else:self.assertEqual(before,tree_bytes(self.f.root))

    def test_all_caught_boundaries_envelope_only_changes_stderr(self):
        cases=self.cases();missing=self.f.root/'PRIVATE_MISSING'
        for name,args in cases.items():
            if name=='replay_local':continue # unsupported is an existing result, not a caught error
            args=[missing if a==self.f.db or a==self.f.web or a==self.f.attributed or a==self.f.replay else a for a in args]
            if name=='title_adapter':args=['--kind','mock','--timeout','-1']+args
            with self.subTest(name=name):
                before=tree_bytes(self.f.root)
                plain=self.call(name,args);encoded=self.call(name,args,True)
                self.assertEqual((plain.returncode,plain.stdout),(1,b''),plain.stderr)
                self.assertEqual((encoded.returncode,encoded.stdout),(1,b''),encoded.stderr)
                value=json.loads(encoded.stderr)
                self.assertEqual(len(encoded.stderr.splitlines()),1)
                self.assertEqual(set(value),{'schema','code','message','exit_status'})
                self.assertEqual(value['schema'],'recap.error.v1');self.assertEqual(value['exit_status'],1)
                self.assertEqual(value['message'],plain.stderr.decode('ascii').removesuffix('\r\n').removesuffix('\n'))
                self.assertNotIn('PRIVATE_MISSING',encoded.stderr.decode('ascii'))
                self.assertNotIn('Traceback',encoded.stderr.decode('ascii'))
                if name=='title_adapter':self.assertEqual(value['code'],'CONFIG_INVALID')
                self.assertEqual(before,tree_bytes(self.f.root))

    def test_usage_errors_stay_plain_exit_two_for_all_parsers(self):
        for name in NAMES:
            with self.subTest(name=name):
                for enabled in (False,True):
                    result=self.call(name,['--not-a-real-option'],enabled)
                    self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,b'')
                    self.assertTrue(result.stderr.startswith(b'usage:'))
                    self.assertNotIn(b'Traceback',result.stderr)

    def test_replay_and_conflicts_stay_negative_stdout_results(self):
        f=self.f
        for name,args in [('replay_local',[f.unsupported]),
                          ('import_check',['--db',f.db,f.conflict,'--source','web','--format','web'])]:
            before=tree_bytes(f.root);plain=self.call(name,args);encoded=self.call(name,args,True)
            self.assertEqual((plain.returncode,plain.stderr),(1,b''))
            self.assertEqual((encoded.returncode,encoded.stdout,encoded.stderr),(1,plain.stdout,b''))
            self.assertIsInstance(json.loads(encoded.stdout),dict)
            self.assertEqual(before,tree_bytes(f.root))

    def test_failed_recovery_result_remains_stdout_and_saved_receipt(self):
        from recaplib import recovery
        f=self.f;manifest=f.root/'recovery-manifest.json'
        recovery.declare_recovery(f.db,manifest)
        restored=f.root/'restored.sqlite';shutil.copyfile(f.db,restored)
        connection=sqlite3.connect(restored)
        try:
            with connection:connection.execute("UPDATE messages SET timestamp='synthetic changed'")
        finally:connection.close()
        before=restored.read_bytes();results=[];receipts=[]
        for enabled in (False,True):
            output=f.root/('receipt-optin.json' if enabled else 'receipt-plain.json')
            result=self.call('recovery',['rehearse',manifest,'--restored-db',restored,'--output',output],enabled)
            self.assertEqual((result.returncode,result.stderr),(1,b''))
            self.assertEqual(json.loads(result.stdout)['status'],'RECOVERY_REHEARSAL_FAILED')
            results.append(result.stdout);receipts.append(output.read_bytes())
            self.assertEqual(restored.read_bytes(),before)
        self.assertEqual(results[0],results[1]);self.assertEqual(receipts[0],receipts[1])

    def test_late_failure_does_not_claim_rollback_or_remove_published_file(self):
        from recaplib import recovery
        from tests._cli import run_cli
        original=recovery.declare_recovery
        for enabled in (False,True):
            output=self.f.root/('published-optin.json' if enabled else 'published-plain.json')
            def after_publication(*args,**kwargs):
                original(*args,**kwargs)
                raise OSError('PRIVATE_LATE_FAILURE')
            with patch.object(recovery,'declare_recovery',side_effect=after_publication):
                result=run_cli(recovery.main,(['--json-errors'] if enabled else [])+
                    ['declare','--db',str(self.f.db),'--output',str(output)])
            self.assertEqual(result.returncode,1);self.assertEqual(result.stdout,'')
            self.assertTrue(output.is_file());self.assertIsInstance(json.loads(output.read_bytes()),dict)
            self.assertNotIn('PRIVATE',result.stderr)
            if enabled:
                value=json.loads(result.stderr)
                self.assertEqual(value['code'],'FILE_ERROR')
                self.assertNotIn('archive_mutation',value)
            else:self.assertEqual(result.stderr,'Filesystem operation failed\n')

    def test_typed_and_adapter_codes_retain_explicit_meaning(self):
        # Unexpected exceptions are not newly caught by ordinary standalone mains.
        from recaplib import title_history, title_adapter
        from tests._cli import run_cli
        args=['--json-errors','--db','unused','--source','s','--conversation','c']
        with patch.object(title_history,'history',side_effect=errors.Stale('fixed stale message')):
            result=run_cli(title_history.main,args)
        self.assertEqual(json.loads(result.stderr)['code'],'STALE')
        with patch.object(title_history,'history',side_effect=RuntimeError('synthetic unexpected')):
            result=run_cli(title_history.main,args)
        self.assertIn('Traceback',result.stderr);self.assertNotIn('recap.error.v1',result.stderr)
        with patch.object(title_adapter,'prepare_request',side_effect=RuntimeError('PRIVATE_ADAPTER')):
            result=run_cli(title_adapter.main,args+['prepare'])
        self.assertEqual(json.loads(result.stderr),dict(schema='recap.error.v1',code='PROVIDER_FAILED',message='PROVIDER_FAILED',exit_status=1))
        self.assertNotIn('PRIVATE',result.stderr)


if __name__=='__main__':unittest.main()
