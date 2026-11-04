"""Independent synthetic regressions for explicit adapter evidence selection."""
import copy
import hashlib
import io
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import title_adapter as adapter
from attributed_title import attributed_evidence
from branch_title import branch_evidence
from conversation_search import find
from replay_title import replay_evidence
from session_workflow import import_export, titles
from title_proposal import apply_preview, preview, snapshot


ROOT = Path(__file__).resolve().parent
TOPIC = 'Compare synthetic orchard irrigation schedules'
META = dict(type='session_meta', payload=dict(id='synthetic'))


def message(identity, texts, kinds=None, role='user'):
    payload = dict(type='message', role=role, content=[
        dict(type='input_text' if role == 'user' else 'output_text', text=text) for text in texts])
    if identity is not None:
        payload['id'] = identity
    if kinds is not None:
        payload['internal_chat_message_metadata_passthrough'] = dict(
            content_item_metadata=[dict(provenance=dict(type=kind)) for kind in kinds])
    return dict(type='response_item', payload=payload)


def event(kind, **values):
    return dict(type='event_msg', payload=dict(type=kind, **values))


def turn(identity, text):
    return [event('task_started', turn_id=identity), event('user_message', message=text),
            message(identity, [text]), message(identity + '-assistant', ['Synthetic answer'], role='assistant'),
            event('task_complete', turn_id=identity)]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


class AdapterMessageSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = self.root / 'archive.sqlite'
        self.path = self.root / 'synthetic.jsonl'
        self.config = adapter.AdapterConfig(kind='external', provider_id='synthetic-provider',
            model='synthetic-model', endpoint='https://example.invalid/synthetic-only')
        self.response = dict(title='Synthetic orchard irrigation schedules', evidence_message_ids=['topic'])

    def local(self, records):
        self.path = self.root / 'synthetic.jsonl'
        self.path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
        import_export(self.db, 'synthetic-source', self.path, 'local-codex')

    def web(self):
        def node(parent, text, role='user'):
            return dict(parent=parent, message=dict(author=dict(role=role),
                create_time=1, content=dict(parts=[text])))
        self.path = self.root / 'synthetic-web.json'
        data = [dict(id='synthetic', title='Original synthetic title', current_node='assistant', mapping={
            'root': dict(parent=None), 'opening': node('root', 'Synthetic opening question'),
            'topic': node('opening', TOPIC), 'assistant': node('topic', 'Synthetic answer', 'assistant'),
            'excluded': node('opening', 'Abandoned synthetic request')})]
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        import_export(self.db, 'synthetic-source', self.path, 'web')
        return data

    def load(self, scope):
        self.db = self.root / (scope + '.sqlite')
        if scope in ('raw', 'web-branch'):
            self.web()
        elif scope == 'local-replay':
            self.local([META, *turn('opening', 'Synthetic opening question'),
                        *turn('discarded', 'Discarded synthetic request'),
                        event('thread_rolled_back', num_turns=1), *turn('topic', TOPIC)])
        else:
            self.local([META, message('opening', ['Synthetic opening question'], ['user']),
                        message('topic', ['SYNTHETIC_HARNESS_SECRET', TOPIC], ['harness', 'user']),
                        message('assistant', ['Synthetic answer'], role='assistant'),
                        message('unknown', ['Unknown synthetic text']),
                        message('harness', ['Only synthetic harness'], ['harness'])])

    def options(self, scope='raw', **kwargs):
        return dict(evidence_scope=scope, input_path=self.path if scope != 'raw' else None, **kwargs)

    def prepare(self, scope='raw', **kwargs):
        return adapter.prepare_request(self.db, 'synthetic-source', 'synthetic', self.config,
                                       **self.options(scope, **kwargs))

    def document(self, scope='raw', **kwargs):
        return adapter.request_document(self.prepare(scope, **kwargs), self.config)

    def complete(self, document, scope='raw', response=None, **kwargs):
        return adapter.complete_response(self.db, 'synthetic-source', 'synthetic', document,
            self.response if response is None else response, self.config, **self.options(scope, **kwargs))

    def rows(self, prepared):
        return json.loads(prepared.payload)['messages']

    def selection(self, scope='raw', message_id='topic', origin_locator=None, selected_origin_locator=None):
        return dict(schema='recap.title-selection.v1', evidence_scope=scope, message_id=message_id,
                    origin_locator=origin_locator, selected_origin_locator=selected_origin_locator,
                    authenticated=False)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(adapter.AdapterError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(statement, parameters)

    def archive_rows(self):
        with closing(sqlite3.connect(self.db)) as connection:
            existing = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            return {table: connection.execute('SELECT * FROM ' + table).fetchall()
                    for table in ('messages', 'export_provenance', 'export_occurrences', 'exports')
                    if table in existing}

    def flags(self, scope='raw', message_id=None, origin_locator=None):
        result = ['--db', str(self.db), '--source', 'synthetic-source', '--conversation', 'synthetic',
                  '--kind', 'external', '--provider-id', self.config.provider_id, '--model', self.config.model,
                  '--endpoint', self.config.endpoint, '--evidence-scope', scope]
        if scope != 'raw':
            result += ['--input', str(self.path)]
        if message_id is not None:
            result += ['--message', message_id]
        if origin_locator is not None:
            result += ['--origin-locator', origin_locator]
        return result

    def cli(self, *arguments, code=None):
        result = subprocess.run([sys.executable, str(ROOT / 'title_adapter.py'), *map(str, arguments)],
            capture_output=True, text=True, encoding='ascii', timeout=30,
            env=dict(os.environ, PYTHONIOENCODING='ascii'))
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(result.returncode, 0 if code is None else 1, result.stderr)
        if code is not None:
            self.assertEqual(result.stdout, '')
            self.assertEqual(result.stderr, code + '\n')
            return result
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def test_old_topic_survives_explicit_selection_through_complete_preview_apply_find(self):
        self.local([META, message('topic', [TOPIC], ['user'])] + [
            message('thanks-' + str(index), ['Thanks'], ['user']) for index in range(20)])
        original, archived = self.path.read_bytes(), self.db.read_bytes()
        rows_before = self.archive_rows()
        found = find(self.db, 'orchard irrigation')
        self.assertEqual(found['total_matches'], 1)
        self.assertEqual(found['matches'][0]['message_matches'][0]['message_id'], 'topic')
        default = self.document('local-attributed')
        self.assertEqual(len(default['payload']['messages']), 20)
        self.assertNotIn('topic', [row['message_id'] for row in default['payload']['messages']])
        self.assert_code('INVALID_RESPONSE', self.complete, default, 'local-attributed')
        selected = self.document('local-attributed', message_id='topic')
        self.assertEqual(selected['payload']['messages'], [dict(message_id='topic', role='user', text=TOPIC)])
        with (patch('title_adapter.generate', side_effect=AssertionError('no provider execution')),
              patch('title_adapter.multiprocessing.get_context', side_effect=AssertionError('no model worker')),
              patch('subprocess.Popen', side_effect=AssertionError('no subprocess')),
              patch('socket.socket', side_effect=AssertionError('no network'))):
            proposal = self.complete(selected, 'local-attributed', message_id='topic')
        self.assertEqual(proposal['evidence_selection'], selected['evidence_selection'])
        self.assertEqual(proposal['provider_execution'], 'NOT_PERFORMED')
        reviewed = preview(self.db, proposal)
        self.assertEqual((self.path.read_bytes(), self.db.read_bytes()), (original, archived))
        self.assertEqual(titles(self.db, 'synthetic-source', 'synthetic')['revision'], 0)
        result = apply_preview(self.db, reviewed)
        self.assertEqual(result['display_title'], self.response['title'])
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.archive_rows(), rows_before)
        found = find(self.db, 'orchard irrigation')['matches'][0]
        self.assertTrue(found['matched_title'])
        self.assertEqual(found['display_title'], self.response['title'])

    def test_no_selector_retains_exact_legacy_payload_context_and_document_shape(self):
        for scope in adapter.EVIDENCE_SCOPES:
            with self.subTest(scope=scope):
                self.load(scope)
                if scope == 'raw':
                    rows, digest = snapshot(self.db, 'synthetic-source', 'synthetic')
                    context = None
                else:
                    reader = {'web-branch': branch_evidence, 'local-replay': replay_evidence,
                              'local-attributed': attributed_evidence}[scope]
                    rows, digest, context = reader(self.db, 'synthetic-source', 'synthetic', self.path)
                users = [dict(message_id=row['message_id'], role='user', text=row['text'])
                         for row in rows if row['role'] == 'user']
                payload = canonical(dict(protocol='recap.title.v1', model=self.config.model,
                                         instruction=adapter.INSTRUCTION, messages=users))
                expected_context = b'' if context is None else canonical(dict(mode=scope, selection=context,
                    adapter_selection=dict(user_occurrences=len(users), unique_user_messages=len(users),
                        included_messages=len(users), omitted_messages=0, truncated_messages=0)))
                legacy = adapter.PreparedRequest('synthetic-source', 'synthetic', digest, payload, expected_context)
                actual = self.prepare(scope)
                self.assertEqual(actual, legacy)
                self.assertEqual(actual, self.prepare(scope, message_id=None, origin_locator=None))
                document = adapter.request_document(actual, self.config)
                expected_keys = {'source', 'conversation', 'content_sha256', 'payload_sha256', 'payload',
                                 'warning', 'consent_scope'}
                if scope != 'raw':
                    expected_keys.add('evidence_context')
                self.assertEqual(set(document), expected_keys)
                self.assertEqual(actual.evidence_selection, b'')
                self.assertNotIn('evidence_selection', self.complete(document, scope))

    def test_all_scopes_freeze_exact_local_selection_without_outbound_leakage(self):
        for scope in adapter.EVIDENCE_SCOPES:
            with self.subTest(scope=scope):
                self.load(scope)
                prepared = self.prepare(scope, message_id='topic')
                expected = self.selection(scope, selected_origin_locator='line:3' if scope == 'local-attributed' else None)
                self.assertEqual(prepared.evidence_selection, canonical(expected))
                self.assertEqual(prepared.content_sha256, snapshot(self.db, 'synthetic-source', 'synthetic')[1])
                payload = json.loads(prepared.payload)
                self.assertEqual(set(payload), {'protocol', 'model', 'instruction', 'messages'})
                self.assertEqual(payload['messages'], [dict(message_id='topic', role='user', text=TOPIC)])
                document = adapter.request_document(prepared, self.config)
                response = dict(self.response, evidence_selection={'forged': True}, evidence_context={'forged': True})
                proposal = adapter.response_proposal(prepared, self.config, response)
                self.assertEqual(document['evidence_selection'], expected)
                self.assertEqual(proposal['evidence_selection'], expected)
                document['evidence_selection']['message_id'] = 'modified'
                proposal['evidence_selection']['authenticated'] = True
                self.assertEqual(adapter.request_document(prepared, self.config)['evidence_selection'], expected)
                if scope == 'raw':
                    self.assertEqual(prepared.evidence_context, b'')
                    self.assertNotIn('evidence_context', proposal)
                else:
                    default_context = json.loads(self.prepare(scope).evidence_context)
                    context = json.loads(prepared.evidence_context)
                    self.assertEqual(context['selection'], default_context['selection'])
                    self.assertEqual(context['adapter_selection'], dict(
                        user_occurrences=2, unique_user_messages=2, included_messages=1,
                        omitted_messages=1, truncated_messages=0))

    def test_invalid_selector_shapes_fail_before_source_database_or_completion_document_reads(self):
        cases = [dict(message_id=value) for value in ('', False, 0, [], {}, b'topic')]
        cases += [dict(evidence_scope='local-attributed', input_path=self.path, message_id='topic',
                       origin_locator=value) for value in
                  ('', 'line:0', 'line:01', 'line:-1', 'line:+1', 'line:1.0', 'line:١',
                   'line:1\n', ' line:1', 'line:1 ', 'LINE:1', 1, False, [], {})]
        cases += [dict(evidence_scope='local-attributed', input_path=self.path, origin_locator='line:2')]
        cases += [dict(evidence_scope=scope, input_path=self.path if scope != 'raw' else None,
                       message_id='topic', origin_locator='line:2') for scope in ('raw', 'web-branch', 'local-replay')]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), patch('sqlite3.connect', side_effect=AssertionError('database read')), \
                    patch.object(Path, 'read_bytes', side_effect=AssertionError('source read')):
                self.assert_code('CONFIG_INVALID', adapter.prepare_request, self.db, 'synthetic-source',
                                 'synthetic', self.config, **kwargs)
                self.assert_code('CONFIG_INVALID', adapter.complete_response, self.db, 'synthetic-source',
                                 'synthetic', {}, {}, self.config, **kwargs)
        self.assertFalse(self.db.exists())
        self.assertFalse(self.path.exists())

    def test_no_selector_preserves_legacy_malformed_saved_input_precedence(self):
        with patch('sqlite3.connect', side_effect=AssertionError('database read')):
            self.assert_code('REQUEST_INVALID', adapter.complete_response, self.db, 'synthetic-source',
                             'synthetic', [], {}, self.config, evidence_scope='invalid')
            self.assert_code('INVALID_RESPONSE', adapter.complete_response, self.db, 'synthetic-source',
                             'synthetic', {}, [], self.config, evidence_scope='invalid')
        self.cli(*self.flags('raw'), '--input', self.path, 'complete-response',
                 self.root / 'missing-request.json', self.root / 'missing-response.json', code='REQUEST_INVALID')
        self.assertFalse(self.db.exists())

    def test_cli_invalid_selector_rejected_before_reading_saved_request_or_response(self):
        cases = [self.flags('raw', 'topic', 'line:2'), self.flags('local-attributed', 'topic', 'line:01'),
                 self.flags('local-attributed', origin_locator='line:2')]
        for flags in cases:
            with self.subTest(flags=flags):
                arguments = ['title_adapter.py', *flags, 'complete-response', 'missing-request', 'missing-response']
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(sys, 'argv', arguments), redirect_stdout(stdout), redirect_stderr(stderr), \
                        patch('title_adapter._read_object', side_effect=AssertionError('saved file read')):
                    with self.assertRaises(SystemExit) as caught:
                        adapter.main()
                self.assertEqual(caught.exception.code, 1)
                self.assertEqual(stdout.getvalue(), '')
                self.assertEqual(stderr.getvalue(), 'CONFIG_INVALID\n')

    def test_missing_nonuser_and_out_of_scope_ids_never_fall_back(self):
        cases = {'raw': ('assistant', 'missing'), 'web-branch': ('assistant', 'excluded', 'missing'),
                 'local-replay': ('topic-assistant', 'discarded', 'missing'),
                 'local-attributed': ('assistant', 'unknown', 'harness', 'missing')}
        for scope, identities in cases.items():
            self.load(scope)
            before = self.db.read_bytes()
            for identity in identities:
                with self.subTest(scope=scope, identity=identity):
                    self.assert_code('SOURCE_ERROR', self.prepare, scope, message_id=identity)
            self.assertEqual(self.db.read_bytes(), before)

    def test_exact_unicode_ids_do_not_trim_casefold_or_normalize(self):
        identities = ['topic', ' topic ', 'é', 'e\u0301', '주제🌱']
        self.local([META] + [message(identity, ['Request ' + str(index)], ['user'])
                            for index, identity in enumerate(identities)])
        for scope in ('raw', 'local-attributed'):
            for index, identity in enumerate(identities):
                with self.subTest(scope=scope, identity=identity):
                    prepared = self.prepare(scope, message_id=identity)
                    self.assertEqual(self.rows(prepared), [dict(message_id=identity, role='user', text='Request ' + str(index))])
                    self.assertEqual(json.loads(prepared.evidence_selection)['message_id'], identity)
            for identity in ('Topic', 'TOPIC', 'topic\n', '주제', ' '):
                self.assert_code('SOURCE_ERROR', self.prepare, scope, message_id=identity)

    def test_web_branch_endpoint_cannot_select_later_or_other_fork(self):
        self.load('web-branch')
        self.assert_code('SOURCE_ERROR', self.prepare, 'web-branch', node='opening', message_id='topic')
        self.assert_code('SOURCE_ERROR', self.prepare, 'web-branch', message_id='excluded')
        alternate = self.prepare('web-branch', node='excluded', message_id='excluded')
        self.assertEqual(self.rows(alternate)[0]['text'], 'Abandoned synthetic request')
        self.assertEqual(json.loads(alternate.evidence_context)['selection']['branch_context']['node_ids'],
                         ['root', 'opening', 'excluded'])
        self.assertEqual(alternate.content_sha256, self.prepare('web-branch', message_id='topic').content_sha256)
        raw = self.prepare('raw', message_id='excluded')
        self.assertEqual(self.rows(raw)[0]['message_id'], 'excluded')
        self.assertEqual(raw.evidence_context, b'')

    def test_replay_renamed_idless_source_uses_archived_ids_not_projection_ids(self):
        records = [META, *turn('opening', 'Synthetic opening question'), *turn('topic', TOPIC)]
        for row in records:
            if row['type'] == 'response_item':
                row['payload'].pop('id')
        self.local(records)
        rows, _, context = replay_evidence(self.db, 'synthetic-source', 'synthetic', self.path)
        identity = next(row['message_id'] for row in rows if row['text'] == TOPIC)
        projection = next(row['projection_id'] for row in context['projection_context']['evidence_mappings']
                          if row['archive_message_id'] == identity)
        renamed = self.root / 'renamed synthetic source.jsonl'
        renamed.write_bytes(self.path.read_bytes())
        self.path = renamed
        prepared = self.prepare('local-replay', message_id=identity)
        self.assertEqual(self.rows(prepared), [dict(message_id=identity, role='user', text=TOPIC)])
        self.assertNotEqual(identity, projection)
        self.assert_code('SOURCE_ERROR', self.prepare, 'local-replay', message_id=projection)
        response = dict(self.response, evidence_message_ids=[identity])
        self.complete(adapter.request_document(prepared, self.config), 'local-replay', response=response, message_id=identity)

    def test_repeated_attributed_ids_require_locator_even_for_identical_text(self):
        repeated = message('topic', [TOPIC], ['user'])
        self.local([META, repeated, copy.deepcopy(repeated)])
        self.assertEqual(len(self.rows(self.prepare('local-attributed'))), 1)
        self.assert_code('SOURCE_ERROR', self.prepare, 'local-attributed', message_id='topic')
        first = self.prepare('local-attributed', message_id='topic', origin_locator='line:2')
        second = self.prepare('local-attributed', message_id='topic', origin_locator='line:3')
        self.assertEqual(first.payload, second.payload)
        self.assertNotEqual(first.evidence_selection, second.evidence_selection)
        unqualified = dict(json.loads(first.evidence_selection), origin_locator=None)
        self.assert_code('REQUEST_INVALID', adapter.request_document,
                         replace(first, evidence_selection=canonical(unqualified)), self.config)
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, adapter.request_document(first, self.config),
                         'local-attributed', message_id='topic', origin_locator='line:3')
        self.assert_code('SOURCE_ERROR', self.prepare, 'local-attributed', message_id='topic', origin_locator='line:99')

    def test_different_attribution_for_same_id_can_be_selected_without_default_dedup(self):
        texts = ['First synthetic topic', 'Second synthetic topic']
        self.local([META, message('topic', texts, ['user', 'harness']),
                    message('topic', texts, ['harness', 'user'])])
        self.assert_code('SOURCE_ERROR', self.prepare, 'local-attributed')
        self.assert_code('SOURCE_ERROR', self.prepare, 'local-attributed', message_id='topic')
        for line, text in ((2, texts[0]), (3, texts[1])):
            prepared = self.prepare('local-attributed', message_id='topic', origin_locator='line:' + str(line))
            self.assertEqual(self.rows(prepared), [dict(message_id='topic', role='user', text=text)])
            context = json.loads(prepared.evidence_context)
            self.assertEqual(context['adapter_selection'], dict(user_occurrences=2, unique_user_messages=1,
                             included_messages=1, omitted_messages=0, truncated_messages=0))
            self.assertEqual(context['selection']['attribution_context']['evidence_parts'], [
                dict(message_id='topic', origin_locator='line:2', content_indices=[0]),
                dict(message_id='topic', origin_locator='line:3', content_indices=[1])])
            self.complete(adapter.request_document(prepared, self.config), 'local-attributed',
                          message_id='topic', origin_locator='line:' + str(line))

        self.local([META, message('topic', texts, ['user', 'harness']),
                    message('topic', texts, ['harness', 'user']), message('other', [TOPIC], ['user'])])
        self.assertEqual(self.rows(self.prepare('local-attributed', message_id='other')),
                         [dict(message_id='other', role='user', text=TOPIC)])

    def test_noneligible_duplicate_does_not_make_unique_attributed_choice_ambiguous(self):
        texts = [TOPIC, 'Excluded harness text']
        self.local([META, message('topic', texts, ['user', 'harness']),
                    message('topic', texts, ['harness', 'harness'])])
        prepared = self.prepare('local-attributed', message_id='topic')
        self.assertEqual(self.rows(prepared)[0]['text'], TOPIC)
        self.assertEqual(json.loads(prepared.evidence_selection)['selected_origin_locator'], 'line:2')
        self.assert_code('SOURCE_ERROR', self.prepare, 'local-attributed', message_id='topic', origin_locator='line:3')

    def test_user_part_alignment_survives_nontext_content_and_raw_does_not_claim_attribution(self):
        selected = message('topic', ['SYNTHETIC_HARNESS_SECRET', TOPIC], ['harness', 'user'])
        selected['payload']['content'].insert(1, dict(type='input_image', image_url='synthetic-image'))
        selected['payload']['internal_chat_message_metadata_passthrough']['content_item_metadata'].insert(1, {})
        self.local([META, selected])
        attributed = self.prepare('local-attributed', message_id='topic')
        raw = self.prepare('raw', message_id='topic')
        self.assertEqual(self.rows(attributed)[0]['text'], TOPIC)
        self.assertNotIn(b'SYNTHETIC_HARNESS_SECRET', attributed.payload)
        self.assertIn(b'SYNTHETIC_HARNESS_SECRET', raw.payload)
        self.assertEqual(raw.evidence_context, b'')
        self.assertIsNone(json.loads(raw.evidence_selection)['selected_origin_locator'])
        parts = json.loads(attributed.evidence_context)['selection']['attribution_context']['evidence_parts']
        self.assertEqual(parts, [dict(message_id='topic', origin_locator='line:2', content_indices=[2])])
        self.assertEqual(raw.content_sha256, attributed.content_sha256)

    def test_malformed_attribution_elsewhere_is_checked_before_selecting_good_occurrence(self):
        malformed = message('unselected', ['Malformed metadata elsewhere'], ['user'])
        malformed['payload']['internal_chat_message_metadata_passthrough']['content_item_metadata'] = []
        self.local([META, message('topic', [TOPIC], ['user']), malformed])
        self.assert_code('SOURCE_ERROR', self.prepare, 'local-attributed', message_id='topic', origin_locator='line:2')

    def test_complete_scope_content_and_provenance_are_checked_before_explicit_choice(self):
        for scope, other in (('web-branch', 'opening'), ('local-replay', 'discarded'),
                             ('local-attributed', 'assistant')):
            for mutation in ('text', 'provenance'):
                with self.subTest(scope=scope, mutation=mutation):
                    self.load(scope)
                    if mutation == 'text':
                        self.sql('UPDATE messages SET text=? WHERE message_id=?', ('Changed unselected content', other))
                    else:
                        for table in ('export_provenance', 'export_occurrences'):
                            self.sql('DELETE FROM ' + table + ' WHERE message=?', (other,))
                    self.assert_code('SOURCE_ERROR', self.prepare, scope, message_id='topic')
                    self.db.unlink()

    def test_source_byte_hash_change_is_not_hidden_by_same_chosen_text(self):
        self.load('local-attributed')
        document = self.document('local-attributed', message_id='topic')
        self.path.write_bytes(self.path.read_bytes() + b'\n')
        self.assert_code('SOURCE_ERROR', self.complete, document, 'local-attributed', message_id='topic')
        import_export(self.db, 'synthetic-source', self.path, 'local-codex')
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, document, 'local-attributed', message_id='topic')

    def test_whole_conversation_mutation_outside_selected_message_stales_completion_and_apply(self):
        for scope in ('raw', 'web-branch'):
            with self.subTest(scope=scope):
                self.load(scope)
                document = self.document(scope, message_id='topic')
                proposal = self.complete(document, scope, message_id='topic')
                reviewed = preview(self.db, proposal)
                self.sql("UPDATE messages SET text='Changed off-branch raw evidence' WHERE message_id='excluded'")
                self.assert_code('PREPARED_REQUEST_STALE', self.complete, document, scope, message_id='topic')
                with self.assertRaisesRegex(ValueError, 'snapshot'):
                    preview(self.db, proposal)
                with self.assertRaisesRegex(ValueError, 'snapshot'):
                    apply_preview(self.db, reviewed)
                self.assertEqual(titles(self.db, 'synthetic-source', 'synthetic')['revision'], 0)

    def test_single_user_raw_saved_recipe_cannot_be_dropped_when_payload_is_identical(self):
        self.local([META, message('topic', [TOPIC], ['user'])])
        default = self.document()
        selected = self.document(message_id='topic')
        self.assertEqual(default['payload'], selected['payload'])
        self.assertEqual(default['payload_sha256'], selected['payload_sha256'])
        self.assertNotEqual(default, selected)
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, selected)
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, default, message_id='topic')
        self.assertEqual(self.complete(selected, message_id='topic')['evidence_selection'], selected['evidence_selection'])

    def test_requested_locator_is_frozen_separately_from_unique_resolved_locator(self):
        self.local([META, message('topic', [TOPIC], ['user'])])
        implicit = self.document('local-attributed', message_id='topic')
        explicit = self.document('local-attributed', message_id='topic', origin_locator='line:2')
        self.assertEqual(implicit['payload'], explicit['payload'])
        self.assertEqual(implicit['evidence_selection'], self.selection('local-attributed', selected_origin_locator='line:2'))
        self.assertEqual(explicit['evidence_selection'], self.selection('local-attributed', origin_locator='line:2',
                                                                      selected_origin_locator='line:2'))
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, implicit, 'local-attributed',
                         message_id='topic', origin_locator='line:2')
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, explicit, 'local-attributed', message_id='topic')

    def test_completion_rejects_edited_or_removed_selection_and_different_message(self):
        self.load('web-branch')
        document = self.document('web-branch', message_id='topic')
        for field, replacement in (('message_id', 'opening'), ('authenticated', True),
                                   ('selected_origin_locator', 'line:3')):
            changed = copy.deepcopy(document)
            changed['evidence_selection'][field] = replacement
            self.assert_code('PREPARED_REQUEST_STALE', self.complete, changed, 'web-branch', message_id='topic')
        changed = copy.deepcopy(document)
        del changed['evidence_selection']
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, changed, 'web-branch', message_id='topic')
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, document, 'web-branch', message_id='opening')
        self.assert_code('INVALID_RESPONSE', self.complete, document, 'web-branch',
                         message_id='topic', response=dict(self.response, evidence_message_ids=['opening']))

    def test_malformed_in_memory_selection_metadata_has_fixed_request_error(self):
        self.load('raw')
        prepared = self.prepare(message_id='topic')
        valid = json.loads(prepared.evidence_selection)
        malformed = [None, 'not bytes', b'{}', b'not json', canonical(dict(valid, authenticated=True)),
                     canonical(dict(valid, origin_locator='line:2')), canonical(dict(valid, unknown='extra')),
                     canonical(dict(valid, message_id='opening')), canonical(dict(valid, evidence_scope='web-branch')),
                     b' ' * (adapter.MAX_SELECTION_BYTES + 1)]
        for value in malformed:
            with self.subTest(value=repr(value)[:80]):
                changed = replace(prepared, evidence_selection=value)
                self.assert_code('REQUEST_INVALID', adapter.request_document, changed, self.config)
                self.assert_code('REQUEST_INVALID', adapter.response_proposal, changed, self.config, self.response)

    def test_explicit_selection_preserves_4000_character_and_65536_byte_bounds(self):
        text = '🌱' * 5000
        self.local([META, message('topic', [text], ['user'])])
        for scope in ('raw', 'local-attributed'):
            prepared = self.prepare(scope, message_id='topic')
            self.assertEqual(self.rows(prepared)[0]['text'], text[:4000])
            self.assertLessEqual(len(prepared.payload), 65536)
        payload_overhead = len(canonical(dict(protocol='recap.title.v1', model=self.config.model,
            instruction=adapter.INSTRUCTION, messages=[dict(message_id='', role='user', text='x')])))
        exact_id = 'x' * (65536 - payload_overhead)
        self.db = self.root / 'exact-bound.sqlite'
        self.local([META, message(exact_id, ['x'], ['user'])])
        self.assertEqual(len(self.prepare(message_id=exact_id).payload), 65536)
        huge_id = exact_id + 'x'
        self.db = self.root / 'oversized.sqlite'
        self.local([META, message(huge_id, ['x'], ['user'])])
        self.assert_code('REQUEST_INVALID', self.prepare, message_id=huge_id)

    def test_default_total_character_limit_and_payload_validator_remain_12000(self):
        self.local([META] + [message('user-' + str(index), ['한' * 5000], ['user']) for index in range(5)])
        default = self.prepare('local-attributed')
        self.assertEqual([len(row['text']) for row in self.rows(default)], [4000, 4000, 4000])
        self.assertEqual([row['message_id'] for row in self.rows(default)], ['user-2', 'user-3', 'user-4'])
        selected = self.prepare('local-attributed', message_id='user-0')
        self.assertEqual([len(row['text']) for row in self.rows(selected)], [4000])
        payload = json.loads(default.payload)
        payload['messages'].append(dict(message_id='extra', role='user', text='x'))
        self.assert_code('REQUEST_INVALID', adapter.request_document, replace(default, payload=canonical(payload)), self.config)

    def test_external_transport_stays_disabled_or_unconfigured_with_explicit_selection(self):
        self.load('raw')
        prepared = self.prepare(message_id='topic')
        with patch('socket.socket', side_effect=AssertionError('no network')):
            self.assert_code('EXTERNAL_DISABLED', adapter.generate, prepared, self.config)
            enabled = replace(self.config, external_enabled=True)
            self.assert_code('CONSENT_REQUIRED', adapter.generate, prepared, enabled)
            consent = dict(adapter.consent_scope(prepared, enabled), approved=True)
            self.assert_code('EXTERNAL_NOT_CONFIGURED', adapter.generate, prepared, enabled, consent=consent)

    def test_local_and_mock_generators_receive_only_explicitly_selected_user(self):
        self.load('raw')
        for config in (adapter.AdapterConfig(), adapter.AdapterConfig(kind='mock', provider_id='synthetic-mock')):
            with self.subTest(kind=config.kind):
                prepared = adapter.prepare_request(self.db, 'synthetic-source', 'synthetic', config, message_id='topic')
                kwargs = {'mock_response': json.dumps(self.response)} if config.kind == 'mock' else {}
                proposal = adapter.generate(prepared, config, **kwargs)
                self.assertEqual(proposal['evidence_message_ids'], ['topic'])
                self.assertEqual(proposal['evidence_selection'], self.selection())

    def test_cli_native_output_and_bom_saved_files_keep_explicit_recipe_readonly(self):
        self.local([META, message('주제🌱', ['합성 과수원 관개 일정'], ['user'])])
        flags = self.flags('local-attributed', '주제🌱', 'line:2')
        expected = self.document('local-attributed', message_id='주제🌱', origin_locator='line:2')
        original, archived = self.path.read_bytes(), self.db.read_bytes()
        request = self.root / '요청 with spaces.json'
        proposal_file = self.root / '제안 with spaces.json'
        receipt = self.cli(*flags, 'prepare', '--output', request)
        self.assertEqual(receipt['document_kind'], 'request')
        self.assertEqual(receipt['sha256'], hashlib.sha256(request.read_bytes()).hexdigest())
        self.assertEqual(json.loads(request.read_text(encoding='utf-8')), expected)
        self.assertNotIn('evidence_selection', receipt)
        request.write_bytes(b'\xef\xbb\xbf' + request.read_bytes())
        response = self.root / 'response with BOM.json'
        response.write_bytes(b'\xef\xbb\xbf' + canonical(dict(title='합성 과수원 관개 일정', evidence_message_ids=['주제🌱'])))
        receipt = self.cli(*flags, 'complete-response', request, response, '--output', proposal_file)
        self.assertEqual(receipt['document_kind'], 'proposal')
        proposal = json.loads(proposal_file.read_text(encoding='utf-8'))
        self.assertEqual(proposal['evidence_selection'], expected['evidence_selection'])
        self.assertEqual(proposal['provider_execution'], 'NOT_PERFORMED')
        self.assertEqual((self.path.read_bytes(), self.db.read_bytes()), (original, archived))
        before = proposal_file.read_bytes()
        self.cli(*flags, 'complete-response', request, response, '--output', proposal_file, code='OUTPUT_FAILED')
        self.assertEqual(proposal_file.read_bytes(), before)
        self.assertEqual(list(self.root.glob('.recap-title-*')), [])


    def test_published_ten_command_workflow_saves_reviews_and_applies_separately(self):
        document = (ROOT / 'docs' / 'ADAPTER_MESSAGE_SELECTION.md').read_text(encoding='utf-8')
        commands = [line for line in document.splitlines()
                    if line.startswith(('mkdir ', 'python recap.py ', 'python title_adapter.py '))]
        self.assertEqual(len(commands), 10)
        scratch = self.root / 'published flow with spaces'
        source = ROOT / 'examples' / 'adapter-message-focus.jsonl'
        response = ROOT / 'examples' / 'adapter-message-response.json'
        originals = (source.read_bytes(), response.read_bytes())
        receipts = []
        archive_bytes = archive_evidence = None
        applied = False
        results = []
        for command in commands:
            # Tokenize the portable published command first, before substituting
            # native paths whose Windows backslashes must never be shell escapes.
            arguments = [part.replace('../recap-adapter-focus-demo', str(scratch))
                         for part in shlex.split(command)]
            if arguments[0] == 'mkdir':
                Path(arguments[1]).mkdir()
                continue
            if 'apply-title' in arguments:
                self.assertEqual(self.db.read_bytes(), archive_bytes)
                reviewed = json.loads((scratch / 'reviewed.json').read_text(encoding='utf-8'))
                self.assertEqual(reviewed['expected_revision'], 0)
                self.assertEqual(reviewed['proposal']['source'], 'demo')
                self.assertEqual(reviewed['proposal']['conversation'], 'synthetic-adapter-focus')
                self.assertEqual(reviewed['proposal']['evidence_message_ids'], ['topic'])
                self.assertEqual(reviewed['proposal']['title'], 'Synthetic orchard irrigation comparison')
            result = subprocess.run([sys.executable, *arguments[1:]], cwd=ROOT,
                capture_output=True, text=True, encoding='ascii', timeout=30,
                env=dict(os.environ, PYTHONIOENCODING='ascii'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            output = json.loads(result.stdout)
            results.append(output)
            self.db = scratch / 'archive.sqlite'
            if 'import' in arguments:
                archive_bytes = self.db.read_bytes()
                archive_evidence = self.archive_rows()
            elif 'apply-title' not in arguments and not applied:
                self.assertEqual(self.db.read_bytes(), archive_bytes)
            if '--output' in arguments:
                saved = Path(arguments[arguments.index('--output') + 1])
                raw = saved.read_bytes()
                self.assertEqual(output['schema'], 'recap.saved-title-json.v1')
                self.assertEqual(output['status'], 'SAVED')
                self.assertEqual(output['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(output['bytes'], len(raw))
                self.assertEqual(output['encoding'], 'UTF-8')
                self.assertTrue(output['staging_cleanup_complete'])
                self.assertIsNone(output['remaining_staging_file'])
                self.assertNotIn('payload', output)
                self.assertNotIn('evidence_selection', output)
                receipts.append(output)
            if 'apply-title' in arguments:
                self.assertEqual(output['display_title'], 'Synthetic orchard irrigation comparison')
                applied = True
            self.assertEqual((source.read_bytes(), response.read_bytes()), originals)
        self.assertEqual([value['document_kind'] for value in receipts], ['request', 'request', 'proposal', 'preview'])
        self.assertEqual(self.archive_rows(), archive_evidence)
        recent = json.loads((scratch / 'recent.json').read_text(encoding='utf-8'))
        focused = json.loads((scratch / 'focused.json').read_text(encoding='utf-8'))
        self.assertEqual([row['message_id'] for row in recent['payload']['messages']],
                         ['followup-' + str(index).zfill(2) for index in range(1, 21)])
        self.assertEqual(focused['payload']['messages'], [dict(message_id='topic', role='user', text=TOPIC)])
        self.assertNotIn('evidence_selection', recent)
        self.assertEqual(focused['evidence_selection'], self.selection('local-attributed', selected_origin_locator='line:2'))
        self.assertEqual(results[-1]['total_matches'], 1)
        self.assertTrue(results[-1]['matches'][0]['matched_title'])
        self.assertEqual(results[-1]['matches'][0]['display_title'], 'Synthetic orchard irrigation comparison')
        self.assertEqual(list(scratch.glob('.recap-title-*')), [])

if __name__ == '__main__':
    unittest.main()
