"""The error guide executes only synthetic missing-path failures."""
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class DiagnosticGuideTests(unittest.TestCase):
    def test_documented_missing_archive_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            guide=(ROOT/'docs/ERROR_DIAGNOSTICS.md').read_text()
            blocks=guide.split('```sh\n')[1:]
            self.assertEqual(len(blocks),1)
            for line in blocks[0].split('```',1)[0].strip().splitlines():
                args=[a.replace('OUTPUT',root.as_posix()) for a in shlex.split(line)]
                self.assertEqual(args[0],'python');args[0]=sys.executable
                p=subprocess.run(args,cwd=ROOT,capture_output=True)
                self.assertEqual(p.returncode,1)
                self.assertEqual(p.stdout,b'')
                self.assertEqual(p.stderr.replace(b'\r\n',b'\n'),b'SQLite operation failed\n')
                self.assertNotIn(str(root).encode(),p.stderr)
                self.assertNotIn(b'Traceback',p.stderr)
                self.assertFalse((root/'missing-private.sqlite').exists())
