"""Selected caught exception diagnostics, not a universal error sanitizer."""
import contextlib
import importlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recaplib.cli_errors import safe_diagnostic

ROOT = Path(__file__).resolve().parents[1]
COMMON = ['--db', 'synthetic-db', '--source', 'synthetic-source', '--conversation', 'synthetic-conversation']
CASES = [
    ('recap', 'ingest', ['--db', 'synthetic-db', 'ingest', 'synthetic-input', '--source', 'synthetic-source'], True),
    ('recaplib.attributed_title', 'suggest_attributed', COMMON + ['synthetic-input'], True),
    ('recaplib.branch_title', 'suggest_branch', COMMON + ['synthetic-input'], True),
    ('recaplib.conversation_search', 'find', ['--db', 'synthetic-db', 'synthetic-query'], True),
    ('recaplib.conversation_view', 'conversations', ['--db', 'synthetic-db', 'list', '--source', 'synthetic-source'], True),
    ('recaplib.export_inventory', 'list_export', ['synthetic-input', '--format', 'web'], False),
    ('recaplib.import_check', 'check_import', ['--db', 'synthetic-db', 'synthetic-input', '--source', 'synthetic-source', '--format', 'web'], True),
    ('recaplib.recovery', 'declare_recovery', ['declare', '--db', 'synthetic-db', '--output', 'synthetic-output'], True),
    ('recaplib.replay_title', 'suggest_replay', COMMON + ['synthetic-input'], True),
    ('recaplib.session_workflow', 'inspect_export', ['inspect', 'synthetic-input', '--format', 'web'], True),
    ('recaplib.title_history', 'history', COMMON, True),
    ('recaplib.title_plan', 'make_plan', ['--db', 'synthetic-db', 'export', 'synthetic-input', '--format', 'web', '--source', 'synthetic-source', '--conversation', 'synthetic-conversation'], True),
    ('recaplib.title_proposal', 'read_document', ['--db', 'synthetic-db', 'preview', 'synthetic-input'], True),
    ('recaplib.title_suggestion', 'suggest', COMMON, True),
    ('recaplib.web_branch', 'branch_view', ['synthetic-input', '--conversation', 'synthetic-conversation'], False),
]


