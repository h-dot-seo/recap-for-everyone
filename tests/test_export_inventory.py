"""Synthetic, offline export inventory contract and discover/select round trips."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recaplib.export_inventory import list_export
from recaplib.session_workflow import import_export, normalize
from recaplib.conversation_view import conversations


class ExportInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic-export.json'
        self.db = Path(self.tmp.name) / 'archive.sqlite'

    @staticmethod
    def web(identity='chat', title='Synthetic title', roles=('user', 'assistant')):
        return dict(id=identity, title=title, mapping={
            'node-' + str(i): dict(parent=None, message=dict(author=dict(role=role),
                content=dict(parts=['SYNTHETIC_PRIVATE_BODY_' + str(i)])))
            for i, role in enumerate(roles)})

    @staticmethod
    def meta(identity):
        return dict(type='session_meta', payload=dict(id=identity,
            title='DO_NOT_GUESS_LOCAL_TITLE', thread_name='DO_NOT_GUESS_THREAD_NAME',
            cwd='/SYNTHETIC_PRIVATE_CWD', originator='SYNTHETIC_PRIVATE_ORIGIN'))

    @staticmethod
    def message(role='user', text='SYNTHETIC_PRIVATE_LOCAL_BODY'):
        return dict(type='response_item', payload=dict(type='message', id='same-message',
            role=role, content=[dict(type='input_text', text=text)]))

    def write_web(self, records):
        self.path.write_bytes(json.dumps(records, ensure_ascii=False).encode('utf-8'))

    def write_local(self, records, separators=('\n',)):
        self.path.write_bytes(''.join(json.dumps(r, ensure_ascii=False) +
            separators[i % len(separators)] for i, r in enumerate(records)).encode('utf-8'))

    def call(self, script, *args, success=True):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / script),
            *map(str, args)], cwd=self.tmp.name, capture_output=True, text=True, encoding='utf-8',
            env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=20)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertTrue(result.stdout.isascii())
        return json.loads(result.stdout) if success else result.stderr

    def test_documented_synthetic_examples_match_ids_titles_and_counts(self):
        examples = Path(__file__).resolve().parents[1] / 'examples'
        for filename, kind, identity, titles in (
                ('web-export.json', 'web', 'synthetic-chat', ['New chat']),
                ('source-attributed-session.jsonl', 'local-codex', 'synthetic-attributed', [])):
            with self.subTest(filename=filename):
                path = examples / filename
                before = path.read_bytes()
                result = list_export(path, kind)
                item, = result['conversations']
                self.assertEqual(item['conversation'], identity)
                self.assertEqual(item['original_titles'], titles)
                self.assertEqual(item['metadata_records'], 1)
                self.assertEqual(item['extracted_messages'], 2)
                self.assertEqual(item['role_counts'], {'user': 1, 'assistant': 1})
                self.assertTrue(item['selection_supported'])
                self.assertEqual(path.read_bytes(), before)

    def test_empty_web_array_has_zero_totals_and_no_next_page(self):
        self.write_web([])
        result = list_export(self.path, 'web')
        self.assertEqual(result['conversations'], [])
        self.assertEqual(result['total_conversations'], 0)
        self.assertEqual(result['selectable_conversations'], 0)
        self.assertIsNone(result['next_offset'])
        self.assertEqual(result['coverage']['extracted_messages'], 0)

    def test_duplicate_web_ids_titles_and_occurrences_not_database_deduplication(self):
        records = [self.web('same', title) for title in ('Second', 'First', 'Second', None, '')]
        self.write_web(records)
        result = list_export(self.path, 'web')
        item, = result['conversations']
        self.assertEqual(item['original_titles'], ['Second', 'First', ''])
        self.assertEqual(item['metadata_records'], 5)
        self.assertEqual(item['extracted_messages'], 10)
        self.assertEqual(item['role_counts'], {'assistant': 5, 'user': 5})
        self.assertEqual(item['selection_blocker'], 'AMBIGUOUS_WEB_ID')
        self.assertFalse(item['selection_supported'])
        self.assertEqual(result['selectable_conversations'], 0)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            normalize(self.path, 'web', conversation=item['conversation'])

    def test_zero_text_and_media_only_web_are_visible_and_blocked(self):
        empty = self.web('empty', roles=())
        media = self.web('media')
        for node in media['mapping'].values():
            node['message']['content'] = dict(parts=[dict(asset='PRIVATE_ASSET')])
        self.write_web([media, empty, copy.deepcopy(empty)])
        result = list_export(self.path, 'web')
        items = {x['conversation']: x for x in result['conversations']}
        self.assertEqual(items['media']['selection_blocker'], 'NO_EXTRACTED_TEXT')
        self.assertEqual(items['empty']['selection_blocker'], 'AMBIGUOUS_WEB_ID')
        for item in items.values():
            self.assertEqual(item['extracted_messages'], 0)
            self.assertEqual(item['role_counts'], {})
            self.assertFalse(item['selection_supported'])
        self.assertNotIn('PRIVATE_ASSET', json.dumps(result))

    def test_web_roles_all_branches_and_legacy_identity_alias(self):
        record = self.web(roles=('user', 'assistant', 'system', 'tool'))
        record['conversation_id'] = record.pop('id')
        record['current_node'] = 'node-1'
        record['mapping']['node-1']['parent'] = 'node-0'
        record['mapping']['node-2']['parent'] = 'node-0'
        self.write_web([record])
        item, = list_export(self.path, 'web')['conversations']
        self.assertEqual(item['role_counts'], dict(user=1, assistant=1, system=1, tool=1))
        self.assertEqual(item['extracted_messages'], 4)
        self.assertTrue(item['selection_supported'])
        self.assertIsNone(item['selection_blocker'])

    def test_local_repeated_metadata_and_occurrences_preserve_boundaries(self):
        records = [self.meta('first'), self.message(), self.message(), self.meta('zero'),
                   self.meta('second'), self.message('assistant'), self.meta('first'), self.message()]
        records[4]['payload']['session_id'] = records[4]['payload'].pop('id')
        self.write_local(records)
        for kind in ('local', 'local-codex'):
            with self.subTest(kind=kind):
                result = list_export(self.path, kind)
                items = {x['conversation']: x for x in result['conversations']}
                self.assertEqual(items['first']['metadata_records'], 2)
                self.assertEqual(items['first']['extracted_messages'], 3)
                self.assertEqual(items['first']['role_counts'], {'user': 3})
                self.assertEqual(items['second']['role_counts'], {'assistant': 1})
                self.assertEqual(items['zero']['selection_blocker'], 'NO_EXTRACTED_TEXT')
                self.assertEqual(result['selectable_conversations'], 2)
                for item in items.values():
                    self.assertEqual(item['original_titles'], [])
                self.assertTrue(items['first']['selection_supported'])

    def test_media_only_local_sessions_are_listed_for_both_profiles(self):
        media = self.message()
        media['payload']['content'] = [dict(type='input_image', image_url='PRIVATE_IMAGE')]
        self.write_local([self.meta('media'), media])
        for kind in ('local', 'local-codex'):
            item, = list_export(self.path, kind)['conversations']
            self.assertEqual(item['metadata_records'], 1)
            self.assertEqual(item['extracted_messages'], 0)
            self.assertEqual(item['selection_blocker'], 'NO_EXTRACTED_TEXT')

    def test_local_profile_counts_follow_existing_parser_not_guessed_text_fields(self):
        media = self.message()
        media['payload']['content'] = [dict(type='input_image', text='legacy profile text')]
        self.write_local([self.meta('chat'), media])
        self.assertEqual(list_export(self.path, 'local')['conversations'][0]['extracted_messages'], 1)
        self.assertEqual(list_export(self.path, 'local-codex')['conversations'][0]['extracted_messages'], 0)

    def test_local_newline_parity_and_unicode_separators_are_not_record_boundaries(self):
        identity = 'session\u2028with\u2029separators\u0085and한글'
        records = [self.meta(identity), self.message(text='body\u2028\u2029\u0085'),
                   self.meta('second'), self.message('assistant')]
        for separators in (('\n',), ('\r\n',), ('\r',), ('\r\n', '\r', '\n')):
            self.write_local(records, separators)
            for kind in ('local', 'local-codex'):
                with self.subTest(separators=separators, kind=kind):
                    result = list_export(self.path, kind)
                    self.assertEqual(result['total_conversations'], 2)
                    self.assertEqual(result['coverage']['observed_records'], 4)
                    self.assertEqual(sum(x['extracted_messages'] for x in result['conversations']), 2)
                    self.assertIn(identity, [x['conversation'] for x in result['conversations']])

    def test_body_free_output_excludes_unknown_metadata_and_message_ids(self):
        record = self.web('private-id', 'Private but deliberately retained title')
        record['private_metadata'] = 'PRIVATE_UNKNOWN_WEB_METADATA'
        record['mapping']['PRIVATE_NODE_ID'] = record['mapping'].pop('node-0')
        self.write_web([record])
        result = list_export(self.path, 'web')
        encoded = json.dumps(result)
        for forbidden in ('SYNTHETIC_PRIVATE_BODY', 'PRIVATE_UNKNOWN_WEB_METADATA', 'PRIVATE_NODE_ID'):
            self.assertNotIn(forbidden, encoded)
        self.assertIn('Private but deliberately retained title', encoded)
        self.assertIn('private-id', encoded)
        self.assertFalse(result['contains_message_text'])
        self.assertIn('PRIVATE METADATA', result['warning'])
        self.write_local([self.meta('local'), self.message()])
        for kind in ('local', 'local-codex'):
            encoded = json.dumps(list_export(self.path, kind))
            for forbidden in ('DO_NOT_GUESS', 'SYNTHETIC_PRIVATE', 'same-message'):
                self.assertNotIn(forbidden, encoded)

    def test_pagination_sorted_by_ids_with_global_totals_and_limits(self):
        identities = ['한글', 'z', 'a', 'A', 'é']
        self.write_web([self.web(i) for i in identities])
        pages = [list_export(self.path, 'web', limit=2, offset=i) for i in (0, 2, 4, 5)]
        self.assertEqual([x['conversation'] for p in pages for x in p['conversations']], sorted(identities))
        self.assertEqual([p['next_offset'] for p in pages], [2, 4, None, None])
        for page in pages:
            self.assertEqual(page['total_conversations'], 5)
            self.assertEqual(page['selectable_conversations'], 5)
            self.assertEqual(page['coverage']['extracted_messages'], 10)
        self.assertEqual(list_export(self.path, 'web', 1000, 2**63 - 1)['conversations'], [])
        self.assertEqual(len(list_export(self.path, 'web', 1)['conversations']), 1)

    def test_argument_validation_occurs_before_read(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('must validate before reading')):
            for limit in (0, -1, 1001, True, False, 1.0, '1', None):
                with self.subTest(limit=limit), self.assertRaises(ValueError):
                    list_export(self.path, 'web', limit=limit)
            for offset in (-1, 2**63, True, False, 0.0, '0', None):
                with self.subTest(offset=offset), self.assertRaises(ValueError):
                    list_export(self.path, 'web', offset=offset)
            with self.assertRaises(ValueError):
                list_export(self.path, 'unsupported')

    def test_one_immutable_source_read_exact_bytes_hash_and_no_database_calls(self):
        for kind in ('web', 'local', 'local-codex'):
            if kind == 'web':
                self.write_web([self.web('한글')])
            else:
                self.write_local([self.meta('한글'), self.message()], ('\r\n',))
            raw = self.path.read_bytes()
            reader = Path.read_bytes
            calls = []
            def frozen_read(path):
                if path == self.path:
                    calls.append(path)
                    return raw if len(calls) == 1 else b'corrupt second snapshot'
                return reader(path)
            with patch.object(Path, 'read_bytes', frozen_read), patch('sqlite3.connect', side_effect=AssertionError('no DB')):
                result = list_export(self.path, kind)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['original_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(result['coverage']['original_sha256'], result['original_sha256'])
            self.assertEqual(result['original_bytes'], len(raw))
            self.assertEqual(self.path.read_bytes(), raw)
            self.assertFalse(self.db.exists())

    def test_invalid_off_page_web_record_rejects_full_file(self):
        for bad in (dict(id='z', mapping={'bad': dict(parent='missing')}),
                    dict(id='z', title=12, mapping={}), dict(id='z', mapping=[])):
            self.write_web([self.web('a'), bad])
            for offset in (0, 999):
                with self.subTest(bad=bad, offset=offset), self.assertRaises(ValueError):
                    list_export(self.path, 'web', limit=1, offset=offset)

    def test_invalid_off_page_local_boundaries_cannot_inherit_previous_session(self):
        for payload in (None, {}, {'id': 17}):
            self.write_local([self.meta('a'), self.message(), dict(type='session_meta', payload=payload), self.message()])
            for kind in ('local', 'local-codex'):
                with self.subTest(payload=payload, kind=kind), self.assertRaises(ValueError):
                    list_export(self.path, kind, limit=1, offset=999)
        self.write_local([self.message(), self.meta('a')])
        for kind in ('local', 'local-codex'):
            with self.assertRaisesRegex(ValueError, 'no session metadata'):
                list_export(self.path, kind)

    def test_strict_json_and_unsupported_roots_are_rejected(self):
        for raw in (b'{}', b'[null]', b'[{"id":"a","id":"b","mapping":{}}]',
                    b'[{"id":"a","mapping":{},"title":NaN}]', b'\xff'):
            self.path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                list_export(self.path, 'web')
        self.path.write_bytes(b'{"type":"session_meta","payload":{"id":"a","id":"b"}}\n')
        for kind in ('local', 'local-codex'):
            with self.assertRaises(ValueError):
                list_export(self.path, kind)

    def test_both_cli_entrypoints_ascii_parity_without_database(self):
        for kind in ('web', 'local', 'local-codex'):
            if kind == 'web':
                self.write_web([self.web('한글', '합성 제목')])
            else:
                self.write_local([self.meta('한글'), self.message()])
            args = (self.path, '--format', kind, '--limit', '1', '--offset', '0')
            standalone = self.call('export_inventory.py', *args)
            unified = self.call('recap.py', 'list-export', *args)
            self.assertEqual(standalone, unified)
            self.assertEqual(unified, list_export(self.path, kind, 1, 0))
            self.assertEqual(set(p.name for p in Path(self.tmp.name).iterdir()), {self.path.name})

    def test_cli_validation_errors_are_clean_and_create_no_database(self):
        self.write_web([self.web()])
        for script, prefix in (('export_inventory.py', ()), ('recap.py', ('list-export',))):
            for extra in (('--limit', '0'), ('--offset', '-1'), ('--offset', str(2**63))):
                self.call(script, *prefix, self.path, '--format', 'web', *extra, success=False)
        self.assertEqual(set(p.name for p in Path(self.tmp.name).iterdir()), {self.path.name})

    def test_selection_support_does_not_promise_conflict_free_database_import(self):
        self.write_local([self.meta('chat'), self.message(text='First synthetic version'),
                          self.message(text='Conflicting synthetic version')])
        for kind in ('local', 'local-codex'):
            item, = list_export(self.path, kind)['conversations']
            self.assertTrue(item['selection_supported'])
            self.assertEqual(item['extracted_messages'], 2)
            self.assertEqual(len(normalize(self.path, kind, conversation='chat')), 2)
            with self.assertRaisesRegex(ValueError, 'conflicting message identity'):
                import_export(self.db, kind, self.path, kind, 'chat')

    def test_discovered_identity_import_round_trip_and_source_unchanged(self):
        for kind in ('web', 'local', 'local-codex'):
            if kind == 'web':
                self.write_web([self.web('selected'), self.web('unselected')])
            else:
                self.write_local([self.meta('selected'), self.message(), self.meta('unselected'), self.message()])
            raw = self.path.read_bytes()
            item = list_export(self.path, kind, limit=1)['conversations'][0]
            self.assertTrue(item['selection_supported'])
            receipt = import_export(self.db, kind, self.path, kind, item['conversation'])
            self.assertEqual(receipt['inserted'], item['extracted_messages'])
            archived = conversations(self.db, kind)['conversations']
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0]['conversation'], 'selected')
            self.assertEqual(self.path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
