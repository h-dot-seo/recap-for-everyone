"""Test the observer with tiny synthetic suites, never recursive full discovery."""
import contextlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch
from tests import timing


class TimingTests(unittest.TestCase):
    def synthetic(self):
        class Synthetic(unittest.TestCase):
            def test_ok(self):print('PRIVATE_STDOUT');print('PRIVATE_STDERR',file=sys.stderr)
            def test_fail(self):self.fail('PRIVATE_FAILURE')
            def test_error(self):raise RuntimeError('PRIVATE_ERROR')
            @unittest.skip('PRIVATE_SKIP')
            def test_skip(self):pass
            @unittest.expectedFailure
            def test_expected(self):self.fail('PRIVATE_EXPECTED')
            @unittest.expectedFailure
            def test_unexpected(self):pass
        return unittest.defaultTestLoader.loadTestsFromTestCase(Synthetic)

    def test_complete_outcome_counts_no_private_diagnostics(self):
        class Loader:
            def loadTestsFromName(inner,name):return self.synthetic()
        out=io.StringIO();err=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            receipt=timing.observe(['tests.test_timing'],Loader(),iter([0,1,4,6]).__next__)
        self.assertEqual(out.getvalue(),'');self.assertEqual(err.getvalue(),'')
        self.assertEqual(receipt['total'],dict(tests=6,failures=1,errors=1,skipped=1,expected_failures=1,unexpected_successes=1,seconds=6))
        self.assertEqual(receipt['modules'][0]['seconds'],3)
        self.assertFalse(receipt['success']);self.assertNotIn('PRIVATE',json.dumps(receipt))
        self.assertRegex(receipt['interpreter'],r'^\d+\.\d+$')

    def test_fixture_error_is_not_empty_success(self):
        class Broken(unittest.TestCase):
            @classmethod
            def setUpClass(cls):raise RuntimeError('PRIVATE_FIXTURE')
            def test_body(self):pass
        class Loader:
            def loadTestsFromName(inner,name):return unittest.defaultTestLoader.loadTestsFromTestCase(Broken)
        receipt=timing.observe(['tests.test_timing'],Loader())
        self.assertEqual(receipt['total']['tests'],0);self.assertEqual(receipt['total']['errors'],1)
        self.assertFalse(receipt['success']);self.assertNotIn('PRIVATE',json.dumps(receipt))

    def test_selection_rejects_paths_arbitrary_modules_duplicates(self):
        self.assertIn('tests.test_timing',timing.select_modules([]))
        for args in (['os'],['tests.timing'],['tests/test_timing.py'],['../test.py'],['tests.test_absent'],['tests.test_timing']*2):
            with self.assertRaises(ValueError):timing.select_modules(args)

    def test_parent_stdout_json_only_and_failure_exit(self):
        class Loader:
            def loadTestsFromName(inner,name):return self.synthetic()
        receipt=timing.observe(['tests.test_timing'],Loader())
        process=subprocess.CompletedProcess([],1,b'PRIVATE_FD\n'+json.dumps(receipt).encode()+b'\n',b'PRIVATE_CHILD_STDERR')
        out=io.StringIO();err=io.StringIO()
        with patch.object(timing.subprocess,'run',return_value=process),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=timing.main(['tests.test_timing'])
        self.assertEqual(code,1);self.assertEqual(json.loads(out.getvalue()),receipt)
        self.assertEqual(err.getvalue(),'');self.assertNotIn('PRIVATE',out.getvalue())

    def test_incomplete_worker_and_invalid_selection_fixed_failure(self):
        for process in (subprocess.CompletedProcess([],2,b'PRIVATE',b'PRIVATE'),subprocess.CompletedProcess([],0,b'{}',b'')):
            out=io.StringIO()
            with patch.object(timing.subprocess,'run',return_value=process),contextlib.redirect_stdout(out):
                self.assertEqual(timing.main(['tests.test_timing']),1)
            self.assertEqual(json.loads(out.getvalue()),timing._fixed_error())
        with patch.object(timing.subprocess,'run',side_effect=AssertionError('must not launch')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(timing.main(['PRIVATE_PATH']),1)

    def test_real_worker_fd_output_is_not_forwarded(self):
        code="""import os,sys,unittest
from unittest.mock import patch
from tests import timing
class Synthetic(unittest.TestCase):
    def runTest(self):
        os.write(1,b'PRIVATE_FD_OUTPUT')
        os.write(2,b'PRIVATE_FD_ERROR')
        self.fail('PRIVATE_FAILURE')
with patch.object(unittest.TestLoader,'loadTestsFromName',return_value=unittest.TestSuite([Synthetic()])):
    sys.exit(timing._worker_main(['tests.test_timing']))
"""
        process=subprocess.run([sys.executable,'-c',code],cwd=timing.ROOT,capture_output=True,timeout=10)
        self.assertEqual(process.returncode,1)
        self.assertIn(b'PRIVATE_FD_OUTPUT',process.stdout);self.assertIn(b'PRIVATE_FD_ERROR',process.stderr)
        out=io.StringIO()
        with patch.object(timing.subprocess,'run',return_value=process),contextlib.redirect_stdout(out):
            self.assertEqual(timing.main(['tests.test_timing']),1)
        self.assertNotIn('PRIVATE',out.getvalue())
        self.assertEqual(json.loads(out.getvalue())['total']['failures'],1)

    def test_unrepresentable_duration_is_a_fixed_failure_not_traceback(self):
        import copy
        class Loader:
            def loadTestsFromName(inner,name):return unittest.TestSuite()
        receipt=timing.observe(['tests.test_timing'],Loader())
        for target in ('module','total'):
            for seconds in (10**400,-10**400,float('nan'),float('inf'),-float('inf'),True):
                with self.subTest(target=target,kind=type(seconds).__name__):
                    bad=copy.deepcopy(receipt)
                    row=bad['modules'][0] if target=='module' else bad['total']
                    row['seconds']=seconds
                    self.assertFalse(timing._valid_receipt(bad,['tests.test_timing'],0))
                    process=subprocess.CompletedProcess([],0,json.dumps(bad).encode(),b'PRIVATE')
                    out=io.StringIO();err=io.StringIO()
                    with patch.object(timing.subprocess,'run',return_value=process),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                        self.assertEqual(timing.main(['tests.test_timing']),1)
                    self.assertEqual(json.loads(out.getvalue()),timing._fixed_error())
                    self.assertEqual(err.getvalue(),'')

    def test_empty_module_counts_and_corrupted_receipts(self):
        class Loader:
            def loadTestsFromName(inner,name):return unittest.TestSuite()
        receipt=timing.observe(['tests.test_timing'],Loader())
        self.assertEqual(receipt['modules'][0]['tests'],0)
        self.assertEqual(receipt['total']['tests'],0)
        self.assertTrue(timing._valid_receipt(receipt,['tests.test_timing'],0))
        import copy
        for key,value in [('seconds',float('nan')),('errors',1),('tests',True)]:
            bad=copy.deepcopy(receipt);bad['total'][key]=value
            self.assertFalse(timing._valid_receipt(bad,['tests.test_timing'],0))
        bad=copy.deepcopy(receipt);bad['total']['errors']=1;bad['modules'][0]['errors']=1
        self.assertFalse(timing._valid_receipt(bad,['tests.test_timing'],0))

    def test_worker_strict_json_admission_fixed_failure(self):
        class Loader:
            def loadTestsFromName(inner,name):return unittest.TestSuite()
        valid=json.dumps(timing.observe(['tests.test_timing'],Loader())).encode()
        duplicate=valid.replace(b'"success": true',b'"success": false, "success": true')
        self.assertNotEqual(valid,duplicate)
        malformed=[duplicate,b'['*100000+b']'*100000,b'\xff']
        for number in (b'NaN',b'Infinity',b'-Infinity',b'1e999'):
            malformed.append(re.sub(rb'"seconds": [0-9.eE+\-]+',b'"seconds": '+number,valid))
        for raw in malformed:
            process=subprocess.CompletedProcess([],0,raw+b'\n',b'PRIVATE_ERROR')
            out=io.StringIO();err=io.StringIO()
            with patch.object(timing.subprocess,'run',return_value=process),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                self.assertEqual(timing.main(['tests.test_timing']),1)
            self.assertEqual(json.loads(out.getvalue()),timing._fixed_error())
            self.assertEqual(err.getvalue(),'')
        process=subprocess.CompletedProcess([],0,valid+b'\n',b'')
        with patch.object(timing.subprocess,'run',return_value=process),patch.object(timing,'loads',side_effect=RecursionError('PRIVATE_DECODER')),contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(timing.main(['tests.test_timing']),1)
        self.assertEqual(json.loads(out.getvalue()),timing._fixed_error())

    def test_documented_small_command_runs_real_process(self):
        # The guide selects a small independent module, never this module or full
        # discovery, so ordinary discovery cannot recursively time itself.
        guide=(timing.ROOT/'docs/TESTING.md').read_text(encoding='utf-8')
        blocks=re.findall(r'```sh\n(.*?)```',guide,re.S)
        self.assertEqual(blocks,['python -m tests.timing tests.test_cli_harness\n'])
        result=subprocess.run([sys.executable,'-m','tests.timing','tests.test_cli_harness'],cwd=timing.ROOT,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stderr,b'')
        receipt=json.loads(result.stdout);self.assertTrue(receipt['success'])
        self.assertEqual(receipt['total']['tests'],6)
        self.assertEqual([row['module'] for row in receipt['modules']],['tests.test_cli_harness'])
        self.assertNotIn('platform',receipt);self.assertNotIn('path',receipt)


if __name__=='__main__':unittest.main()
