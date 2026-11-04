"""Synthetic web tag validation, atomic rejection, and reviewed-title workflow."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from branch_title import suggest_branch
from conversation_view import conversation
from export_inventory import list_export
from import_check import check_import
from prepare_web_export import prepare_web_export
from session_workflow import import_export, inspect_export, normalize
from web_branch import branch_view


class WebContentTypeValidationTests(unittest.TestCase):
    diagnostic = 'message content_type must be nonempty text'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'synthetic.json'
        self.db = self.root / 'archive.sqlite'

    @staticmethod
    def invalid_tags():
        return (None, False, True, 0, 1, 2.5, [], ['code'], {},
                {'private': 'SYNTHETIC_PRIVATE'}, '', ' ', '\t\n', '\u2003')

    @staticmethod
    def record(content, identity='selected'):
        return dict(id=identity, title='New chat', current_node='request', mapping={
            'greeting': dict(message=dict(author=dict(role='user'),
                            content=dict(content_type='text', parts=['Hello!']))),
            'request': dict(parent='greeting', message=dict(author=dict(role='user'), content=content))})

    def write(self, content, extra=()):
        self.path.write_bytes(b'\xef\xbb\xbf' + json.dumps(
            [self.record(content), *extra], ensure_ascii=False).encode('utf-8') + b'\r\n')
        return self.path.read_bytes()

    def reject(self, operation):
        with self.assertRaises(ValueError) as caught:
            operation()
        self.assertEqual(str(caught.exception), self.diagnostic)

    def call(self, *args, script='recap.py', success=True, encoding='utf-8'):
        result = subprocess.run([sys.executable, script, '--db', str(self.db), *map(str, args)],
            capture_output=True, timeout=30, env=dict(os.environ, PYTHONIOENCODING=encoding))
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr.decode(encoding))
        self.assertNotIn(b'Traceback', result.stderr)
        return json.loads(result.stdout) if success else result

    def test_invalid_tags_reject_before_database_access_for_every_content_shape(self):
        for tag in self.invalid_tags():
            for fields in ({}, dict(text='SYNTHETIC_PRIVATE'),
                           dict(parts=['SYNTHETIC_PRIVATE']), dict(parts=[]),
                           dict(parts=['valid first', dict(text='SYNTHETIC_PRIVATE')])):
                with self.subTest(tag=tag, fields=fields):
                    raw = self.write(dict(content_type=tag, **fields))
                    with patch('sqlite3.connect', side_effect=AssertionError('database opened')) as connect:
                        self.reject(lambda: import_export(self.db, 'web', self.path, 'web'))
                        connect.assert_not_called()
                    self.assertFalse(self.db.exists())
                    self.assertEqual(self.path.read_bytes(), raw)

    def test_all_whole_file_readers_reject_late_unselected_malformed_conversation(self):
        self.write(dict(content_type='text', parts=['Synthetic orchard request']))
        import_export(self.db, 'web', self.path, 'web')
        before = self.db.read_bytes()
        for tag in self.invalid_tags():
            raw = self.write(dict(content_type='text', parts=['Synthetic orchard request']),
                [self.record(dict(content_type=tag, text='SYNTHETIC_PRIVATE'), 'unselected')])
            operations = (
                lambda: normalize(self.path, 'web', conversation='selected'),
                lambda: inspect_export(self.path, 'web', 'selected'),
                lambda: list_export(self.path, 'web', contains='no matches'),
                lambda: check_import(self.db, 'web', self.path, 'web', 'selected'),
                lambda: import_export(self.db, 'web', self.path, 'web', 'selected'),
                lambda: branch_view(self.path, 'selected', 'greeting'),
                lambda: suggest_branch(self.db, 'web', 'selected', self.path, 'greeting'))
            for operation in operations:
                with self.subTest(tag=tag, operation=operation):
                    with patch('sqlite3.connect', side_effect=AssertionError('database opened')):
                        self.reject(operation)
                    self.assertEqual(self.db.read_bytes(), before)
                    self.assertEqual(self.path.read_bytes(), raw)

    def test_branch_selection_does_not_bypass_malformed_off_path_node(self):
        self.write(dict(content_type='text', parts=['Synthetic orchard request']))
        data = json.loads(self.path.read_text(encoding='utf-8-sig'))
        data[0]['mapping']['alternate'] = dict(parent='greeting', message=dict(
            author=dict(role='assistant'), content=dict(content_type={}, parts=['SYNTHETIC_PRIVATE'])))
        self.path.write_text(json.dumps(data), encoding='utf-8')
        with patch('sqlite3.connect', side_effect=AssertionError('database opened')):
            self.reject(lambda: branch_view(self.path, 'selected'))
            self.reject(lambda: suggest_branch(self.db, 'web', 'selected', self.path))

    def test_present_invalid_tags_reject_all_supported_roles(self):
        for role in ('user', 'assistant', 'system', 'tool'):
            self.write(dict(content_type=None, parts=['SYNTHETIC_PRIVATE']))
            data = json.loads(self.path.read_text(encoding='utf-8-sig'))
            data[0]['mapping']['request']['message']['author']['role'] = role
            self.path.write_text(json.dumps(data), encoding='utf-8')
            with self.subTest(role=role):
                self.reject(lambda: normalize(self.path, 'web'))

    def test_absent_unknown_padded_and_nonblank_tags_keep_exact_existing_behavior(self):
        for tag in (None, 'text', 'multimodal_text', 'future_type', ' code', 'execution_output ', 'future\nvariant'):
            content = dict(parts=['  Synthetic orchard\n', dict(text='SYNTHETIC_PRIVATE'), '\tanswer  '])
            if tag is not None:
                content['content_type'] = tag
            self.write(content)
            with self.subTest(tag=tag):
                rows, report = normalize(self.path, 'web', include_report=True)
                self.assertEqual(rows[1]['text'], '  Synthetic orchard\n\n\tanswer  ')
                self.assertEqual(report['nontext_parts_skipped'], 1)
                self.assertEqual(report['unsupported_text_fields'], 0)
        for tag in (None, 'unknown', ' code', 'execution_output '):
            content = dict(text='SYNTHETIC_PRIVATE')
            if tag is not None:
                content['content_type'] = tag
            self.write(content)
            rows, report = normalize(self.path, 'web', include_report=True)
            self.assertEqual([row['message_id'] for row in rows], ['greeting'])
            self.assertEqual(report['unsupported_text_fields'], 1)
            self.assertIn('Unsupported text fields were not extracted.', report['warnings'])

    def test_string_parts_preserve_exact_text_and_original_provenance(self):
        body = '  Synthetic orchard 합성 🌱\n'
        raw = self.write(dict(content_type='text', parts=[body, '\tanswer  ']))
        import_export(self.db, 'web', self.path, 'web')
        detail = conversation(self.db, 'web', 'selected')
        request = next(row for row in detail['messages'] if row['message_id'] == 'request')
        self.assertEqual(request['text'], body + '\n\tanswer  ')
        self.assertIn(dict(original_sha256=hashlib.sha256(raw).hexdigest(),
                           locator='mapping:request', parent_id='greeting'),
                      request['export_provenance'])
        self.assertEqual(self.path.read_bytes(), raw)

    def test_exact_code_and_output_shapes_still_preserve_bytes_and_reject_ambiguity(self):
        for tag in ('code', 'execution_output'):
            self.write(dict(content_type=tag, text='  Synthetic orchard\n'))
            rows, report = normalize(self.path, 'web', include_report=True)
            self.assertEqual(rows[1]['text'], '  Synthetic orchard\n')
            self.assertEqual(report['text_field_messages'], 1)
            for fields in ({}, dict(text=None), dict(text='synthetic', parts=[])):
                self.write(dict(content_type=tag, **fields))
                with self.assertRaises(ValueError):
                    normalize(self.path, 'web')

    def test_malformed_meaningful_request_cannot_save_partial_greeting_title(self):
        self.write(dict(content_type='code', text='Compare synthetic orchard irrigation designs'))
        import_export(self.db, 'web', self.path, 'web')
        before = self.db.read_bytes()
        raw = self.write(dict(content_type=['code'], text='SYNTHETIC_PRIVATE orchard request'))
        output = self.root / 'proposal.json'
        with patch('branch_title.archive_conversation') as read:
            self.reject(lambda: suggest_branch(self.db, 'web', 'selected', self.path))
            read.assert_not_called()
        result = self.call('--source', 'web', '--conversation', 'selected', self.path,
                           '--output', output, script='branch_title.py', success=False, encoding='ascii')
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr.decode('ascii').replace('\r\n', '\n'), self.diagnostic + '\n')
        self.assertFalse(output.exists())
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_cli_failures_are_fixed_value_free_without_partial_output_or_archive(self):
        raw = self.write(dict(content_type={'private': 'SYNTHETIC_PRIVATE 합성'}, parts=['SYNTHETIC_PRIVATE']))
        commands = [('inspect', self.path, '--format', 'web'),
                    ('import', self.path, '--format', 'web', '--source', 'web'),
                    ('list-export', self.path, '--format', 'web'),
                    ('check-import', self.path, '--format', 'web', '--source', 'web')]
        for args in commands:
            result = self.call(*args, success=False, encoding='ascii')
            self.assertEqual(result.stdout, b'')
            self.assertEqual(result.stderr.decode('ascii').replace('\r\n', '\n'), self.diagnostic + '\n')
            self.assertFalse(self.db.exists())
            self.assertEqual(self.path.read_bytes(), raw)

    def test_failure_workflows_accept_windows_crlf_without_relaxing_other_assertions(self):
        real_run = subprocess.run
        observed = []

        def windows_stderr(*args, **kwargs):
            result = real_run(*args, **kwargs)
            original_stdout = result.stdout
            original_code = result.returncode
            if result.returncode:
                # Idempotent on Windows too; never synthesize CRCRLF.
                result.stderr = result.stderr.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
                self.assertEqual(result.stderr, self.diagnostic.encode('ascii') + b'\r\n')
                observed.append(result.stderr)
            self.assertEqual(result.stdout, original_stdout)
            self.assertEqual(result.returncode, original_code)
            return result

        methods = (
            'test_malformed_meaningful_request_cannot_save_partial_greeting_title',
            'test_cli_failures_are_fixed_value_free_without_partial_output_or_archive')
        for method in methods:
            with self.subTest(method=method):
                case = type(self)(method)
                try:
                    case.setUp()
                    with patch('subprocess.run', side_effect=windows_stderr):
                        getattr(case, method)()
                finally:
                    self.assertTrue(case.doCleanups())
                self.assertFalse(case.root.exists())
        self.assertEqual(len(observed), 5)

    def test_zip_preparation_rejects_before_output_staging(self):
        raw = self.write(dict(content_type=None, text='SYNTHETIC_PRIVATE'))
        archive = self.root / 'synthetic.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('conversations.json', raw)
        before = archive.read_bytes()
        for output in (self.root / 'prepared.json', self.root / 'missing' / 'prepared.json'):
            with patch('prepare_web_export.tempfile.mkstemp', side_effect=AssertionError('staged output')):
                with self.assertRaisesRegex(ValueError, '^selected JSON member is not a supported web export$'):
                    prepare_web_export(archive, 'conversations.json', output)
            self.assertFalse(output.exists())
        self.assertEqual(archive.read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(list(self.root.glob('.recap-prepare-*')), [])

    def test_corrected_source_import_review_apply_search_keeps_body_and_provenance(self):
        self.write(dict(content_type=['code'], text='Compare synthetic orchard irrigation designs'))
        self.reject(lambda: import_export(self.db, 'web', self.path, 'web'))
        self.assertFalse(self.db.exists())
        body = 'Compare synthetic orchard irrigation designs 합성 🌱\n'
        raw = self.write(dict(content_type='code', text=body))
        self.call('import', self.path, '--format', 'web', '--source', 'web')
        before = self.db.read_bytes()
        proposal = self.root / 'proposal.json'; reviewed = self.root / 'reviewed.json'
        self.call('--source', 'web', '--conversation', 'selected', self.path,
                  '--output', proposal, script='branch_title.py')
        document = json.loads(proposal.read_text(encoding='utf-8'))
        self.assertEqual(document['evidence_message_ids'], ['request'])
        self.assertIn('orchard', document['title'])
        self.assertIn('합성', document['title'])
        self.call('preview-title', proposal, '--with-evidence', '--output', reviewed)
        self.assertEqual(self.db.read_bytes(), before)
        applied = self.call('apply-title', reviewed)
        self.assertGreater(applied['revision'], 0)
        self.assertEqual(applied['display_title'], document['title'])
        result = self.call('find', 'orchard', '--source', 'web')
        self.assertEqual(result['total_matches'], 1)
        detail = conversation(self.db, 'web', 'selected')
        self.assertEqual(detail['display_title'], applied['display_title'])
        self.assertEqual(detail['revision'], applied['revision'])
        self.assertEqual(detail['original_title'], 'New chat')
        request = next(row for row in detail['messages'] if row['message_id'] == 'request')
        self.assertEqual(request['text'], body)
        self.assertIn(dict(original_sha256=hashlib.sha256(raw).hexdigest(), locator='mapping:request',
                           parent_id='greeting'), request['export_provenance'])
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(import_export(self.db, 'web', self.path, 'web')['inserted'], 0)


if __name__ == '__main__':
    unittest.main()
