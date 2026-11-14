"""Execute the synthetic fresh-object rehearsal, not a SQLite copy/self-check."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

from recap import ingest
from recaplib.recovery import declare_recovery, rehearse_recovery

ROOT = Path(__file__).resolve().parents[1]


class RebuildRehearsalTests(unittest.TestCase):
    def test_documented_fresh_replay(self):
        blocks = re.findall(r'```sh\n(.*?)```', (ROOT / 'docs/REBUILD_REHEARSAL.md').read_text(encoding='utf-8'), re.S)
        self.assertEqual(len(blocks), 1)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'fresh output'
            output.mkdir()
            live = output / 'archive.sqlite'
            rebuilt = output / 'rebuilt.sqlite'
            reference = None
            results = []
            for index, line in enumerate(blocks[0].strip().splitlines()):
                tokens = shlex.split(line)
                self.assertEqual(tokens[:2], ['python', 'recap.py'])
                if index == 0:
                    self.assertFalse(live.exists())
                if index == 2:
                    self.assertFalse(rebuilt.exists())
                    self.assertTrue(live.is_file())
                    reference = hashlib.sha256(live.read_bytes()).hexdigest()
                argv = [sys.executable] + [token.replace('OUTPUT', str(output)) for token in tokens[1:]]
                run = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=60,
                                     env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0'))
                self.assertEqual(run.returncode, 0, line + '\n' + run.stderr.decode('utf-8'))
                self.assertEqual(run.stderr, b'')
                self.assertTrue(run.stdout.isascii())
                results.append(json.loads(run.stdout))
                if reference is not None:
                    self.assertEqual(hashlib.sha256(live.read_bytes()).hexdigest(), reference)
            self.assertEqual(len(results), 4)
            self.assertFalse(os.path.samefile(live, rebuilt))
            receipt = json.loads((output / 'rebuild-receipt.json').read_bytes())
            self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_PASSED')
            self.assertEqual(receipt['restored']['path'], str(output) + '/rebuilt.sqlite')
            checks = {item['check']: item for item in receipt['checks']}
            for name in ['artifact_rows', 'messages_digest', 'source_counts', 'fts_rows', 'fts_match_sample', 'declared_objects']:
                self.assertEqual(checks[name]['status'], 'PASS', name)
            self.assertEqual(checks['fts_rows']['fts_rows'], 2)
            self.assertTrue(checks['fts_match_sample']['matched'])
            for field in ['clean_destination_verified', 'remote_backup_verified', 'decryption_keys_verified', 'future_restore_verified']:
                self.assertEqual(receipt[field], 'NOT_ESTABLISHED')
            self.assertFalse(receipt['restored_archive_written'])
            self.assertFalse(receipt['contains_message_text'])

    def test_different_source_is_not_a_successful_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ingest(root / 'live.sqlite', 'demo', ROOT / 'examples/conversations.jsonl')
            declare_recovery(root / 'live.sqlite', root / 'manifest.json')
            ingest(root / 'rebuilt.sqlite', 'other', ROOT / 'examples/conversations.jsonl')
            result = rehearse_recovery(root / 'manifest.json', root / 'rebuilt.sqlite', root / 'receipt.json')
            self.assertEqual(result['status'], 'RECOVERY_REHEARSAL_FAILED')
            self.assertIn('messages_digest', result['failed_checks'])
            self.assertTrue((root / 'receipt.json').is_file())

    def test_missing_retained_object_is_not_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'empty objects').mkdir()
            for name in ['live.sqlite', 'rebuilt.sqlite']:
                ingest(root / name, 'demo', ROOT / 'examples/conversations.jsonl')
            declare_recovery(root / 'live.sqlite', root / 'manifest.json')
            result = rehearse_recovery(root / 'manifest.json', root / 'rebuilt.sqlite', root / 'receipt.json',
                                      objects=root / 'empty objects')
            self.assertEqual(result['status'], 'RECOVERY_REHEARSAL_FAILED')
            self.assertIn('declared_objects', result['failed_checks'])


if __name__ == '__main__':
    unittest.main()
