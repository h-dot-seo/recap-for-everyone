"""Synthetic typed-part validation boundaries, atomicity, and provenance."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recaplib.attributed_title import suggest_attributed
from recaplib.conversation_view import conversation
from recaplib.export_inventory import list_export
from recaplib.import_check import check_import
from recaplib.local_parser import LocalImportError, parse_artifact
from recaplib.session_workflow import import_export, inspect_export, normalize
from recaplib.title_suggestion import suggest


class TypedContentShapeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.jsonl'
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.records = [dict(type='session_meta', payload=dict(id='selected')),
                        self.message([dict(type='input_text', text='Hello!')], identity='greeting')]

    @staticmethod
    def message(parts, role='user', identity='request'):
        return dict(type='response_item', payload=dict(type='message', role=role,
                    id=identity, content=parts))

    @staticmethod
    def invalid_tags():
        return (None, False, True, 0, 1, 2.5, [], ['input_text'], {},
                {'private': 'SYNTHETIC_PRIVATE'}, '', ' ', '\t\n', '\u2003')

    def write(self, extra=(), newline='\n', bom=False, blank=False):
        lines = [json.dumps(row, ensure_ascii=False) for row in [*self.records, *extra]]
        if blank:
            lines.insert(2, '')
        self.path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + (newline.join(lines) + newline).encode('utf-8'))
        return self.path.read_bytes()

    def assert_invalid(self, operation, line=3, diagnostic='typed content item type must be nonempty text'):
        with self.assertRaises(LocalImportError) as caught:
            operation()
        error = str(caught.exception)
        self.assertTrue(error.startswith(diagnostic + ': '), error)
        self.assertTrue(error.endswith(':' + str(line)), error)
        self.assertNotIn('SYNTHETIC_PRIVATE', error)
        self.assertNotIn('Compare synthetic', error)

    def test_all_present_invalid_tags_reject_user_and_assistant_before_creation(self):
        for role in ('user', 'assistant'):
            for tag in self.invalid_tags():
                with self.subTest(role=role, tag=tag):
                    raw = self.write([self.message([dict(type=tag, text='SYNTHETIC_PRIVATE')], role)])
                    self.assert_invalid(lambda: import_export(self.db, 'source', self.path, 'local-codex'))
                    self.assertFalse(self.db.exists())
                    self.assertEqual(self.path.read_bytes(), raw)

    def test_invalid_tag_after_valid_part_rejects_before_any_database_connection(self):
        for tag in self.invalid_tags():
            for text_fields in ({}, {'text': ''}, {'text': ' \t\n'}):
                with self.subTest(tag=tag, text_fields=text_fields):
                    raw = self.write([self.message([
                        dict(type='input_text', text='Synthetic valid first part'),
                        dict(type=tag, **text_fields)])])
                    with patch('sqlite3.connect', side_effect=AssertionError('database opened')) as connect:
                        self.assert_invalid(lambda: import_export(self.db, 'source', self.path, 'local-codex'))
                        connect.assert_not_called()
                    self.assertFalse(self.db.exists())
                    self.assertEqual(self.path.read_bytes(), raw)

    def test_all_present_invalid_tags_preserve_existing_archive_and_source(self):
        self.write()
        import_export(self.db, 'source', self.path, 'local-codex')
        before = self.db.read_bytes()
        for tag in self.invalid_tags():
            with self.subTest(tag=tag):
                raw = self.write([self.message([dict(type=tag, text='SYNTHETIC_PRIVATE')])])
                self.assert_invalid(lambda: import_export(self.db, 'source', self.path, 'local-codex'))
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(self.path.read_bytes(), raw)

    def test_late_unselected_malformed_part_rejects_every_whole_file_reader(self):
        extra = [dict(type='session_meta', payload=dict(id='unselected')),
                 self.message([dict(type=['input_text'], text='SYNTHETIC_PRIVATE')])]
        for existing in (False, True):
            if existing:
                self.write()
                import_export(self.db, 'source', self.path, 'local-codex')
            before = self.db.read_bytes() if existing else None
            raw = self.write(extra)
            operations = (
                lambda: normalize(self.path, 'local-codex', conversation='selected'),
                lambda: inspect_export(self.path, 'local-codex', 'selected'),
                lambda: list_export(self.path, 'local-codex'),
                lambda: check_import(self.db, 'source', self.path, 'local-codex', 'selected'),
                lambda: import_export(self.db, 'source', self.path, 'local-codex', 'selected'),
                lambda: suggest_attributed(self.db, 'source', 'selected', self.path))
            for operation in operations:
                with self.subTest(existing=existing, operation=operation):
                    self.assert_invalid(operation, line=4)
                    self.assertEqual(self.db.read_bytes() if self.db.exists() else None, before)
                    self.assertEqual(self.path.read_bytes(), raw)

    def test_greeting_loss_reproducer_never_yields_partial_title_proposal(self):
        self.records[1]['payload']['internal_chat_message_metadata_passthrough'] = {
            'content_item_metadata': [{'provenance': {'type': 'user'}}]}
        self.write()
        import_export(self.db, 'source', self.path, 'local-codex')
        self.assertEqual(suggest(self.db, 'source', 'selected')['title'], 'Hello!')
        before = self.db.read_bytes()
        raw = self.write([self.message([dict(type=['input_text'],
                       text='Compare synthetic orchard irrigation designs')])])
        with patch('recaplib.attributed_title.archive_conversation') as archive_read:
            self.assert_invalid(lambda: suggest_attributed(self.db, 'source', 'selected', self.path))
            archive_read.assert_not_called()
        self.assert_invalid(lambda: import_export(self.db, 'source', self.path, 'local-codex'))
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_physical_line_numbers_include_blank_lines_bom_and_each_newline(self):
        for newline in ('\n', '\r\n', '\r'):
            for bom in (False, True):
                with self.subTest(newline=newline, bom=bom):
                    self.write([self.message([dict(type=None, text='SYNTHETIC_PRIVATE')])],
                               newline=newline, bom=bom, blank=True)
                    self.assert_invalid(lambda: inspect_export(self.path, 'local-codex'), line=4)

    def test_existing_malformed_content_errors_have_fixed_diagnostics_and_line(self):
        cases = [(None, 'typed message content must be an array'),
                 ({'private': 'SYNTHETIC_PRIVATE'}, 'typed message content must be an array'),
                 (['SYNTHETIC_PRIVATE'], 'typed content item must be an object'),
                 ([None], 'typed content item must be an object'),
                 ([dict(type='input_text')], 'typed text content requires a string'),
                 ([dict(type='output_text', text={'private': 'SYNTHETIC_PRIVATE'})],
                  'typed text content requires a string')]
        for parts, diagnostic in cases:
            with self.subTest(parts=parts):
                self.write([self.message(parts)], newline='\r\n', bom=True, blank=True)
                self.assert_invalid(lambda: inspect_export(self.path, 'local-codex'),
                                    line=4, diagnostic=diagnostic)

    def test_missing_unknown_media_and_padded_tags_are_counted_without_coercion(self):
        parts = [dict(text='SYNTHETIC_PRIVATE'),
                 *[dict(type=tag, text={'private': 'SYNTHETIC_PRIVATE'}) for tag in
                   ('input_image', 'input_audio', 'future_type', ' input_text', 'output_text ', 'future\nvariant')],
                 dict(type='input_text', text='  Synthetic request\n'),
                 dict(type='output_text', text='\tSynthetic answer  ')]
        self.write([self.message(parts)])
        rows, report = normalize(self.path, 'local-codex', include_report=True)
        self.assertEqual(rows[1]['text'], '  Synthetic request\n\n\tSynthetic answer  ')
        self.assertEqual(report['skipped_content_parts'], 7)
        self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps((rows, report)))

    def test_legacy_profile_keeps_accepting_present_malformed_tags(self):
        for tag in self.invalid_tags():
            with self.subTest(tag=tag):
                self.write([self.message([dict(type=tag, text='  Legacy synthetic text  ')])])
                rows, report = normalize(self.path, 'local', include_report=True)
                self.assertEqual(rows[1]['text'], 'Legacy synthetic text')
                self.assertEqual(report['skipped_content_parts'], 0)

    def test_unsupported_roles_and_nonmessage_content_are_not_newly_validated(self):
        extra = [self.message([dict(type=[], text='SYNTHETIC_PRIVATE')], role=role)
                 for role in ('system', 'developer', 'tool', 'future_role')]
        extra += [dict(type='response_item', payload=dict(type='function_call',
                  content=[dict(type=None, text='SYNTHETIC_PRIVATE')]))]
        self.write(extra)
        rows, report = normalize(self.path, 'local-codex', include_report=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(report['rollout_context']['skipped_role_messages'], 4)
        self.assertEqual(report['rollout_context']['nonmessage_response_items'], 1)
        self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps((rows, report)))

    def test_metadata_only_utility_paths_keep_their_own_validation_contract(self):
        self.write([self.message([dict(type=None, text='SYNTHETIC_PRIVATE')])])
        parsed = parse_artifact(self.path, 'agents/claude/raw/synthetic.jsonl', content_profile='codex')
        self.assertEqual(parsed.admission_status, 'accepted_metadata_only')
        self.assertEqual(parsed.messages, ())
        row = dict(id='index', thread_name='Synthetic title', updated_at='synthetic',
                   type='response_item', payload=dict(type='message', role='user',
                   content=[dict(type=None, text='SYNTHETIC_PRIVATE')]))
        self.path.write_text(json.dumps(row) + '\n', encoding='utf-8')
        parsed = parse_artifact(self.path, 'session_index.jsonl', content_profile='codex')
        self.assertEqual(parsed.reason_code, 'session_index_metadata')
        self.assertEqual(parsed.messages, ())

    def test_valid_bytes_hashes_variant_hashes_and_archive_provenance_are_unchanged(self):
        record = self.message([dict(type='input_text', text='  Synthetic orchard request\n')])
        raw = self.write([record], newline='\r\n', bom=True, blank=True)
        digest = hashlib.sha256(raw).hexdigest()
        parsed = parse_artifact(self.path, self.path.name, content_profile='codex')
        message = parsed.messages[1]
        self.assertEqual(message.line_number, 4)
        self.assertEqual(message.text_sha256, hashlib.sha256(message.text.encode()).hexdigest())
        self.assertEqual(message.variant_sha256, hashlib.sha256(json.dumps(record, ensure_ascii=True,
                         sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest())
        report = inspect_export(self.path, 'local-codex')
        self.assertEqual(report['original_sha256'], digest)
        import_export(self.db, 'source', self.path, 'local-codex')
        rows = conversation(self.db, 'source', 'selected')['messages']
        request = next(row for row in rows if row['message_id'] == 'request')
        self.assertEqual(request['text'], message.text)
        self.assertEqual(request['export_provenance'][0]['original_sha256'], digest)
        self.assertEqual(request['export_provenance'][0]['locator'], 'line:4')
        self.assertEqual(import_export(self.db, 'source', self.path, 'local-codex')['inserted'], 0)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_cli_ascii_failures_have_no_payload_traceback_or_partial_json(self):
        raw = self.write([self.message([dict(type=['input_text'], text='SYNTHETIC_PRIVATE 합성')])])
        commands = [('inspect', self.path, '--format', 'local-codex'),
                    ('import', self.path, '--format', 'local-codex', '--source', 'source'),
                    ('list-export', self.path, '--format', 'local-codex'),
                    ('check-import', self.path, '--format', 'local-codex', '--source', 'source'),
                    ('suggest-attributed-title', self.path, '--source', 'source', '--conversation', 'selected')]
        for args in commands:
            with self.subTest(command=args[0]):
                result = subprocess.run([sys.executable, 'recap.py', '--db', str(self.db), *map(str, args)],
                    capture_output=True, timeout=20, env=dict(os.environ, PYTHONIOENCODING='ascii'))
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, b'')
                error = result.stderr.decode('ascii')
                self.assertIn('typed content item type must be nonempty text', error)
                self.assertIn(':3', error)
                self.assertNotIn('Traceback', error)
                self.assertNotIn('SYNTHETIC_PRIVATE', error)
                self.assertFalse(self.db.exists())
                self.assertEqual(self.path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
