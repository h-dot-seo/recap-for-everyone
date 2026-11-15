"""Offline package-path checks; actual wheel installation is a separate observation."""
from contextlib import closing
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
class PackageEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.cwd=self.root/'empty';self.cwd.mkdir()
        self.env=dict(os.environ,PYTHONPATH=str(ROOT))
    def invoke(self,*args,env=None):
        return subprocess.run([sys.executable,'-m','recaplib',*map(str,args)],cwd=self.cwd,env=env or self.env,capture_output=True,timeout=30)
    def test_module_help_version_and_usage_outside_checkout(self):
        from recaplib import __version__
        r=self.invoke('--version');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout,('recap-for-everyone '+__version__+os.linesep).encode())
        r=self.invoke('--help');self.assertEqual(r.returncode,0);self.assertIn(b'usage: python -m recaplib',r.stdout)
        r=self.invoke('unknown-command');self.assertEqual(r.returncode,2);self.assertIn(b'usage: python -m recaplib',r.stderr)
    def test_synthetic_ingest_find_show_and_database_parity(self):
        path=self.root/'synthetic.jsonl';path.write_text(json.dumps(dict(conversation_id='c',message_id='m',role='user',timestamp='t',text='synthetic orchard'))+'\n',encoding='utf-8')
        a=self.root/'module.sqlite';b=self.root/'root.sqlite'
        for command in (['ingest',path,'--source','s'],['find','orchard'],['show','--source','s','--conversation','c']):
            module=self.invoke('--db',a,*command)
            root=subprocess.run([sys.executable,str(ROOT/'recap.py'),'--db',str(b),*map(str,command)],cwd=self.cwd,env=self.env,capture_output=True)
            self.assertEqual(module.returncode,0,module.stderr);self.assertEqual((module.returncode,module.stdout,module.stderr),(root.returncode,root.stdout,root.stderr))
        with closing(sqlite3.connect(a)) as x,closing(sqlite3.connect(b)) as y:
            tables=[r[0] for r in x.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            for table in tables:self.assertEqual(x.execute('SELECT * FROM "'+table+'"').fetchall(),y.execute('SELECT * FROM "'+table+'"').fetchall())
    def test_package_only_catalog_has_no_checkout_release(self):
        target=self.root/'site';target.mkdir();shutil.copytree(ROOT/'recaplib',target/'recaplib',ignore=shutil.ignore_patterns('__pycache__'))
        env=dict(self.env,PYTHONPATH=str(target));r=self.invoke('describe',env=env)
        self.assertEqual(r.returncode,0,r.stderr);self.assertIsNone(json.loads(r.stdout)['release'])
        self.assertFalse((target/'PUBLICATION_MANIFEST.json').exists())
    def test_metadata_pins_build_only_backend_and_package(self):
        text=(ROOT/'pyproject.toml').read_text(encoding='utf-8')
        self.assertIn('flit_core==3.12.0',text);self.assertIn('flit_core.buildapi',text)
        self.assertRegex(text,r'dynamic\s*=\s*\["version"\]')
        self.assertIn('recap = "recaplib.cli:main"',text);self.assertIn('name = "recaplib"',text)
        self.assertIn('requires-python = ">=3.10"',text)
        from runtime_check import MINIMUM_PYTHON
        self.assertEqual(MINIMUM_PYTHON,(3,10))
        self.assertNotRegex(text,r'(?m)^dependencies\s*=');self.assertNotRegex(text,r'(?m)^(license|authors)\s*=')
        self.assertIn('Private :: Do Not Upload',text)
    def test_root_patch_seam_is_retained_without_mutating_package_globals(self):
        import recap
        from recaplib import cli
        original=cli.ingest
        for module in (recap,cli):
            with patch.object(module,'ingest',side_effect=ValueError('synthetic seam')),patch.object(sys,'argv',['recap','--db','unused','ingest','unused','--source','s']),contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as caught:module.main()
            self.assertEqual(caught.exception.code,1);self.assertEqual(err.getvalue(),'synthetic seam\n')
        self.assertIs(cli.ingest,original)
    def test_root_reexports_stay_available(self):
        import recap
        from recaplib import archive
        for name in ('SCHEMA','_validate_source','ingest','ingest_bytes','readonly','search','validate_normalized'):
            self.assertIs(getattr(recap,name),getattr(archive,name))
        self.assertTrue(callable(recap.build_parser))
    def test_module_negative_execution_error_matches_root_bytes(self):
        args=['--db',self.root/'absent.sqlite','show','--source','s','--conversation','c']
        a=self.invoke(*args);b=subprocess.run([sys.executable,str(ROOT/'recap.py'),*map(str,args)],cwd=self.cwd,env=self.env,capture_output=True)
        self.assertEqual((a.returncode,a.stdout,a.stderr),(b.returncode,b.stdout,b.stderr));self.assertEqual(a.returncode,1)
    def test_offline_guide_and_install_boundaries(self):
        import shlex
        text=(ROOT/'docs/PACKAGE_INSTALL.md').read_text(encoding='utf-8')
        self.assertIn('pipx install git+https://github.com/h-dot-seo/recap-for-everyone.git@main',text)
        self.assertIn('release: null',text)
        blocks=re.findall(r'```sh\n(.*?)```',text,re.S);self.assertEqual(len(blocks),1)
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);self.assertEqual(args[0],'recap');r=self.invoke(*args[1:]);self.assertEqual(r.returncode,0,r.stderr)
