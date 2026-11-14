"""Harness behavior is tested independently from application entrypoints."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

from tests._cli import run_cli, ROOT


class CliHarnessTests(unittest.TestCase):
    def test_success_argv_cwd_and_sequential_restoration(self):
        saved=sys.argv,os.getcwd(),sys.stdout,sys.stderr
        with tempfile.TemporaryDirectory() as temporary:
            for value in ('first','second','\ud800'):
                def main():
                    self.assertEqual(sys.argv[1:],[value])
                    self.assertEqual(Path.cwd(),Path(temporary).resolve())
                    print('result');print('warning',file=sys.stderr)
                result=run_cli(main,[value],cwd=temporary)
                self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'result\n','warning\n'))
                self.assertIs(sys.argv,saved[0]);self.assertEqual(os.getcwd(),saved[1])
                self.assertIs(sys.stdout,saved[2]);self.assertIs(sys.stderr,saved[3])

    def test_system_exit_variants_and_integer_return(self):
        for code,expected,stderr in ((None,0,''),(0,0,''),(7,7,''),('problem',1,'problem\n'),('한글',1,'\\ud55c\\uae00\n')):
            def main():raise SystemExit(code)
            result=run_cli(main,[])
            self.assertEqual((result.returncode,result.stdout,result.stderr),(expected,'',stderr))
        self.assertEqual(run_cli(lambda:4,[]).returncode,4)
        self.assertEqual(run_cli(lambda:'not exit status',[]).returncode,0)

    def test_stdout_ascii_enforced_at_write_and_stderr_backslashreplace(self):
        reached=[]
        def catches_write():
            try:print('한글')
            except UnicodeEncodeError:reached.append('caught-at-write')
            print('ASCII')
            print('한글',file=sys.stderr)
        result=run_cli(catches_write,[])
        self.assertEqual(reached,['caught-at-write'])
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,'ASCII\n','\\ud55c\\uae00\n'))
        def uncaught():print('한글')
        result=run_cli(uncaught,[])
        self.assertEqual(result.returncode,1)
        self.assertIn('UnicodeEncodeError',result.stderr)
        result.stderr.encode('ascii')

    def test_uncaught_traceback_and_failure_restores_globals(self):
        saved=sys.argv,os.getcwd(),sys.stdout,sys.stderr
        def fail():raise ValueError('synthetic 한글 failure')
        result=run_cli(fail,[])
        self.assertEqual(result.returncode,1)
        self.assertIn('Traceback',result.stderr)
        self.assertIn('ValueError: synthetic \\ud55c\\uae00 failure',result.stderr)
        self.assertIs(sys.argv,saved[0]);self.assertEqual(os.getcwd(),saved[1])
        self.assertIs(sys.stdout,saved[2]);self.assertIs(sys.stderr,saved[3])
        with tempfile.TemporaryDirectory() as temporary:
            result=run_cli(fail,[],cwd=Path(temporary)/'missing')
        self.assertEqual(result.returncode,1)
        self.assertIn('FileNotFoundError',result.stderr)
        self.assertEqual(os.getcwd(),saved[1])

    def test_real_text_stream_properties_and_flush(self):
        def main():
            self.assertEqual(sys.stdout.encoding,'ascii')
            self.assertEqual(sys.stdout.errors,'strict')
            self.assertEqual(sys.stderr.errors,'backslashreplace')
            sys.stdout.write('direct');sys.stdout.flush()
            sys.stdout.buffer.write(b' bytes')
        result=run_cli(main,[])
        self.assertEqual(result.stdout,'direct bytes')
        self.assertEqual(result.returncode,0)


if __name__=='__main__':
    unittest.main()
