"""Synthetic damaged local record tags must not conceal a session boundary."""
import copy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recaplib.attributed_title import suggest_attributed
from recaplib.export_inventory import list_export
from recaplib.import_check import check_import
from recaplib.local_parser import LocalImportError, parse_artifact, parse_jsonl_bytes
from recaplib.replay_title import suggest_replay
from recaplib.session_workflow import import_export, inspect_export, normalize, titles
from recaplib.title_proposal import preview, snapshot
from recaplib.title_suggestion import suggest


ROOT = Path(__file__).resolve().parents[1]
KINDS = ('local', 'local-codex')
BAD_TAGS = (None, False, True, 0, 1, [], ['session_meta'], {},
            {'private': 'SYNTHETIC_TAG_MARKER'}, '', ' ', '\t\r\n', '\u2028')


def message(identity, text):
    return dict(type='response_item', payload=dict(type='message', role='user', id=identity,
        content=[dict(type='input_text', text=text)],
        internal_chat_message_metadata_passthrough=dict(content_item_metadata=[
            dict(provenance=dict(type='user'))])))


class LocalRecordDiscriminatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='recap record tags ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'synthetic.jsonl'
        self.db = self.root / 'archive.sqlite'
        self.records = [dict(type='session_meta', payload=dict(id='session-A')),
                        message('a', 'Can you help with my project?'),
                        dict(type='session_meta', payload=dict(id='session-B')),
                        message('b', 'Compare synthetic irrigation designs')]

    def write(self, records=None):
        raw = ''.join(json.dumps(r, ensure_ascii=False) + '\n'
                      for r in (self.records if records is None else records)).encode('utf-8')
        self.path.write_bytes(raw)
        return raw

    def damaged(self, tag):
        records = copy.deepcopy(self.records)
        records[2]['type'] = tag
        records[2]['payload'].update(cwd='/synthetic/SYNTHETIC_PAYLOAD_MARKER',
                                     originator='synthetic')
        return records

    def assert_fixed_error(self, operation, line=3):
        with self.assertRaises(LocalImportError) as caught:
            operation()
        self.assertEqual(str(caught.exception), f'invalid local record type: {self.path.name}:{line}')
        for marker in ('SYNTHETIC_TAG_MARKER', 'SYNTHETIC_PAYLOAD_MARKER',
                       'session-B', 'Compare synthetic irrigation'):
            self.assertNotIn(marker, str(caught.exception))

    def test_malformed_boundary_cannot_import_later_message_under_previous_identity(self):
        for tag in BAD_TAGS:
            raw = self.write(self.damaged(tag))
            for kind in KINDS:
                with self.subTest(kind=kind, tag=tag), patch('sqlite3.connect',
                        side_effect=AssertionError('database accessed before source validation')):
                    self.assert_fixed_error(lambda: import_export(self.db, 'demo', self.path, kind))
                self.assertFalse(self.db.exists())
                self.assertEqual(self.path.read_bytes(), raw)

    def test_all_source_readers_reject_before_database_access(self):
        self.write(self.damaged([]))
        for kind in KINDS:
            operations = (lambda: normalize(self.path, kind),
                          lambda: inspect_export(self.path, kind),
                          lambda: list_export(self.path, kind),
                          lambda: list_export(self.path, kind, contains='no-match'),
                          lambda: list_export(self.path, kind, text_contains='no-match'),
                          lambda: check_import(self.db, 'demo', self.path, kind))
            for operation in operations:
                with self.subTest(kind=kind), patch('sqlite3.connect', side_effect=AssertionError('database accessed')):
                    self.assert_fixed_error(operation)
        self.assertFalse(self.db.exists())

    def test_selection_cannot_hide_damaged_other_boundary_or_late_record(self):
        for tag in BAD_TAGS:
            self.write(self.damaged(tag))
            for kind in KINDS:
                for identity in ('session-A', 'session-B', 'missing'):
                    operations = (lambda: inspect_export(self.path, kind, conversation=identity),
                                  lambda: import_export(self.db, 'demo', self.path, kind, conversation=identity),
                                  lambda: check_import(self.db, 'demo', self.path, kind, conversation=identity))
                    for operation in operations:
                        with self.subTest(kind=kind, tag=tag, identity=identity):
                            self.assert_fixed_error(operation)
        self.assertFalse(self.db.exists())

    def test_failed_reimport_preserves_existing_archive_and_title_revision(self):
        self.write()
        import_export(self.db, 'demo', self.path, 'local-codex')
        titles(self.db, 'demo', 'session-B', 'Reviewed synthetic title', 0)
        before = self.db.read_bytes()
        for tag in BAD_TAGS:
            self.write(self.damaged(tag))
            for kind in KINDS:
                with self.subTest(kind=kind, tag=tag):
                    self.assert_fixed_error(lambda: import_export(self.db, 'demo', self.path, kind))
                    self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(titles(self.db, 'demo', 'session-B')['revision'], 1)

    def test_byte_and_path_parser_contracts_agree(self):
        raw = self.write(self.damaged(False))
        for profile in ('legacy', 'codex'):
            with self.subTest(profile=profile):
                self.assert_fixed_error(lambda: parse_jsonl_bytes(raw, self.path.name, profile))
                with self.assertRaises(LocalImportError) as caught:
                    parse_artifact(self.path, self.path.name, content_profile=profile)
                self.assertEqual(str(caught.exception), f'invalid local record type: {self.path}:3')
        self.assertEqual(self.path.read_bytes(), raw)

    def test_bom_blank_lines_and_supported_newlines_preserve_physical_location(self):
        records = self.damaged({'private': 'SYNTHETIC_TAG_MARKER'})
        for kind in KINDS:
            for ending in (b'\n', b'\r\n', b'\r'):
                for bom in (b'', b'\xef\xbb\xbf'):
                    lines = [json.dumps(r).encode('utf-8') for r in records]
                    raw = bom + ending.join([lines[0], b'', lines[1], lines[2], lines[3]]) + ending
                    self.path.write_bytes(raw)
                    with self.subTest(kind=kind, ending=ending, bom=bom):
                        self.assert_fixed_error(lambda: inspect_export(self.path, kind), line=4)
                        self.assertEqual(self.path.read_bytes(), raw)

    def test_malformed_first_record_and_skipped_payloads_still_reject(self):
        for kind in KINDS:
            for tag in BAD_TAGS:
                for payload in (None, [], {}, {'type': 'function_call'}, {'private': 'SYNTHETIC_PAYLOAD_MARKER'}):
                    self.write([dict(type=tag, payload=payload), *self.records])
                    with self.subTest(kind=kind, tag=tag, payload=payload):
                        self.assert_fixed_error(lambda: inspect_export(self.path, kind), line=1)

    def test_damaged_user_record_cannot_leave_only_a_generic_title_candidate(self):
        for tag in BAD_TAGS:
            records = self.records[:2] + [message('later', 'Compare synthetic irrigation designs')]
            records[-1]['type'] = tag
            self.write(records)
            for kind in KINDS:
                with self.subTest(kind=kind, tag=tag):
                    self.assert_fixed_error(lambda: import_export(self.db, 'demo', self.path, kind))
                    self.assertFalse(self.db.exists())

    def test_absent_unknown_and_padded_types_keep_literal_skip_compatibility(self):
        unknown = [dict(payload=dict(private='SYNTHETIC_PAYLOAD_MARKER')),
                   dict(type='future_record', payload=dict(private='SYNTHETIC_PAYLOAD_MARKER')),
                   dict(type=' session_meta ', payload=dict(id='ignored-not-a-boundary')),
                   dict(type='\u200b', payload={})]
        raw = self.write([self.records[0], self.records[1], *unknown,
                          message('later', 'Another request in the same synthetic session')])
        for kind in KINDS:
            rows, report = normalize(self.path, kind, include_report=True)
            self.assertEqual([r['conversation_id'] for r in rows], ['session-A', 'session-A'])
            self.assertEqual(report['rollout_context']['other_records'], len(unknown))
            self.assertTrue(any('unknown records' in warning for warning in report['warnings']))
            self.assertNotIn('SYNTHETIC_PAYLOAD_MARKER', json.dumps(report))
            self.assertEqual(self.path.read_bytes(), raw)

    def test_valid_multiple_sessions_still_select_and_review_the_correct_request(self):
        raw = self.write()
        for kind in KINDS:
            rows = normalize(self.path, kind)
            self.assertEqual([(r['conversation_id'], r['message_id'], r['origin_locator']) for r in rows],
                             [('session-A', 'a', 'line:2'), ('session-B', 'b', 'line:4')])
            inventory = list_export(self.path, kind)
            self.assertEqual(inventory['total_conversations'], 2)
            self.assertEqual(inventory['selectable_conversations'], 2)
            import_export(self.db, kind, self.path, kind, conversation='session-B',
                          expected_export_sha256=hashlib.sha256(raw).hexdigest())
            proposal = suggest(self.db, kind, 'session-B')
            self.assertEqual(proposal['title'], 'Compare synthetic irrigation designs')
            self.assertEqual(proposal['evidence_message_ids'], ['b'])
            before = self.db.read_bytes()
            self.assertEqual(preview(self.db, proposal)['expected_revision'], 0)
            self.assertEqual(self.db.read_bytes(), before)
            self.assertEqual([r['message_id'] for r in snapshot(self.db, kind, 'session-B')[0]], ['b'])
        self.assertEqual(self.path.read_bytes(), raw)

    def test_metadata_only_index_and_raw_agent_utility_paths_keep_existing_contracts(self):
        for tag in BAD_TAGS:
            raw = (json.dumps(dict(id='synthetic-index', thread_name='Synthetic title',
                updated_at='synthetic-time', type=tag, payload=None)) + '\n').encode()
            for profile in ('legacy', 'codex'):
                for name, reason in (('session_index.jsonl', 'session_index_metadata'),
                    ('agents/tool-a/raw/synthetic.jsonl', 'agent_raw_evidence'),
                    ('agents/tool-b/raw/synthetic.jsonl', 'agent_raw_evidence'),
                    ('agents/tool-c/raw/synthetic.jsonl', 'agent_raw_evidence')):
                    with self.subTest(tag=tag, profile=profile, name=name):
                        parsed = parse_jsonl_bytes(raw, name, profile)
                        self.assertEqual(parsed.admission_status, 'accepted_metadata_only')
                        self.assertEqual(parsed.reason_code, reason)
                        self.assertEqual(parsed.messages, ())
        index = self.root / 'session_index.jsonl'
        index.write_bytes(raw)
        for kind in KINDS:
            self.assertEqual(list_export(index, kind)['total_conversations'], 0)

    def test_sqlite_utility_admission_is_unchanged(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('CREATE TABLE synthetic(value TEXT)')
        parsed = parse_artifact(self.db, 'synthetic.sqlite', artifact_kind='sqlite')
        self.assertEqual(parsed.admission_status, 'accepted_metadata_only')
        self.assertEqual(parsed.reason_code, 'sqlite_backup')

    def test_source_backed_title_generation_rejects_without_archive_or_fallback(self):
        self.write(self.damaged(None))
        with patch('sqlite3.connect', side_effect=AssertionError('database accessed')):
            self.assert_fixed_error(lambda: suggest_attributed(self.db, 'demo', 'session-A', self.path,
                                                              message_id='a'))
            with self.assertRaises(ValueError):
                suggest_replay(self.db, 'demo', 'session-A', self.path)
        self.assertFalse(self.db.exists())

    def test_hash_mismatch_still_precedes_discriminator_validation(self):
        self.write(self.damaged(None))
        for kind in KINDS:
            with self.subTest(kind=kind), patch('recaplib.session_workflow._normalize_bytes',
                    side_effect=AssertionError('source parsed despite mismatched hash')):
                with self.assertRaisesRegex(ValueError, 'export changed after inspection'):
                    inspect_export(self.path, kind, expected_export_sha256='0' * 64)

    def test_cli_errors_are_fixed_without_partial_json_database_or_saved_proposal(self):
        self.write(self.damaged({'private': 'SYNTHETIC_TAG_MARKER'}))
        commands = []
        for kind in KINDS:
            options = (str(self.path), '--format', kind)
            commands.extend([
                ('recap.py', 'inspect', *options),
                ('recap.py', 'list-export', *options, '--contains', 'no-match'),
                ('export_inventory.py', *options),
                ('recap.py', '--db', str(self.db), 'import', *options, '--source', 'demo'),
                ('session_workflow.py', '--db', str(self.db), 'import', *options, '--source', 'demo'),
                ('recap.py', '--db', str(self.db), 'check-import', *options, '--source', 'demo')])
        output = self.root / 'must-not-exist.json'
        commands += [('recap.py', '--db', str(self.db), 'suggest-attributed-title', str(self.path),
                      '--source', 'demo', '--conversation', 'session-A', '--message', 'a', '--output', str(output)),
                     ('attributed_title.py', '--db', str(self.db), str(self.path), '--source', 'demo',
                      '--conversation', 'session-A', '--message', 'a', '--output', str(output))]
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, str(ROOT / command[0]), *command[1:]],
                    cwd=self.root, capture_output=True, text=True, encoding='utf-8', timeout=30,
                    env=dict(os.environ, PYTHONIOENCODING='ascii'))
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, f'invalid local record type: {self.path.name}:3\n')
                self.assertFalse(self.db.exists())
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
