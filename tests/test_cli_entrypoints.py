"""Retain actual interpreter/bootstrap coverage for every root CLI main."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
ENTRYPOINTS=('attributed_title.py','benchmark.py','branch_title.py','build_manifest.py',
             'conversation_search.py','conversation_view.py','export_inventory.py','import_check.py',
             'recap.py','recovery.py','replay_local.py','replay_title.py','runtime_check.py',
             'session_workflow.py','title_adapter.py','title_history.py','title_plan.py',
             'title_proposal.py','title_suggestion.py','web_branch.py')


class CliEntrypointTests(unittest.TestCase):
    def test_all_root_main_entrypoints_are_covered(self):
        found=set()
        for path in ROOT.glob('*.py'):
            tree=ast.parse(path.read_text(encoding='utf-8'))
            if any(isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name=='main' or
                   isinstance(node,ast.ImportFrom) and any(alias.asname=='main' or alias.name=='main' and alias.asname is None for alias in node.names)
                   for node in tree.body):
                found.add(path.name)
        self.assertEqual(found,set(ENTRYPOINTS))
        self.assertEqual(len(found),20)

    def run_process(self,name,*arguments):
        return subprocess.run([sys.executable,str(ROOT/name),*arguments],cwd=ROOT,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,
            env=dict(os.environ,PYTHONIOENCODING='ascii',PYTHONDONTWRITEBYTECODE='1'))

    def test_actual_help_bootstrap_all_entrypoints(self):
        for name in ENTRYPOINTS:
            with self.subTest(entrypoint=name):
                result=self.run_process(name,'--help')
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stderr,b'')
                self.assertIn('usage:',result.stdout.decode('ascii'))

    def test_actual_ascii_usage_failures_all_entrypoints(self):
        for name in ENTRYPOINTS:
            with self.subTest(entrypoint=name):
                result=self.run_process(name,'--unknown-synthetic-한글')
                self.assertEqual(result.returncode,2,result.stderr)
                self.assertEqual(result.stdout,b'')
                diagnostic=result.stderr.decode('ascii')
                self.assertIn('error:',diagnostic)
                self.assertNotIn('Traceback',diagnostic)


if __name__=='__main__':
    unittest.main()
