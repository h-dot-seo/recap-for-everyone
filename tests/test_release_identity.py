"""CLI identity and declared release agreement, not authenticity or a tag policy."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import recap
from recaplib import __version__
from recaplib.command_catalog import describe
from tests._cli import run_cli

ROOT=Path(__file__).resolve().parents[1]


def release_matches(version,release):
    return release==version or release.startswith(version+'-')


class ReleaseIdentityTests(unittest.TestCase):
    def test_declared_release_labels_agree(self):
        self.assertRegex(__version__,r'^\d+\.\d+\.\d+$')
        release=json.loads((ROOT/'PUBLICATION_MANIFEST.json').read_text(encoding='utf-8'))['release']
        current=re.search(r'^Current release: `([^`]+)`', (ROOT/'VALIDATION.md').read_text(encoding='utf-8'),re.M).group(1)
        labels=re.findall(r'^## .*\((\d+\.\d+\.\d+(?:-[a-z0-9-]+)?)\):?$',(ROOT/'docs/VALIDATION_HISTORY.md').read_text(encoding='utf-8'),re.M)
        self.assertTrue(release_matches(__version__,release),( __version__,release))
        self.assertEqual(current,release);self.assertTrue(labels);self.assertEqual(labels[-1],release)

    def test_numeric_boundary_not_plain_prefix(self):
        for label in ('0.99.5','0.99.5-cli-version'):self.assertTrue(release_matches('0.99.5',label))
        for label in ('0.99.50','0.99.50-cli-version','0.99.4','v0.99.5'):self.assertFalse(release_matches('0.99.5',label))

    def test_version_output_and_catalog_option(self):
        for args in (['--version'],['--db','PRIVATE_MISSING','--version'],['--json-errors','--version']):
            result=run_cli(recap.main,args)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'recap-for-everyone '+__version__+'\n');self.assertEqual(result.stderr,'')
        self.assertIn('--version',{flag for option in describe(recap.build_parser())['global_options'] for flag in option['flags']})

    def test_no_io_after_imports_and_parser_initialization(self):
        # Imports themselves read Python source/bytecode. Warm those normal imports
        # first, then audit the actual version dispatch for all opens/DB/network.
        code="""import sys, argparse, contextlib, io
# Exercise the standard-library version formatter before installing the audit.
# This resolves interpreter-specific lazy imports without calling recap version.
warm = argparse.ArgumentParser()
warm.add_argument('--version', action='version', version='synthetic')
with contextlib.redirect_stdout(io.StringIO()):
    try: warm.parse_args(['--version'])
    except SystemExit: pass
import recap
from recaplib import command_catalog, title_document_output
recap.build_parser()
def guard(event,args):
    if event in ('open','sqlite3.connect','socket.connect','socket.__new__'):
        raise AssertionError('version dispatch performed IO')
sys.addaudithook(guard)
sys.argv=['recap.py','--db','PRIVATE_MISSING','--version']
recap.main()
"""
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,('recap-for-everyone '+__version__+'\n').encode());self.assertEqual(result.stderr,b'')

    def test_real_process_other_cwd_missing_manifest_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);copy=root/'copy';copy.mkdir()
            shutil.copyfile(ROOT/'recap.py',copy/'recap.py')
            shutil.copytree(ROOT/'recaplib',copy/'recaplib',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            cwd=root/'elsewhere';cwd.mkdir();marker=cwd/'original';marker.write_bytes(b'unchanged')
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result=subprocess.run([sys.executable,'-B',str(copy/'recap.py'),'--version'],cwd=cwd,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,('recap-for-everyone '+__version__+'\n').encode());self.assertEqual(result.stderr,b'')
            self.assertFalse((copy/'PUBLICATION_MANIFEST.json').exists())
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_version_docs_preserve_existing_shell_blocks(self):
        for path,digest in SH_FENCES.items():
            raw=(ROOT/path).read_bytes()
            self.assertEqual(hashlib.sha256(b''.join(re.findall(rb'```sh\n.*?```',raw,re.S))).hexdigest(),digest)
            self.assertIn(('recap-for-everyone '+__version__).encode(),raw)


SH_FENCES = {'docs/COMMANDS.md': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'docs/INSTALL.md': '41c15fb0379791df44f9b873a5d88b3d514f84988564e2b06d9c518515cb10e5'}

if __name__=='__main__':unittest.main()
