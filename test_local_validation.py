"""Synthetic local timestamp and session-boundary validation regressions."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from local_parser import LocalImportError
from recap import ingest
from session_workflow import import_export, normalize


class LocalValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.jsonl'
        self.db = Path(self.tmp.name) / 'archive.sqlite'

    @staticmethod
    def message():
        return dict(type='response_item', payload=dict(type='message', id='m',
                    role='user', content=[dict(type='input_text', text='Synthetic message')]))

    def write(self, message=None, boundary=None):
        records = [dict(type='session_meta', payload=dict(id='first'))]
        if boundary is not None:
            records.append(boundary)
        records.append(self.message() if message is None else message)
        self.path.write_text(''.join(json.dumps(record) + '\n' for record in records), encoding='utf-8')

    def test_valid_timestamp_values_and_missing_timestamp(self):
        for kind in ('local', 'local-codex'):
            self.write()
            self.assertEqual(normalize(self.path, kind)[0]['timestamp'], 'unknown')
            for value, expected in ((None, 'unknown'), (0, '0'), (0.0, '0.0'),
                                    (17, '17'), (1.25, '1.25'), ('synthetic-time', 'synthetic-time')):
                with self.subTest(kind=kind, timestamp=value):
                    message = self.message(); message['timestamp'] = value
                    self.write(message)
                    self.assertEqual(normalize(self.path, kind)[0]['timestamp'], expected)

    def test_invalid_timestamps_rejected_before_database_creation(self):
        for kind in ('local', 'local-codex'):
            for value in ('', False, True, [], {}, {'private': 'SYNTHETIC_PRIVATE'},
                          float('nan'), float('inf'), -float('inf')):
                with self.subTest(kind=kind, timestamp=value):
                    message = self.message(); message['timestamp'] = value
                    self.write(message)
                    with self.assertRaisesRegex(LocalImportError, r'finite number: .*:2$') as caught:
                        import_export(self.db, 'demo', self.path, kind)
                    self.assertNotIn('SYNTHETIC_PRIVATE', str(caught.exception))
                    self.assertFalse(self.db.exists())

    def test_invalid_timestamp_on_empty_text_is_not_silently_ignored(self):
        for kind in ('local', 'local-codex'):
            message = self.message(); message['timestamp'] = False
            message['payload']['content'][0]['text'] = ' '
            self.write(message)
            with self.assertRaises(LocalImportError):
                normalize(self.path, kind)

    def test_corrupt_session_boundaries_cannot_reuse_previous_identity(self):
        for kind in ('local', 'local-codex'):
            for payload in (None, [], 'SYNTHETIC_PRIVATE', False, {}, {'id': 17}):
                with self.subTest(kind=kind, payload=payload):
                    self.write(boundary=dict(type='session_meta', payload=payload))
                    with self.assertRaisesRegex(LocalImportError, r'session metadata .*:2$') as caught:
                        import_export(self.db, 'demo', self.path, kind)
                    self.assertNotIn('SYNTHETIC_PRIVATE', str(caught.exception))
                    self.assertFalse(self.db.exists())

    def test_corrupt_initial_metadata_reports_its_physical_line(self):
        for kind in ('local', 'local-codex'):
            for record in (dict(type='session_meta'), dict(type='session_meta', payload=None),
                           dict(type='session_meta', payload={})):
                self.path.write_text('\n' + json.dumps(record) + '\n' + json.dumps(self.message()) + '\n')
                with self.assertRaisesRegex(LocalImportError, r'session metadata .*:2$'):
                    normalize(self.path, kind)

    def test_valid_session_boundary_and_legacy_identity_alias(self):
        for kind in ('local', 'local-codex'):
            self.write(boundary=dict(type='session_meta', payload=dict(session_id='second')))
            self.assertEqual(normalize(self.path, kind)[0]['conversation_id'], 'second')

    def test_failed_reimports_leave_existing_archive_bytes_unchanged(self):
        self.write()
        import_export(self.db, 'demo', self.path, 'local')
        before = self.db.read_bytes()
        for kind in ('local', 'local-codex'):
            message = self.message(); message['timestamp'] = {}
            for records in ((message, None), (None, dict(type='session_meta', payload=None))):
                self.write(*records)
                with self.assertRaises(LocalImportError):
                    import_export(self.db, 'demo', self.path, kind)
                self.assertEqual(self.db.read_bytes(), before)

    def test_corrected_epoch_zero_conflicts_without_rewriting_legacy_evidence(self):
        message = self.message(); message['timestamp'] = 0
        self.write(message)
        row = normalize(self.path, 'local')[0]; row['timestamp'] = 'unknown'
        legacy = Path(self.tmp.name) / 'legacy.jsonl'
        legacy.write_text(json.dumps(row) + '\n')
        ingest(self.db, 'demo', legacy, provenance=[row])
        before = self.db.read_bytes()
        for kind in ('local', 'local-codex'):
            with self.assertRaisesRegex(ValueError, 'conflicting message identity'):
                import_export(self.db, 'demo', self.path, kind)
            self.assertEqual(self.db.read_bytes(), before)

    def test_cli_errors_are_clean_and_do_not_create_database(self):
        for kind in ('local', 'local-codex'):
            for corruption in ('timestamp', 'boundary'):
                message = self.message()
                if corruption == 'timestamp':
                    message['timestamp'] = {'private': 'SYNTHETIC_PRIVATE'}
                self.write(message, dict(type='session_meta', payload=None) if corruption == 'boundary' else None)
                for script in ('recap.py', 'session_workflow.py'):
                    result = subprocess.run([sys.executable, script, '--db', str(self.db), 'import',
                                             str(self.path), '--format', kind, '--source', 'demo'],
                                            capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(':2', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertNotIn('SYNTHETIC_PRIVATE', result.stderr)
                    self.assertFalse(self.db.exists())


if __name__ == '__main__':
    unittest.main()
