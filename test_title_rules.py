import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from session_workflow import import_export, titles
from title_proposal import preview, snapshot
from title_rules import validate_title


class TitleRulesTests(unittest.TestCase):
    def test_control_and_unicode_line_breaks_are_rejected(self):
        for separator in ('\n', '\r', '\t', '\x00', '\x7f', '\x85', '\u2028', '\u2029', '\ud800'):
            with self.subTest(separator=separator), self.assertRaises(ValueError):
                validate_title('Synthetic' + separator + 'title')
        for value in ('', ' ', 'x' * 201, 123, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_title(value)

    def test_unicode_emoji_and_valid_boundaries_are_preserved(self):
        for title in ('합성 과수원 계획', 'Synthetic 👩‍🔬 plan', 'x' * 200, ' Padded title '):
            self.assertEqual(validate_title(title), title)

    def test_both_write_paths_reject_without_modifying_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'archive.sqlite'
            import_export(db, 'demo', 'examples/web-export.json', 'web')
            _, digest = snapshot(db, 'demo', 'synthetic-chat')
            before = db.read_bytes()
            for title in ('Synthetic\nplan', 'Synthetic\u2028plan', 'Synthetic\x7fplan'):
                with self.assertRaises(ValueError):
                    titles(db, 'demo', 'synthetic-chat', title, 0)
                proposal = dict(source='demo', conversation='synthetic-chat', content_sha256=digest,
                                title=title, provider='operator', evidence_message_ids=['m1'])
                with self.assertRaises(ValueError):
                    preview(db, proposal)
            self.assertEqual(db.read_bytes(), before)
            self.assertEqual(titles(db, 'demo', 'synthetic-chat')['revision'], 0)

    def test_title_update_never_creates_a_missing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'missing.sqlite'
            with self.assertRaises(sqlite3.OperationalError):
                titles(db, 'demo', 'synthetic', 'Synthetic plan', 0)
            self.assertFalse(db.exists())
            result = subprocess.run([sys.executable, 'session_workflow.py', '--db', str(db), 'title',
                                     '--source', 'demo', '--conversation', 'synthetic', '--set', 'Synthetic plan',
                                     '--expected-revision', '0'], capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(db.exists())

    def test_existing_database_uri_escapes_percent_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'synthetic%23#archive.sqlite'
            import_export(db, 'demo', 'examples/web-export.json', 'web')
            result = titles(db, 'demo', 'synthetic-chat', 'Synthetic reviewed title', 0)
            self.assertEqual(result['display_title'], 'Synthetic reviewed title')