class CliDiagnosticsTests(unittest.TestCase):
    def test_kind_order_and_existing_application_messages(self):
        errors = [(OSError('PRIVATE_OS_MARKER'), 'Filesystem operation failed'),
                  (sqlite3.OperationalError('PRIVATE_SQL_MARKER'), 'SQLite operation failed'),
                  (json.JSONDecodeError('PRIVATE_JSON_MARKER', 'PRIVATE_DOCUMENT', 1), 'JSON decoding failed'),
                  (UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'PRIVATE_DECODE_MARKER'), 'Text decoding failed')]
        for error, expected in errors:
            self.assertEqual(safe_diagnostic(error), expected)
        for error in (ValueError('fixed value contract'), TypeError('fixed type contract'), KeyError('fixed key contract'), UnicodeError('fixed unicode contract')):
            self.assertEqual(safe_diagnostic(error), str(error))

    def test_exact_code_authored_os_messages_only(self):
        messages = ('output path already exists; choose a new file name',
                    'incomplete recovery document write', 'incomplete document write',
                    'rebuilt database was published; receipt publication failed; database was preserved; '
                    'inspect the requested new database before retrying')
        for message in messages:
            self.assertEqual(safe_diagnostic(OSError(message)), message)
            self.assertEqual(safe_diagnostic(FileExistsError(message)), message)
            self.assertEqual(safe_diagnostic(OSError(5, message, 'PRIVATE_PATH')), 'Filesystem operation failed')
            self.assertEqual(safe_diagnostic(OSError(message + ' PRIVATE_PAYLOAD')), 'Filesystem operation failed')
        self.assertEqual(safe_diagnostic(OSError(['PRIVATE_PAYLOAD'])), 'Filesystem operation failed')
        message = 'read-only SQLite protections could not be enabled'
        self.assertEqual(safe_diagnostic(sqlite3.DatabaseError(message)), message)
        self.assertEqual(safe_diagnostic(sqlite3.DatabaseError(message + ' PRIVATE')), 'SQLite operation failed')

    def test_every_existing_catch_uses_helper_without_expanding_catches(self):
        errors = [OSError('PRIVATE_OS_MARKER'), json.JSONDecodeError('PRIVATE_JSON_MARKER', 'PRIVATE_DOCUMENT', 1),
                  UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'PRIVATE_DECODE_MARKER'), ValueError('fixed application contract')]
        for name, operation, argv, catches_sqlite in CASES:
            module = importlib.import_module(name)
            for error in errors + ([sqlite3.OperationalError('PRIVATE_SQL_MARKER')] if catches_sqlite else []):
                with self.subTest(module=name, error=type(error).__name__):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with patch.object(module, operation, side_effect=error), patch.object(sys, 'argv', [name] + argv), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as exit_info:
                            module.main()
                    self.assertEqual(exit_info.exception.code, 1)
                    self.assertEqual(stdout.getvalue(), '')
                    self.assertEqual(stderr.getvalue(), safe_diagnostic(error) + '\n')
            if not catches_sqlite:
                with patch.object(module, operation, side_effect=sqlite3.Error('uncaught sentinel')), patch.object(sys, 'argv', [name] + argv):
                    with self.assertRaises(sqlite3.Error):
                        module.main()

    def run_cli(self, module, args):
        return subprocess.run([sys.executable, '-m', module] + [str(a) for a in args], cwd=ROOT, capture_output=True, text=True)

    def assert_failure(self, result, expected, *private):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, expected + '\n')
        for value in private:
            self.assertNotIn(value, result.stderr)

    def test_actual_missing_json_decode_and_utf8_unified_and_standalone(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-private-path-') as tmp:
            root=Path(tmp); missing=root/'PRIVATE_MISSING_INPUT'
            commands=[('recap',['web-branch',missing,'--conversation','synthetic']),
                      ('recaplib.web_branch',[missing,'--conversation','synthetic'])]
            for module,args in commands:
                self.assert_failure(self.run_cli(module,args),'Filesystem operation failed',str(root),missing.name)
            path=root/'PRIVATE_PLAN_INPUT'
            for raw,expected in [(b'{"PRIVATE_JSON_BODY":', 'JSON decoding failed'),(b'\xffPRIVATE_BYTES','Text decoding failed')]:
                path.write_bytes(raw)
                # title-plan reads raw UTF-8 and strict JSON at its existing catch.
                self.assert_failure(self.run_cli('recaplib.title_plan',['--db','unused','check','unused',path]),expected,str(root),'PRIVATE')

    def test_actual_sqlite_errors_do_not_echo_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'PRIVATE_SQLITE_PATH'
            connection=sqlite3.connect(path)
            try:
                connection.execute('CREATE TABLE harmless (value TEXT)')
                connection.commit()
            finally:
                connection.close()
            for module,args in [('recap',['--db',path,'stats']),('recaplib.conversation_search',['--db',path,'synthetic'])]:
                self.assert_failure(self.run_cli(module,args),'SQLite operation failed','PRIVATE_SQLITE_PATH','no such table')

    def test_actual_rebuild_published_db_receipt_failure_keeps_warning(self):
        import recap
        from recaplib import recovery
        from tests.test_rebuild_archive import RebuildTests
        fixture = RebuildTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.declare([fixture.step()])
        original = fixture.live.read_bytes()
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ['recap', 'rebuild-archive', str(fixture.manifest), '--plan', str(fixture.plan),
                '--objects', str(fixture.objects), '--new-db', str(fixture.db), '--output', str(fixture.output)]
        with patch.object(recovery, '_publish_new_file', side_effect=OSError('PRIVATE_RECEIPT_FAILURE')), patch.object(sys, 'argv', argv), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exit_info:
                recap.main()
        self.assertEqual(exit_info.exception.code, 1)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(stderr.getvalue(), 'rebuilt database was published; receipt publication failed; database was preserved; inspect the requested new database before retrying\n')
        self.assertNotIn(str(fixture.root), stderr.getvalue())
        self.assertNotIn('PRIVATE_RECEIPT_FAILURE', stderr.getvalue())
        self.assertTrue(fixture.db.is_file())
        self.assertFalse(fixture.output.exists())
        self.assertEqual(fixture.live.read_bytes(), original)
        self.assertFalse(list(fixture.root.glob('.recap-*')))
        connection = sqlite3.connect(fixture.db)
        try:
            self.assertGreater(connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 0)
        finally:
            connection.close()

    def test_title_output_missing_parent_and_collision_no_leak(self):
        from recaplib.archive import ingest_bytes
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); db=root/'archive.sqlite'
            ingest_bytes(db,'synthetic',b'{"conversation_id":"c","message_id":"m","role":"user","text":"synthetic user topic","timestamp":"2026-01-01"}\n')
            collision=root/'PRIVATE_COLLISION'; collision.write_text('preserve',encoding='utf-8')
            absent=root/'PRIVATE_PARENT'/'out.json'
            for output in (collision,absent):
                for module,args in [('recap',['--db',db,'suggest-title','--source','synthetic','--conversation','c','--output',output]),
                                    ('recaplib.title_suggestion',['--db',db,'--source','synthetic','--conversation','c','--output',output])]:
                    self.assert_failure(self.run_cli(module,args),'Filesystem operation failed',str(root),'PRIVATE')
            self.assertEqual(collision.read_text(encoding='utf-8'),'preserve')
            self.assertFalse(absent.exists())
            self.assertFalse(list(root.glob('.recap-*')))


if __name__ == '__main__':
    unittest.main()
