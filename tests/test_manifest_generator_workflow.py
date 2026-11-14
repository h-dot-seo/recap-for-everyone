"""Execute the synthetic contributor guide without changing this checkout."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ManifestGeneratorWorkflowTests(unittest.TestCase):
    def test_documented_plan_and_exclusive_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide = (ROOT/'docs/BUILD_MANIFEST.md').read_text()
            blocks = guide.split('```sh\n')[1:]
            self.assertEqual(len(blocks),1)
            results=[];before=None
            for line in blocks[0].split('```',1)[0].strip().splitlines():
                args=[a.replace('OUTPUT',root.as_posix()) for a in shlex.split(line)]
                self.assertEqual(args[0],'python');args[0]=sys.executable
                result=subprocess.run(args,cwd=ROOT,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr)
                results.append(json.loads(result.stdout))
                old=(root/'manifest-demo/PUBLICATION_MANIFEST.json').read_bytes()
                if before is None:before=old
                self.assertEqual(before,old)
            self.assertEqual(results[1]['added'],['added.txt'])
            candidate=json.loads((root/'candidate.json').read_text())
            self.assertEqual([r['path'] for r in candidate['files']],['added.txt','changed.txt'])
            for row in candidate['files']:
                raw=(root/'manifest-demo'/row['path']).read_bytes()
                self.assertEqual(row['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(candidate['license_status'],'NOT_SELECTED')
            last=subprocess.run(args,cwd=ROOT,capture_output=True)
            self.assertNotEqual(last.returncode,0)

    def test_help_documents_actual_usage(self):
        output=subprocess.check_output([sys.executable,str(ROOT/'build_manifest.py'),'--help'],text=True)
        usage=' '.join(output.split('\n\n',1)[0].split())
        self.assertIn(usage,(ROOT/'docs/COMMANDS.md').read_text())
