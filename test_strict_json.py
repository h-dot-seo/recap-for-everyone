import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from local_parser import LocalImportError, parse_artifact
from recap import ingest
from session_workflow import import_export
from strict_json import loads


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_members_including_escaped_and_nested_keys(self):
        for value in ('{"id":1,"id":2}', '{"id":1,"\\u0069d":2}',
                      '{"outer":{"private-synthetic-key":1,"private-synthetic-key":2}}'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, '^duplicate JSON object key$'):
                loads(value)

    def test_distinct_objects_and_unicode_values_are_preserved(self):
        text = '[{"id":"한글","parts":["a\\u2028b"]},{"id":"second"}]'
        self.assertEqual(loads(text), json.loads(text))

    def test_normalized_duplicate_rejected_without_creating_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.jsonl'; db = Path(tmp) / 'archive.sqlite'
            path.write_text('\n{"conversation_id":"c","message_id":"m","role":"user",'
                            '"role":"assistant","timestamp":"synthetic","text":"Synthetic"}\n')
            with self.assertRaisesRegex(ValueError, 'line 2'):
                ingest(db, 'demo', path)
            self.assertFalse(db.exists())

    def test_local_nested_duplicate_reports_physical_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.jsonl'; db = Path(tmp) / 'archive.sqlite'
            path.write_bytes(b'{"type":"session_meta","payload":{"id":"synthetic"}}\r\n\r\n'
                             b'{"type":"response_item","payload":{"type":"message","role":"user",'
                             b'"content":[{"text":"Synthetic A","text":"Synthetic B"}]}}\r\n')
            with self.assertRaisesRegex(LocalImportError, ':3') as caught:
                parse_artifact(path, path.name)
            self.assertNotIn('Synthetic A', str(caught.exception))
            with self.assertRaises(LocalImportError):
                import_export(db, 'demo', path, 'local')
            self.assertFalse(db.exists())

    def test_invalid_local_reimport_leaves_archive_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.jsonl'; db = Path(tmp) / 'archive.sqlite'
            import_export(db, 'demo', 'examples/local-session.jsonl', 'local')
            before = db.read_bytes()
            path.write_text('{"type":"session_meta","payload":{"id":"first","id":"second"}}\n')
            with self.assertRaises(LocalImportError):
                import_export(db, 'demo', path, 'local')
            self.assertEqual(db.read_bytes(), before)

    def test_cli_rejects_duplicate_reviewed_revision_before_db_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'reviewed.json'; db = Path(tmp) / 'missing.sqlite'
            path.write_text('{"expected_revision":0,"expected_revision":null,"proposal":{}}')
            result = subprocess.run([sys.executable, 'title_proposal.py', '--db', str(db), 'apply', str(path)],
                                    capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('duplicate JSON object key', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(db.exists())
