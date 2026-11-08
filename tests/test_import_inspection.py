import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from recaplib.session_workflow import inspect_export, import_export


class ImportInspectionTests(unittest.TestCase):
    def test_web_counts_and_original_hash_without_message_text(self):
        report = inspect_export('examples/web-export.json', 'web')
        self.assertEqual(report['extracted_messages'], 2)
        self.assertEqual(report['role_counts'], {'assistant': 1, 'user': 1})
        self.assertEqual(report['conversations_with_text'], 1)
        self.assertEqual(report['original_sha256'], hashlib.sha256(Path('examples/web-export.json').read_bytes()).hexdigest())
        self.assertFalse(report['contains_message_text'])
        self.assertNotIn('orchard', json.dumps(report))

    def test_local_metadata_and_nonmessage_record_counts(self):
        report = inspect_export('examples/local-session.jsonl', 'local')
        self.assertEqual(report['observed_records'], 2)
        self.assertEqual(report['sessions_in_metadata'], 1)
        self.assertEqual(report['extracted_messages'], 1)
        self.assertEqual(report['records_without_extracted_message'], 1)

    def test_web_nontext_and_empty_nodes_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.json'
            path.write_text(json.dumps([dict(id='synthetic', mapping={
                'root': dict(message=None),
                'image': dict(parent='root', message=dict(author=dict(role='user'),
                    content=dict(parts=[dict(content_type='image_asset_pointer')]))),
            })]))
            report = inspect_export(path, 'web')
            self.assertEqual(report['mapping_nodes'], 2)
            self.assertEqual(report['nodes_without_extracted_text'], 2)
            self.assertEqual(report['extracted_messages'], 0)
            self.assertTrue(report['warnings'])
            self.assertEqual(report['conversations_in_export'], 1)
            self.assertEqual(report['conversations_with_text'], 0)

    def test_import_receipt_includes_same_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'archive.sqlite'
            expected = inspect_export('examples/web-export.json', 'web')
            expected.pop('mode')
            receipt = import_export(db, 'demo', 'examples/web-export.json', 'web')
            self.assertEqual(receipt['inserted'], 2)
            self.assertEqual(receipt['coverage'], expected)

    def test_inspection_rejects_malformed_web_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.json'
            path.write_text(json.dumps([dict(id='synthetic', title=['not text'], mapping={})]))
            with self.assertRaisesRegex(ValueError, 'title must be text'):
                inspect_export(path, 'web')

    def test_cli_inspection_never_opens_supplied_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'never-created.sqlite'
            for prefix in ([], ['--db', str(db)]):
                result = subprocess.run([sys.executable, 'session_workflow.py', *prefix, 'inspect',
                                         'examples/local-session.jsonl', '--format', 'local'],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['extracted_messages'], 1)
                self.assertFalse(db.exists())

    def test_import_still_requires_explicit_database(self):
        result = subprocess.run([sys.executable, 'session_workflow.py', 'import',
                                 'examples/web-export.json', '--format', 'web', '--source', 'demo'],
                                capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--db is required', result.stderr)

    def test_empty_local_session_warns_without_exposing_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.jsonl'
            path.write_text(json.dumps(dict(type='session_meta', payload=dict(id='private-synthetic-label'))) + '\n')
            report = inspect_export(path, 'local')
            self.assertEqual(report['extracted_messages'], 0)
            self.assertEqual(report['reason_code'], 'no_response_messages')
            self.assertTrue(report['warnings'])
            self.assertNotIn('private-synthetic-label', json.dumps(report))
