"""Synthetic offline regression: index admission must govern export inventory.

An exact session_index.jsonl basename is a metadata utility, never a rollout,
including when otherwise ignored fields happen to resemble rollout envelopes.
"""
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

from export_inventory import list_export
from session_workflow import import_export, normalize


KINDS = ('local', 'local-codex')
MISSING = object()


class MetadataInventoryContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'session_index.jsonl'
        self.db = Path(self.tmp.name) / 'synthetic.sqlite'

    @staticmethod
    def entry(**extra):
        return dict(id='synthetic-index-id', thread_name='Synthetic café title',
                    updated_at='2026-01-01T00:00:00Z', **extra)

    def write(self, *records):
        raw = ''.join(json.dumps(record, ensure_ascii=False) + '\r\n'
                      for record in records).encode('utf-8')
        self.path.write_bytes(raw)
        return raw

    def assert_index(self, result, raw, count=1):
        self.assertEqual(result['conversations'], [])
        self.assertEqual(result['total_conversations'], 0)
        self.assertEqual(result['selectable_conversations'], 0)
        self.assertIsNone(result['next_offset'])
        self.assertFalse(result['contains_message_text'])
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(result['original_sha256'], digest)
        self.assertEqual(result['original_bytes'], len(raw))
        coverage = result['coverage']
        self.assertEqual(coverage['original_sha256'], digest)
        self.assertEqual(coverage['parser_admission_status'], 'accepted_metadata_only')
        self.assertEqual(coverage['reason_code'], 'session_index_metadata')
        self.assertEqual(coverage['observed_records'], count)
        self.assertEqual(coverage['extracted_messages'], 0)
        self.assertIn('No messages extracted; inspect the supported format and source before importing.',
                      coverage['warnings'])
        self.assertEqual(coverage['sessions_in_metadata'], 0)
        self.assertEqual(coverage['records_without_extracted_message'], count)
        if 'filter' in result:
            self.assertEqual(result['filter']['matched_conversations'], 0)
            self.assertEqual(result['filter']['matched_selectable_conversations'], 0)
            if 'matched_messages' in result['filter']:
                self.assertEqual(result['filter']['matched_messages'], 0)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_plain_index_retains_existing_zero_conversation_shape(self):
        raw = self.write(self.entry())
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assert_index(list_export(self.path, kind), raw)
                self.assertEqual(normalize(self.path, kind), [])

    def test_nonempty_core_strings_preserve_existing_whitespace_acceptance(self):
        # Admission requires nonempty strings, not trimmed or date-validated text.
        raw = self.write(dict(id=' ', thread_name='\t', updated_at='\r\n'))
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assert_index(list_export(self.path, kind), raw)

    def test_extra_session_meta_payloads_never_reinterpret_index(self):
        payloads = (MISSING, None, False, True, 0, 12, '', 'not an envelope',
                    [], [dict(id='phantom-list-id')], {},
                    dict(id='phantom-payload-id'), dict(session_id='phantom-alias-id'),
                    dict(id=False), dict(id=[]), dict(id={}), dict(id=None),
                    dict(id='conflict-one', session_id='conflict-two'))
        for payload in payloads:
            extra = dict(type='session_meta')
            if payload is not MISSING:
                extra['payload'] = payload
            raw = self.write(self.entry(**extra))
            for kind in KINDS:
                with self.subTest(kind=kind, payload=repr(payload)):
                    self.assert_index(list_export(self.path, kind), raw)

    def test_other_rollout_looking_fields_are_ignored(self):
        for record_type in (None, False, [], {}, 'response_item', 'event_msg'):
            raw = self.write(self.entry(type=record_type, payload=dict(
                type='message', role='user', content=[dict(type='input_text',
                text='SYNTHETIC_BODY_MARKER')]), session_id='phantom-top-level-id',
                title='NOT_AN_INFERRED_TITLE'))
            for kind in KINDS:
                with self.subTest(kind=kind, record_type=record_type):
                    self.assert_index(list_export(self.path, kind), raw)

    def test_filters_and_canonical_matching_never_expose_index_or_payload_ids(self):
        raw = self.write(self.entry(type='session_meta', payload=dict(
            id='phantom-payload-id', title='Synthetic café title')))
        for kind in KINDS:
            for field in ('contains', 'text_contains'):
                for query in ('synthetic-index-id', 'phantom-payload-id',
                              'Synthetic', 'cafe\u0301'):
                    for canonical in (False, True):
                        with self.subTest(kind=kind, field=field, query=query,
                                          canonical=canonical):
                            result = list_export(self.path, kind, limit=1, offset=7,
                                canonical_unicode=canonical, **{field: query})
                            self.assert_index(result, raw)
                            self.assertEqual(result['filter']['canonical_unicode'], canonical)

    def test_invalid_core_field_rejects_whole_file_even_outside_filter_page(self):
        for field in ('id', 'thread_name', 'updated_at'):
            for value in (MISSING, None, False, True, 0, [], {}, ''):
                invalid = self.entry(type='session_meta', payload=dict(id='phantom'))
                if value is MISSING:
                    del invalid[field]
                else:
                    invalid[field] = value
                raw = self.write(self.entry(), invalid)
                for kind in KINDS:
                    for options in ({}, {'contains': 'no-match'},
                                    {'text_contains': 'no-match', 'canonical_unicode': True}):
                        with self.subTest(kind=kind, field=field, value=repr(value), options=options):
                            with self.assertRaisesRegex(ValueError, 'invalid session index metadata'):
                                list_export(self.path, kind, limit=1, offset=99, **options)
                            self.assertEqual(self.path.read_bytes(), raw)

    def test_invalid_json_and_duplicate_keys_reject_whole_index(self):
        valid = json.dumps(self.entry())
        bad_lines = ('{', '[]', 'null',
                     '{"id":"one","id":"two","thread_name":"title","updated_at":"date"}',
                     '{"id":"one","thread_name":"title","updated_at":"date",'
                     '"payload":{"id":"one","id":"two"}}')
        for bad in bad_lines:
            raw = (valid + '\r\n' + bad + '\r\n').encode('utf-8')
            self.path.write_bytes(raw)
            for kind in KINDS:
                with self.subTest(kind=kind, bad=bad):
                    with self.assertRaises(ValueError):
                        list_export(self.path, kind, limit=1, offset=999,
                                    contains='no-match', canonical_unicode=True)
                    self.assertEqual(self.path.read_bytes(), raw)

    def test_hash_leases_apply_before_metadata_inventory(self):
        raw = self.write(self.entry(type='session_meta'))
        digest = hashlib.sha256(raw).hexdigest()
        for kind in KINDS:
            with self.subTest(kind=kind):
                result = list_export(self.path, kind, expected_export_sha256=digest)
                self.assert_index(result, raw)
                self.assertEqual(result['coverage']['expected_export_sha256'], digest)
                with patch('export_inventory._normalize_bytes', side_effect=AssertionError('parse after stale lease')):
                    with self.assertRaisesRegex(ValueError, 'export changed after inspection'):
                        list_export(self.path, kind, expected_export_sha256='0' * 64)
                self.assertEqual(self.path.read_bytes(), raw)

    def test_inventory_reads_source_once_and_never_connects_database(self):
        raw = self.write(self.entry(type='session_meta', payload=dict(id='phantom')))
        original_read = Path.read_bytes
        for kind in KINDS:
            calls = []
            def snapshot(path):
                calls.append(path)
                self.assertEqual(path, self.path)
                self.assertEqual(len(calls), 1, 'source reread')
                return raw
            with self.subTest(kind=kind):
                with patch.object(Path, 'read_bytes', snapshot), patch(
                        'sqlite3.connect', side_effect=AssertionError('inventory accessed SQLite')):
                    result = list_export(self.path, kind)
                self.assertEqual(calls, [self.path])
                self.assert_index(result, raw)
                self.assertEqual(original_read(self.path), raw)
                self.assertFalse(self.db.exists())

    def test_empty_and_blank_indexes_are_accepted_metadata_only(self):
        for raw in (b'', b'\r\n \t\r\n\n', b'\xef\xbb\xbf\r\n'):
            self.path.write_bytes(raw)
            for kind in KINDS:
                with self.subTest(kind=kind, raw=raw):
                    self.assert_index(list_export(self.path, kind), raw, count=0)

    def test_empty_or_blank_renamed_index_is_not_a_metadata_utility(self):
        renamed = self.path.with_name('renamed-index.jsonl')
        for raw in (b'', b'\r\n \t\r\n'):
            renamed.write_bytes(raw)
            for kind in KINDS:
                with self.subTest(kind=kind, raw=raw):
                    with self.assertRaisesRegex(ValueError, 'no session metadata'):
                        list_export(renamed, kind)
                    self.assertEqual(renamed.read_bytes(), raw)

    def test_basename_controls_index_not_directory_or_rollout_like_extras(self):
        ordinary = self.write(self.entry())
        renamed = self.path.with_name('renamed-index.jsonl')
        renamed.write_bytes(ordinary)
        hybrid = dict(type='session_meta', payload=dict(id='real-rollout-id'))
        for kind in KINDS:
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, 'no session metadata'):
                    list_export(renamed, kind)
                nested = self.path.parent / 'nested'
                nested.mkdir(exist_ok=True)
                exact = nested / self.path.name
                exact.write_bytes(ordinary)
                self.assert_index(list_export(exact, kind), ordinary)
                hybrid_path = self.path.with_name('hybrid-rollout.jsonl')
                hybrid_raw = (json.dumps(self.entry(**hybrid)) + '\r\n').encode('utf-8')
                hybrid_path.write_bytes(hybrid_raw)
                result = list_export(hybrid_path, kind)
                self.assert_zero_rollout(result)
                self.assertEqual(hybrid_path.read_bytes(), hybrid_raw)

    def assert_zero_rollout(self, result):
        self.assertEqual(result['total_conversations'], 1)
        item, = result['conversations']
        self.assertEqual(item['conversation'], 'real-rollout-id')
        self.assertEqual(item['original_titles'], [])
        self.assertEqual(item['metadata_records'], 1)
        self.assertEqual(item['extracted_messages'], 0)
        self.assertEqual(item['role_counts'], {})
        self.assertEqual(item['selection_blocker'], 'NO_EXTRACTED_TEXT')
        self.assertFalse(item['selection_supported'])
        self.assertEqual(result['coverage']['parser_admission_status'], 'accepted_zero_message')

    def test_real_zero_message_rollout_retains_its_identity(self):
        rollout = self.path.with_name('ordinary-rollout.jsonl')
        raw = b'{"type":"session_meta","payload":{"id":"real-rollout-id"}}\r\n'
        rollout.write_bytes(raw)
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.assert_zero_rollout(list_export(rollout, kind))
                self.assertEqual(rollout.read_bytes(), raw)

    def cli(self, script, prefix, kind, *extra):
        return subprocess.run([sys.executable, str(Path(__file__).parent / script),
            *prefix, str(self.path), '--format', kind, *extra], cwd=self.tmp.name,
            capture_output=True, text=True, encoding='utf-8', timeout=20,
            env=dict(os.environ, PYTHONIOENCODING='ascii'))

    def test_standalone_and_unified_cli_success_parity_without_tracebacks(self):
        for extra in (dict(type='session_meta'), dict(type='session_meta', payload=None),
                      dict(type='session_meta', payload=dict(id='phantom'))):
            raw = self.write(self.entry(**extra))
            for kind in KINDS:
                for filters in ((), ('--contains', 'phantom', '--canonical-unicode'),
                                ('--text-contains', 'Synthetic')):
                    with self.subTest(kind=kind, extra=extra, filters=filters):
                        results = []
                        for script, prefix in (('export_inventory.py', ()),
                                               ('recap.py', ('list-export',))):
                            process = self.cli(script, prefix, kind, *filters)
                            self.assertEqual(process.returncode, 0, process.stderr)
                            self.assertEqual(process.stderr, '')
                            self.assertNotIn('Traceback', process.stdout + process.stderr)
                            results.append(json.loads(process.stdout))
                            self.assert_index(results[-1], raw)
                        self.assertEqual(*results)

    def test_standalone_and_unified_cli_failure_parity_without_partial_output(self):
        for raw, flags in ((b'{bad json}\r\n', ()),
                           (b'{"id":"x"}\r\n', ()),
                           ((json.dumps(self.entry()) + '\r\n').encode('utf-8'),
                            ('--expected-export-sha256', '0' * 64))):
            self.path.write_bytes(raw)
            for kind in KINDS:
                with self.subTest(kind=kind, raw=raw, flags=flags):
                    failures = []
                    for script, prefix in (('export_inventory.py', ()),
                                           ('recap.py', ('list-export',))):
                        process = self.cli(script, prefix, kind, *flags)
                        self.assertEqual(process.returncode, 1)
                        self.assertEqual(process.stdout, '')
                        self.assertTrue(process.stderr.strip())
                        self.assertNotIn('Traceback', process.stderr)
                        failures.append(process.stderr)
                    self.assertEqual(*failures)
                    self.assertEqual(self.path.read_bytes(), raw)

    def test_existing_zero_record_import_policy_is_not_metadata_persistence(self):
        raw = self.write(self.entry(type='session_meta', payload=dict(id='phantom')))
        empty_digest = hashlib.sha256(b'').hexdigest()
        for kind in KINDS:
            with self.subTest(kind=kind):
                result = import_export(self.db, kind, self.path, kind)
                self.assertEqual(result['records'], 0)
                self.assertEqual(result['inserted'], 0)
                self.assertEqual(result['source_sha256'], empty_digest)
                self.assertEqual(result['coverage']['original_sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(result['coverage']['parser_admission_status'], 'accepted_metadata_only')
                connection = sqlite3.connect(self.db)
                try:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 0)
                    self.assertEqual(connection.execute('SELECT sha256,bytes,record_count FROM artifacts WHERE source_id=?',
                                                       (kind,)).fetchall(), [(empty_digest, 0, 0)])
                    for table in ('export_provenance', 'export_occurrences'):
                        self.assertEqual(connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
                finally:
                    connection.close()
                for identity in ('synthetic-index-id', 'phantom'):
                    with self.assertRaisesRegex(ValueError, 'no extracted messages'):
                        import_export(self.db, kind, self.path, kind, conversation=identity)
                self.assertEqual(self.path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
