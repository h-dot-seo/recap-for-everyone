"""Synthetic scoped provider-contract regressions; no real corpus or transport."""
import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from recaplib.session_workflow import import_export, titles
from tests.test_attributed_title import label, message, text_part
from tests.test_branch_title import fixture
from tests.test_replay_local import event, turn
from recaplib.title_adapter import (AdapterConfig, AdapterError, MAX_CONTEXT_BYTES, PreparedRequest, generate,
                           check_external_consent, consent_scope, prepare_request, response_proposal)
from recaplib.title_proposal import apply_preview, preview, snapshot


ROOT = Path(__file__).resolve().parents[1]


class ScopedTitleAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.db = self.directory / 'archive.sqlite'
        self.path = self.directory / 'synthetic.json'
        self.mock = AdapterConfig(kind='mock', provider_id='synthetic-mock', model='synthetic-v1')
        self.meta = dict(type='session_meta', payload=dict(id='synthetic'))

    def web(self, data=None):
        data = fixture() if data is None else data
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        import_export(self.db, 'synthetic-source', self.path, 'web')
        return data

    def local(self, records):
        self.path = self.directory / 'synthetic.jsonl'
        self.path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
        import_export(self.db, 'synthetic-source', self.path, 'local-codex')

    def attributed(self):
        records = [self.meta,
                   message([text_part('HARNESS_SECRET'), dict(type='input_image', image_url='synthetic-image'),
                            text_part('합성 과수원 계획')], [label('harness'), {}, label('user')], identity='u1'),
                   message([text_part('Second eligible request')], [label('user')], identity='u2'),
                   message([text_part('ASSISTANT_SECRET', 'output_text')], identity='a', role='assistant')]
        self.local(records)
        return records

    def prepared(self, scope, *, config=AdapterConfig(), node=None):
        return prepare_request(self.db, 'synthetic-source', 'synthetic', config,
                               evidence_scope=scope, input_path=self.path, node=node)

    def rows(self, prepared):
        return json.loads(prepared.payload)['messages']

    def context(self, prepared, scope):
        self.assertIsInstance(prepared.evidence_context, bytes)
        context = json.loads(prepared.evidence_context)
        self.assertEqual(context['mode'], scope)
        self.assertIsInstance(context['selection'], dict)
        self.assertIsInstance(context['adapter_selection'], dict)
        return context

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(AdapterError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def cli(self, *args, success=True, script='title_adapter.py'):
        result = subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                                capture_output=True, timeout=30,
                                env=dict(os.environ, PYTHONIOENCODING='ascii'))
        self.assertEqual(result.returncode == 0, success, result.stderr.decode('ascii', errors='replace'))
        self.assertNotIn(b'Traceback', result.stderr)
        return json.loads(result.stdout) if success else result.stderr.decode('ascii').strip()

    def flags(self, scope):
        return ['--db', self.db, '--source', 'synthetic-source', '--conversation', 'synthetic',
                '--evidence-scope', scope, '--input', self.path]

    def test_raw_contract_and_positional_constructor_remain_unchanged(self):
        self.web()
        prepared = prepare_request(self.db, 'synthetic-source', 'synthetic')
        explicit = prepare_request(self.db, 'synthetic-source', 'synthetic', evidence_scope='raw')
        self.assertEqual(prepared, explicit)
        self.assertEqual(prepared.evidence_context, b'')
        old = PreparedRequest(prepared.source, prepared.conversation, prepared.content_sha256, prepared.payload)
        self.assertEqual(old, prepared)
        proposal = response_proposal(prepared, AdapterConfig(), dict(title='Synthetic title', evidence_message_ids=['old']))
        self.assertNotIn('evidence_context', proposal)
        self.assertEqual(set(proposal), {'source', 'conversation', 'content_sha256', 'title',
                         'evidence_message_ids', 'provider', 'semantic_validation', 'request_sha256'})
        output = self.cli('--db', self.db, '--source', 'synthetic-source', '--conversation', 'synthetic', 'prepare')
        self.assertNotIn('evidence_context', output)

    def test_active_branch_excludes_abandoned_and_explicit_node_selects_it(self):
        self.web()
        active = self.prepared('web-branch')
        self.assertEqual(self.rows(active), [dict(message_id='active', role='user', text='Selected orchard plan')])
        self.assertNotIn(b'Abandoned', active.payload)
        context = self.context(active, 'web-branch')
        self.assertEqual(context['selection']['branch_context']['node_ids'], ['root', 'active'])
        alternate = self.prepared('web-branch', node='old')
        self.assertEqual([row['message_id'] for row in self.rows(alternate)], ['old'])
        self.assertEqual(active.content_sha256, alternate.content_sha256)
        self.assertEqual(active.content_sha256, snapshot(self.db, 'synthetic-source', 'synthetic')[1])

    def test_replay_excludes_rolled_back_turn_and_retains_multiple_users(self):
        self.local([self.meta, *turn('a'), *turn('b'), event('thread_rolled_back', num_turns=1), *turn('c')])
        prepared = self.prepared('local-replay', config=self.mock)
        self.assertEqual([row['message_id'] for row in self.rows(prepared)], ['au', 'cu'])
        self.assertNotIn(b'Synthetic question b', prepared.payload)
        context = self.context(prepared, 'local-replay')
        self.assertEqual(context['selection']['projection_context']['retained_turns'], 2)
        proposal = generate(prepared, self.mock, mock_response=json.dumps(dict(title='Retained questions', evidence_message_ids=['au', 'cu'])))
        self.assertEqual(proposal['evidence_message_ids'], ['au', 'cu'])
        self.assertEqual(proposal['evidence_context'], context)
        self.assert_code('INVALID_RESPONSE', response_proposal, prepared, self.mock,
                         dict(title='Invalid evidence', evidence_message_ids=['bu']))

    def test_attribution_excludes_harness_and_preserves_all_original_indices(self):
        self.attributed()
        prepared = self.prepared('local-attributed')
        self.assertEqual(self.rows(prepared), [dict(message_id='u1', role='user', text='합성 과수원 계획'),
                                              dict(message_id='u2', role='user', text='Second eligible request')])
        self.assertNotIn(b'HARNESS_SECRET', prepared.payload)
        self.assertNotIn(b'ASSISTANT_SECRET', prepared.payload)
        context = self.context(prepared, 'local-attributed')
        attribution = context['selection']['attribution_context']
        self.assertEqual(attribution['evidence_parts'], [
            dict(message_id='u1', origin_locator='line:2', content_indices=[2]),
            dict(message_id='u2', origin_locator='line:3', content_indices=[0])])
        self.assertIs(attribution['producer_attribution_authenticated'], False)
        self.assertEqual(prepared.content_sha256, snapshot(self.db, 'synthetic-source', 'synthetic')[1])

    def test_invalid_scope_combinations_are_rejected_before_database_access(self):
        bad = [dict(evidence_scope='unknown'), dict(evidence_scope=None), dict(evidence_scope=[]),
               dict(evidence_scope='raw', input_path=self.path), dict(evidence_scope='raw', node='active')]
        for scope in ('web-branch', 'local-replay', 'local-attributed'):
            bad.append(dict(evidence_scope=scope))
        for scope in ('local-replay', 'local-attributed'):
            bad.append(dict(evidence_scope=scope, input_path=self.path, node='active'))
        with patch('sqlite3.connect', side_effect=AssertionError('database must not be touched')):
            for kwargs in bad:
                with self.subTest(kwargs=kwargs):
                    self.assert_code('CONFIG_INVALID', prepare_request, self.db, 'synthetic-source', 'synthetic', **kwargs)
        self.assertFalse(self.db.exists())

    def test_missing_or_wrong_sources_never_fall_back_to_raw(self):
        self.web()
        for scope in ('web-branch', 'local-replay', 'local-attributed'):
            with self.subTest(scope=scope):
                self.assert_code('SOURCE_ERROR', prepare_request, self.db, 'synthetic-source', 'synthetic',
                                 evidence_scope=scope, input_path=self.directory / 'PRIVATE_MISSING_INPUT')
        self.assert_code('SOURCE_ERROR', prepare_request, self.db, 'wrong-source', 'synthetic',
                         evidence_scope='web-branch', input_path=self.path)
        self.assert_code('SOURCE_ERROR', prepare_request, self.db, 'synthetic-source', 'wrong-conversation',
                         evidence_scope='web-branch', input_path=self.path)
        self.assert_code('SOURCE_ERROR', self.prepared, 'local-replay')
        self.assert_code('SOURCE_ERROR', self.prepared, 'local-attributed')

    def test_absent_scoped_user_evidence_has_distinct_code(self):
        self.web()
        self.assert_code('NO_USER_EVIDENCE', self.prepared, 'web-branch', node='root')
        self.local([self.meta, *turn('a'), event('thread_rolled_back', num_turns=1)])
        self.assert_code('NO_USER_EVIDENCE', self.prepared, 'local-replay')
        self.local([self.meta, message([text_part('Only harness')], [label('harness')])])
        self.assert_code('NO_USER_EVIDENCE', self.prepared, 'local-attributed')

    def test_replay_unsupported_projection_has_sanitized_source_error(self):
        self.local([self.meta, *turn('a'), dict(type='compacted', payload=dict(replacement_history=[]))])
        self.assert_code('SOURCE_ERROR', self.prepared, 'local-replay')

    def test_unimported_current_node_and_format_changes_are_rejected(self):
        data = self.web()
        data[0]['current_node'] = 'old'
        self.path.write_text(json.dumps(data), encoding='utf-8')
        self.assert_code('SOURCE_ERROR', self.prepared, 'web-branch')
        import_export(self.db, 'synthetic-source', self.path, 'web')
        self.assertEqual(self.rows(self.prepared('web-branch'))[0]['message_id'], 'old')
        self.path.write_text(json.dumps(data, indent=2), encoding='utf-8')
        self.assert_code('SOURCE_ERROR', self.prepared, 'web-branch')

    def test_archived_content_and_provenance_mutations_rejected(self):
        for mutation in ('text', 'role', 'timestamp', 'provenance'):
            with self.subTest(mutation=mutation):
                if self.db.exists():
                    self.db.unlink()
                self.web()
                with closing(sqlite3.connect(self.db)) as connection, connection:
                    if mutation == 'provenance':
                        connection.execute('DELETE FROM export_provenance')
                        connection.execute('DELETE FROM export_occurrences')
                    else:
                        connection.execute('UPDATE messages SET ' + mutation + "='SYNTHETIC_CHANGED' WHERE message_id='active'")
                self.assert_code('SOURCE_ERROR', self.prepared, 'web-branch')

    def test_attributed_nonselected_raw_content_is_still_verified(self):
        self.attributed()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE messages SET text='Altered assistant' WHERE message_id='a'")
        self.assert_code('SOURCE_ERROR', self.prepared, 'local-attributed')

    def test_whole_raw_snapshot_guards_off_branch_changes_after_preparation(self):
        data = self.web()
        proposal = generate(self.prepared('web-branch'))
        reviewed = preview(self.db, proposal)
        data[0]['mapping']['new-old'] = dict(parent='old', message=dict(author=dict(role='user'), content=dict(parts=['New abandoned branch'])))
        self.web(data)
        with self.assertRaises(ValueError):
            preview(self.db, proposal)
        with self.assertRaises(ValueError):
            apply_preview(self.db, reviewed)
        self.assertEqual(titles(self.db, 'synthetic-source', 'synthetic')['revision'], 0)

    def test_scope_selection_happens_before_twenty_message_bound(self):
        data = fixture()
        for index in range(30):
            data[0]['mapping']['off-' + str(index)] = dict(parent='root', message=dict(
                author=dict(role='user'), create_time=100 + index, content=dict(parts=['Excluded late request ' + str(index)])))
        self.web(data)
        prepared = self.prepared('web-branch')
        self.assertEqual([row['message_id'] for row in self.rows(prepared)], ['active'])
        self.assertNotIn(b'Excluded late', prepared.payload)

    def test_attributed_scope_precedes_bounds_and_keeps_full_selection_context(self):
        records = [self.meta, message([text_part('Early genuine question')], [label('user')], identity='early')]
        records.extend(message([text_part('Late harness ' + str(i))], [label('harness')], identity='h' + str(i)) for i in range(30))
        self.local(records)
        prepared = self.prepared('local-attributed')
        self.assertEqual([row['message_id'] for row in self.rows(prepared)], ['early'])
        self.assertEqual(self.context(prepared, 'local-attributed')['selection']['attribution_context']['coverage']['excluded_text_parts'], 30)

    def test_twenty_message_limit_and_response_whitelist_use_prepared_evidence(self):
        self.local([self.meta] + [message([text_part('Question ' + str(i))], [label('user')], identity='u' + str(i)) for i in range(25)])
        prepared = self.prepared('local-attributed', config=self.mock)
        self.assertEqual([row['message_id'] for row in self.rows(prepared)], ['u' + str(i) for i in range(5, 25)])
        context = self.context(prepared, 'local-attributed')
        self.assertEqual(len(context['selection']['attribution_context']['evidence_parts']), 25)
        self.assertEqual(context['adapter_selection'], dict(user_occurrences=25, unique_user_messages=25,
                         included_messages=20, omitted_messages=5, truncated_messages=0))
        for identity in ('u0', 'line:7', 'missing'):
            self.assert_code('INVALID_RESPONSE', response_proposal, prepared, self.mock,
                             dict(title='Synthetic title', evidence_message_ids=[identity]))
        proposal = response_proposal(prepared, self.mock, dict(title='Synthetic title', evidence_message_ids=['u5', 'u24'],
                                                              evidence_context={'injected': True}))
        self.assertEqual(proposal['evidence_context'], context)

    def test_character_limits_apply_after_attributed_parts_are_selected(self):
        self.local([self.meta] + [message([text_part('Harness' * 1000), text_part('한' * 5000 + str(i))],
                    [label('harness'), label('user')], identity='u' + str(i)) for i in range(5)])
        prepared = self.prepared('local-attributed')
        rows = self.rows(prepared)
        self.assertEqual([row['message_id'] for row in rows], ['u2', 'u3', 'u4'])
        self.assertEqual([len(row['text']) for row in rows], [4000, 4000, 4000])
        self.assertNotIn(b'Harness', prepared.payload)
        self.assertLessEqual(len(prepared.payload), 65536)
        self.assertEqual(self.context(prepared, 'local-attributed')['adapter_selection'], dict(
            user_occurrences=5, unique_user_messages=5, included_messages=3, omitted_messages=2, truncated_messages=3))

    def test_repeated_identical_id_collapses_at_most_recent_occurrence(self):
        repeated = message([text_part('Same selected question')], [label('user')], identity='repeat')
        middle = message([text_part('Middle question')], [label('user')], identity='middle')
        self.local([self.meta, repeated, middle, copy.deepcopy(repeated)])
        prepared = self.prepared('local-attributed')
        self.assertEqual([row['message_id'] for row in self.rows(prepared)], ['middle', 'repeat'])
        parts = self.context(prepared, 'local-attributed')['selection']['attribution_context']['evidence_parts']
        self.assertEqual([part['origin_locator'] for part in parts], ['line:2', 'line:3', 'line:4'])
        self.assertEqual(generate(prepared)['evidence_message_ids'], ['middle'])
        self.assertEqual(self.context(prepared, 'local-attributed')['adapter_selection'], dict(
            user_occurrences=3, unique_user_messages=2, included_messages=2, omitted_messages=0, truncated_messages=0))

    def test_repeated_id_with_different_attribution_text_is_ambiguous(self):
        first = message([text_part('First question'), text_part('Second question')], [label('user'), label('harness')])
        second = message([text_part('First question'), text_part('Second question')], [label('harness'), label('user')])
        self.local([self.meta, first, second])
        self.assertEqual(len(snapshot(self.db, 'synthetic-source', 'synthetic')[0]), 1)
        self.assert_code('SOURCE_ERROR', self.prepared, 'local-attributed')

    def test_preparation_is_deterministic_readonly_and_reads_input_once(self):
        for scope in ('web-branch', 'local-replay', 'local-attributed'):
            with self.subTest(scope=scope):
                if self.db.exists():
                    self.db.unlink()
                if scope == 'web-branch':
                    self.web()
                elif scope == 'local-replay':
                    self.local([self.meta, *turn('a')])
                else:
                    self.attributed()
                before_db, before_input = self.db.read_bytes(), self.path.read_bytes()
                original = Path.read_bytes
                reads = []
                def read(path):
                    if path == self.path:
                        reads.append(path)
                    return original(path)
                with patch.object(Path, 'read_bytes', read):
                    prepared = self.prepared(scope)
                self.assertEqual(len(reads), 1)
                self.assertEqual(prepared, self.prepared(scope))
                self.assertEqual(self.db.read_bytes(), before_db)
                self.assertEqual(self.path.read_bytes(), before_input)

    def test_scoped_unicode_cli_prepare_generate_preview_apply_search(self):
        self.attributed()
        original = self.path.read_bytes()
        prepared = self.cli(*self.flags('local-attributed'), 'prepare')
        self.assertEqual(prepared['evidence_context']['mode'], 'local-attributed')
        self.assertEqual(prepared['payload']['messages'][0]['text'], '합성 과수원 계획')
        response = self.directory / 'response.json'
        response.write_text(json.dumps(dict(title='합성 과수원 설계', evidence_message_ids=['u1'])), encoding='utf-8')
        proposal = self.cli(*self.flags('local-attributed'), '--kind', 'mock', '--model', 'synthetic-v1',
                            'generate', '--response', response)
        self.assertEqual(proposal['title'], '합성 과수원 설계')
        self.assertEqual(proposal['evidence_message_ids'], ['u1'])
        saved = self.directory / 'proposal.json'
        saved.write_text(json.dumps(proposal), encoding='utf-8')
        reviewed = self.cli('--db', self.db, 'preview', saved, script='title_proposal.py')
        saved.write_text(json.dumps(reviewed), encoding='utf-8')
        self.cli('--db', self.db, 'apply', saved, script='title_proposal.py')
        found = self.cli('--db', self.db, 'find', 'HARNESS_SECRET', script='recap.py')
        self.assertEqual(found['total_matches'], 1)
        found_title = self.cli('--db', self.db, 'find', '합성 과수원 설계', script='recap.py')
        self.assertEqual(found_title['total_matches'], 1)
        self.assertEqual(titles(self.db, 'synthetic-source', 'synthetic')['display_title'], '합성 과수원 설계')
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_frozen_context_rejected_before_worker_launch(self):
        self.web()
        prepared = self.prepared('web-branch')
        invalid = [None, {}, 'not-bytes', b'not-json', b'[]', b'{}', b'\xff',
                   b'x' * (MAX_CONTEXT_BYTES + 1),
                   json.dumps(dict(mode='raw', selection={}, adapter_selection={})).encode(),
                   json.dumps(dict(mode='web-branch', selection=[], adapter_selection={})).encode(),
                   b'{"mode":"web-branch","mode":"local-replay","selection":{},"adapter_selection":{}}',
                   b'{"mode":"web-branch","selection":{"value":1e999},"adapter_selection":{}}']
        with patch('recaplib.title_adapter.multiprocessing.get_context', side_effect=AssertionError('must not launch')):
            for context in invalid:
                with self.subTest(type=type(context).__name__, length=len(context) if context is not None else 0):
                    self.assert_code('REQUEST_INVALID', generate, replace(prepared, evidence_context=context))
        with patch('recaplib.title_adapter.MAX_CONTEXT_BYTES', 1):
            self.assert_code('REQUEST_INVALID', self.prepared, 'web-branch')

    def test_replay_reused_explicit_id_remains_unsupported(self):
        first, second = turn('a'), turn('b')
        second[1]['payload']['message'] = first[1]['payload']['message']
        second[2]['payload'] = copy.deepcopy(first[2]['payload'])
        self.local([self.meta, *first, *second])
        self.assert_code('SOURCE_ERROR', self.prepared, 'local-replay')

    def test_attribution_label_change_without_reimport_is_source_error(self):
        records = self.attributed()
        records[1]['payload']['internal_chat_message_metadata_passthrough']['content_item_metadata'] = [label('user'), {}, label('harness')]
        self.path.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
        self.assert_code('SOURCE_ERROR', self.prepared, 'local-attributed')

    def test_supplied_only_queue_accepts_scoped_adapter_proposal_without_fallback(self):
        from recaplib.title_batch import review_queue
        self.attributed()
        proposal = generate(self.prepared('local-attributed'))
        before = self.db.read_bytes()
        with patch('recaplib.title_batch.excerpt', side_effect=AssertionError('no raw fallback')):
            queue = review_queue(self.db, 'synthetic-source', supplied_proposals=[proposal], supplied_only=True)
        self.assertTrue(queue['supplied_only'])
        self.assertEqual(queue['ready_count'], 1)
        self.assertEqual(queue['items'][0]['proposal'], proposal)
        self.assertEqual(self.db.read_bytes(), before)

    def test_each_scope_cli_prepares_and_generates_locally(self):
        for scope in ('web-branch', 'local-replay', 'local-attributed'):
            with self.subTest(scope=scope):
                if self.db.exists():
                    self.db.unlink()
                if scope == 'web-branch':
                    self.web()
                elif scope == 'local-replay':
                    self.local([self.meta, *turn('a')])
                else:
                    self.attributed()
                prepared = self.cli(*self.flags(scope), 'prepare')
                generated = self.cli(*self.flags(scope), 'generate')
                self.assertEqual(prepared['evidence_context'], generated['evidence_context'])
                self.assertEqual(prepared['payload_sha256'], generated['request_sha256'])
                self.assertEqual(prepared['content_sha256'], generated['content_sha256'])
                self.assertEqual(generated['provider'], 'local-extractive')
                self.assertTrue(set(generated['evidence_message_ids']) <= {
                    row['message_id'] for row in prepared['payload']['messages']})

    def test_scoped_consent_is_bound_to_selected_payload_without_transport(self):
        self.web()
        config = AdapterConfig(kind='external', provider_id='synthetic-provider', model='synthetic-model',
                               endpoint='https://example.invalid/title', external_enabled=True)
        active = self.prepared('web-branch', config=config)
        alternate = self.prepared('web-branch', config=config, node='old')
        consent = dict(approved=True, **consent_scope(active, config))
        self.assertEqual(consent['payload_sha256'], active.payload_sha256)
        self.assertNotEqual(active.payload_sha256, alternate.payload_sha256)
        self.assertNotIn('evidence_context', json.loads(active.payload))
        self.assertNotIn('branch_context', json.loads(active.payload))
        with patch('recaplib.title_adapter.multiprocessing.get_context', side_effect=AssertionError('must not launch')):
            self.assert_code('CONSENT_REQUIRED', check_external_consent, alternate, config, consent)
            self.assert_code('EXTERNAL_NOT_CONFIGURED', generate, active, config, consent=consent)

    def test_cli_invalid_scope_combinations_and_missing_input_are_sanitized(self):
        base = ['--db', self.db, '--source', 'synthetic-source', '--conversation', 'synthetic']
        for extra in (['--input', self.path], ['--node', 'active'], ['--evidence-scope', 'web-branch'],
                      ['--evidence-scope', 'local-replay', '--input', self.path, '--node', 'active']):
            with self.subTest(extra=extra):
                self.assertEqual(self.cli(*base, *extra, 'prepare', success=False), 'CONFIG_INVALID')
        self.assertFalse(self.db.exists())
        self.web()
        self.path.unlink()
        self.assertEqual(self.cli(*self.flags('web-branch'), 'generate', success=False), 'SOURCE_ERROR')


if __name__ == '__main__':
    unittest.main()
