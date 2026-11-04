"""Execute published workflow arguments with this interpreter, not every shell."""
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('make_review_demo', ROOT / 'examples/make_review_demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class StartHereTests(unittest.TestCase):
    def test_exact_documented_commands_and_review_checkpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'new-demo'
            document = (ROOT / 'docs/START_HERE.md').read_text(encoding='utf-8')
            blocks = re.findall(r'```sh\n(.*?)```', document, re.S)
            outputs = []
            originals = None
            for block in blocks:
                for command in block.strip().splitlines():
                    tokens = shlex.split(command)
                    self.assertEqual(tokens.pop(0), 'python')
                    tokens = [t.replace('../recap-start-demo', str(destination)) for t in tokens]
                    output = None
                    if '>' in tokens:
                        redirect = tokens.index('>')
                        self.assertEqual(redirect, len(tokens) - 2)
                        output = Path(tokens[-1]); tokens = tokens[:redirect]
                    # Model the guide's explicit human review before this synthetic apply.
                    if 'apply-title' in tokens:
                        reviewed = json.loads((destination/'reviewed.json').read_text())
                        self.assertEqual(reviewed['proposal']['source'], 'demo')
                        self.assertEqual(reviewed['proposal']['conversation'], 'web-05')
                        self.assertEqual(reviewed['previous_title'], 'New chat')
                        self.assertEqual(reviewed['expected_revision'], 0)
                        self.assertEqual(reviewed['proposal']['title'], 'Synthetic orchard follow-up')
                    result = subprocess.run([sys.executable, *tokens], cwd=ROOT,
                                            capture_output=True, encoding='utf-8', timeout=30)
                    self.assertEqual(result.returncode, 0, command+'\n'+result.stderr)
                    payload = json.loads(result.stdout); outputs.append((tokens,payload))
                    if output is not None:
                        output.write_text(result.stdout, encoding='utf-8')
                    if tokens[0] == 'examples/make_review_demo.py':
                        originals = {name: (destination/name).read_bytes() for name in ('web.zip','local.jsonl')}
                        self.assertFalse((destination/'archive.sqlite').exists())
            self.assertEqual(len(outputs), 21)
            queue = json.loads((destination/'queue.json').read_text())
            self.assertEqual(queue['total_conversations'],24)
            self.assertEqual(sum(i['status']=='UNAVAILABLE' for i in queue['items']),2)
            deferred = json.loads((destination/'deferred.json').read_text())
            self.assertEqual([i['conversation'] for i in deferred['items']],['web-05'])
            remaining = json.loads((destination/'remaining.json').read_text())
            self.assertEqual(remaining['total_conversations'],23)
            state = next(p for t,p in reversed(outputs) if 'review-state' in t)
            self.assertEqual(state['state'],'open');self.assertEqual(state['recorded_state'],'deferred')
            self.assertTrue(state['stale_decision'])
            searches = [p for t,p in outputs if 'find' in t]
            self.assertEqual([p['total_matches'] for p in searches],[1,12])
            self.assertEqual(originals,{name:(destination/name).read_bytes() for name in originals})
            # Reusing the reviewed apply must fail without modifying the database.
            before=(destination/'archive.sqlite').read_bytes()
            retry=subprocess.run([sys.executable,'recap.py','--db',str(destination/'archive.sqlite'),
                                  'apply-title',str(destination/'reviewed.json')],cwd=ROOT,capture_output=True,timeout=30)
            self.assertNotEqual(retry.returncode,0)
            self.assertEqual((destination/'archive.sqlite').read_bytes(),before)

    def test_generator_refuses_existing_directory_and_never_reads_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'new'
            with patch.object(Path,'read_bytes',side_effect=AssertionError('no input reads')), \
                 patch.object(Path,'read_text',side_effect=AssertionError('no input reads')):
                result=demo.make_demo(target)
            self.assertTrue(result['synthetic_only']);self.assertFalse(result['database_created'])
            before={p.name:p.read_bytes() for p in target.iterdir()}
            with self.assertRaises(FileExistsError):demo.make_demo(target)
            self.assertEqual(before,{p.name:p.read_bytes() for p in target.iterdir()})
            empty=Path(tmp)/'empty';empty.mkdir()
            with self.assertRaises(FileExistsError):demo.make_demo(empty)
            self.assertEqual(list(empty.iterdir()),[])

    def test_generator_failure_is_clean_and_does_not_remove_partial_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing=Path(tmp)/'missing'/'new'
            result=subprocess.run([sys.executable,'examples/make_review_demo.py',str(missing)],
                                  cwd=ROOT,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,1);self.assertNotIn('Traceback',result.stderr)
            self.assertEqual(result.stdout,'');self.assertFalse(missing.exists())
            target=Path(tmp)/'partial'
            with patch.object(demo.zipfile,'ZipFile',side_effect=OSError('synthetic failure')):
                with self.assertRaises(OSError):demo.make_demo(target)
            self.assertTrue(target.is_dir())
            with self.assertRaises(FileExistsError):demo.make_demo(target)
