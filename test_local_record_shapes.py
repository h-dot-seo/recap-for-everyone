"""Synthetic malformed local record envelopes fail before archive work."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from attributed_title import suggest_attributed
from export_inventory import list_export
from import_check import check_import
from local_parser import LocalImportError
from replay_title import suggest_replay
from session_workflow import import_export, inspect_export


class LocalRecordShapeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.jsonl'
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.valid = [dict(type='session_meta', payload=dict(id='synthetic')),
                      dict(type='response_item', payload=dict(type='message', role='user', id='u',
                           content=[dict(type='input_text', text='Synthetic valid request')]))]

    def write(self, extra=(), newline='\n', bom=False):
        text = newline.join(json.dumps(r) for r in [*self.valid, *extra]) + newline
        self.path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + text.encode())

    @staticmethod
    def malformed():
        for payload in (None, [], False, 0, 'SYNTHETIC_PRIVATE', {}):
            yield dict(type='response_item', payload=payload)
        yield dict(type='response_item')
        for value in (None, '', ' ', '\t\n', False, 0, [], {'private': 'SYNTHETIC_PRIVATE'}):
            yield dict(type='response_item', payload=dict(type=value))
        yield dict(type='response_item', payload=dict(type='message'))
        for value in (None, '', ' ', '\t\n', False, 0, [], {'private': 'SYNTHETIC_PRIVATE'}):
            yield dict(type='response_item', payload=dict(type='message', role=value))

    def test_malformed_known_envelopes_reject_before_database_creation(self):
        for kind in ('local', 'local-codex'):
            for record in self.malformed():
                with self.subTest(kind=kind, record=record):
                    self.write([record])
                    with self.assertRaises(LocalImportError) as caught:
                        import_export(self.db, 'synthetic', self.path, kind)
                    self.assertTrue(str(caught.exception).endswith(':3'))
                    self.assertNotIn('SYNTHETIC_PRIVATE', str(caught.exception))
                    self.assertFalse(self.db.exists())

    def test_failed_reimports_leave_existing_archive_unchanged(self):
        self.write()
        import_export(self.db, 'synthetic', self.path, 'local-codex')
        before = self.db.read_bytes()
        for kind in ('local', 'local-codex'):
            for record in self.malformed():
                with self.subTest(kind=kind, record=record):
                    self.write([record])
                    with self.assertRaises(LocalImportError):
                        import_export(self.db, 'synthetic', self.path, kind)
                    self.assertEqual(self.db.read_bytes(), before)

    def test_inspection_inventory_and_conflict_check_reject_same_shapes(self):
        for kind in ('local', 'local-codex'):
            for record in self.malformed():
                self.write([record])
                for operation in (lambda: inspect_export(self.path, kind),
                                  lambda: list_export(self.path, kind),
                                  lambda: check_import(self.db, 'synthetic', self.path, kind)):
                    with self.subTest(kind=kind, record=record), self.assertRaises(LocalImportError):
                        operation()
                    self.assertFalse(self.db.exists())

    def test_supported_unknown_types_and_roles_remain_explicit_skips(self):
        records = [dict(type='response_item', payload=dict(type=kind, arguments='SYNTHETIC_PRIVATE'))
                   for kind in ('function_call', 'function_call_output', 'future_response')]
        records += [dict(type='response_item', payload=dict(type='message', role=role, content=None))
                    for role in ('system', 'developer', 'tool', 'future_role')]
        for kind in ('local', 'local-codex'):
            self.write(records)
            report = inspect_export(self.path, kind)
            self.assertEqual(report['extracted_messages'], 1)
            self.assertEqual(report['rollout_context']['nonmessage_response_items'], 3)
            self.assertEqual(report['rollout_context']['skipped_role_messages'], 4)
            self.assertTrue(report['warnings'])
            self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps(report))

    def test_physical_lines_preserved_for_bom_and_all_supported_newlines(self):
        for kind in ('local', 'local-codex'):
            for newline in ('\n', '\r\n', '\r'):
                for bom in (False, True):
                    self.write([dict(type='response_item', payload=None)], newline, bom)
                    with self.subTest(kind=kind, newline=newline, bom=bom), self.assertRaisesRegex(LocalImportError, ':3$'):
                        inspect_export(self.path, kind)

    def test_attributed_and_replay_helpers_reject_malformed_source_without_db(self):
        self.write([dict(type='response_item', payload=None)])
        for helper in (suggest_attributed, suggest_replay):
            with self.subTest(helper=helper.__name__), self.assertRaises(ValueError):
                helper(self.db, 'synthetic', 'synthetic', self.path)
            self.assertFalse(self.db.exists())

    def test_cli_failures_are_clean_and_do_not_echo_payload(self):
        self.write([dict(type='response_item', payload='SYNTHETIC_PRIVATE')])
        for kind in ('local', 'local-codex'):
            for script in ('recap.py', 'session_workflow.py'):
                result = subprocess.run([sys.executable, script, '--db', str(self.db), 'import',
                    str(self.path), '--format', kind, '--source', 'synthetic'], capture_output=True, text=True, timeout=20)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(':3', result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertNotIn('SYNTHETIC_PRIVATE', result.stderr)
                self.assertFalse(self.db.exists())


if __name__ == '__main__':
    unittest.main()
