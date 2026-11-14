"""Offline saved-request completion: synthetic files only, no provider execution."""
import copy
import hashlib
from tests._cli import run_cli
import recap
from recaplib import title_proposal
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from recaplib import title_adapter as adapter
from recaplib.session_workflow import import_export, titles
from tests.test_attributed_title import label, message, text_part
from tests.test_branch_title import fixture
from tests.test_replay_local import event, turn
from recaplib.title_proposal import apply_preview, preview

ROOT = Path(__file__).resolve().parents[1]


def documented_arguments(line, scratch):
    # Tokenize published relative paths before substituting Windows paths.
    return [part.replace('../recap-response-demo', str(scratch)) for part in shlex.split(line)]


class SavedTitleResponseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.db = self.directory / 'archive.sqlite'
        self.path = self.directory / 'synthetic.json'
        self.config = adapter.AdapterConfig(kind='external', provider_id='synthetic-provider',
            model='synthetic-model', endpoint='https://EXAMPLE.invalid:443/title')
        self.response = dict(title='합성 과수원 설계 🌱', evidence_message_ids=['active'])
        self.data = fixture()
        self.web()

    def web(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        import_export(self.db, 'synthetic-source', self.path, 'web')

    def local(self, scope):
        self.path = self.directory / 'synthetic.jsonl'
        meta = dict(type='session_meta', payload=dict(id='synthetic'))
        if scope == 'local-replay':
            rows = [meta, *turn('a'), *turn('b'), event('thread_rolled_back', num_turns=1)]
            identity = 'au'
        else:
            rows = [meta, message([text_part('HARNESS_PRIVATE'), text_part('합성 과수원 계획')],
                                  [label('harness'), label('user')], identity='u1')]
            identity = 'u1'
        self.path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
        import_export(self.db, 'synthetic-source', self.path, 'local-codex')
        return dict(title='합성 과수원 설계 🌱', evidence_message_ids=[identity])

    def options(self, scope='raw', node=None):
        return dict(evidence_scope=scope, input_path=self.path if scope != 'raw' else None, node=node)

    def prepared(self, scope='raw', config=None, node=None):
        config = config or self.config
        return adapter.prepare_request(self.db, 'synthetic-source', 'synthetic', config, **self.options(scope, node))

    def document(self, scope='raw', config=None, node=None):
        config = config or self.config
        return adapter.request_document(self.prepared(scope, config, node), config)

    def complete(self, document, response=None, config=None, scope='raw', node=None):
        return adapter.complete_response(self.db, 'synthetic-source', 'synthetic', document,
            self.response if response is None else response, config or self.config, **self.options(scope, node))

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(adapter.AdapterError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def flags(self, scope='raw', config=None, db=None):
        config = config or self.config
        flags = ['--db', str(db or self.db), '--source', 'synthetic-source', '--conversation', 'synthetic',
                 '--kind', config.kind, '--provider-id', config.provider_id, '--model', config.model]
        if config.endpoint:
            flags.extend(['--endpoint', config.endpoint])
        if config.external_enabled:
            flags.append('--allow-external')
        if scope != 'raw':
            flags.extend(['--evidence-scope', scope, '--input', str(self.path)])
        return flags

    def cli(self, *args, script='title_adapter.py', code=None):
        entry = {'title_adapter.py': adapter.main, 'title_proposal.py': title_proposal.main,
                 'recap.py': recap.main}[script]
        result = run_cli(entry, list(map(str, args)))
        result.stdout = result.stdout.encode('ascii'); result.stderr = result.stderr.encode('ascii')
        self.assertNotIn(b'Traceback', result.stderr)
        if code:
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stderr.decode('ascii').strip(), code)
            self.assertEqual(result.stdout, b'')
            return
        self.assertEqual(result.returncode, 0, result.stderr.decode('ascii', errors='replace'))
        return json.loads(result.stdout)

    def save(self, name, document):
        path = self.directory / name
        path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        return path

    def test_raw_completion_is_repeatable_readonly_and_never_executes_provider(self):
        document = self.document()
        before, original = self.db.read_bytes(), self.path.read_bytes()
        with (patch('recaplib.title_adapter.generate', side_effect=AssertionError('no generate')),
             patch('recaplib.title_adapter.multiprocessing.get_context', side_effect=AssertionError('no worker')),
             patch('subprocess.Popen', side_effect=AssertionError('no subprocess')),
             patch('socket.socket', side_effect=AssertionError('no transport'))):
            first = self.complete(document)
            self.assertEqual(first, self.complete(document))
        self.assertEqual(first['provider'], 'external-adapter')
        self.assertEqual(first['response_origin'], 'supplied_local_file')
        self.assertEqual(first['provider_execution'], 'NOT_PERFORMED')
        self.assertEqual(first['semantic_validation'], 'NOT_PERFORMED')
        self.assertEqual(first['request_sha256'], document['payload_sha256'])
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(titles(self.db, 'synthetic-source', 'synthetic')['revision'], 0)
        self.assertEqual(apply_preview(self.db, preview(self.db, first))['display_title'], self.response['title'])

    def test_all_scoped_roundtrips_keep_frozen_context(self):
        for scope in ('web-branch', 'local-replay', 'local-attributed'):
            with self.subTest(scope=scope):
                response = self.response if scope == 'web-branch' else self.local(scope)
                document = self.document(scope)
                before = self.db.read_bytes()
                proposal = self.complete(document, response, scope=scope)
                self.assertEqual(proposal['evidence_context'], document['evidence_context'])
                self.assertEqual(proposal['evidence_message_ids'], response['evidence_message_ids'])
                preview(self.db, proposal)
                self.assertEqual(self.db.read_bytes(), before)

    def test_complete_compares_entire_document_not_only_claimed_hashes(self):
        document = self.document('web-branch')
        changes = [(['source'], 'another-source'), (['conversation'], 'another-conversation'),
            (['content_sha256'], '0' * 64), (['payload_sha256'], '0' * 64),
            (['payload', 'model'], 'altered-model'), (['payload', 'instruction'], 'Altered instruction'),
            (['payload', 'messages', 0, 'text'], 'Injected user text'),
            (['payload', 'messages', 0, 'message_id'], 'old'),
            (['consent_scope', 'provider_id'], 'altered-provider'),
            (['consent_scope', 'endpoint'], 'https://example.invalid/other'),
            (['consent_scope', 'model'], 'altered-model'),
            (['consent_scope', 'payload_sha256'], '0' * 64),
            (['evidence_context', 'mode'], 'local-replay'),
            (['evidence_context', 'adapter_selection', 'included_messages'], 99),
            (['evidence_context', 'selection'], {}), (['warning'], 'Altered warning')]
        for path, value in changes:
            with self.subTest(path=path):
                changed = copy.deepcopy(document)
                target = changed
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.assert_code('PREPARED_REQUEST_STALE', self.complete, changed, scope='web-branch')
        for key in document:
            changed = copy.deepcopy(document)
            del changed[key]
            self.assert_code('PREPARED_REQUEST_STALE', self.complete, changed, scope='web-branch')
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, dict(document, extra='ignored?'), scope='web-branch')

    def test_recomputed_payload_hash_cannot_legitimize_modified_body(self):
        document = self.document()
        document['payload']['messages'][0]['text'] = 'Operator-injected request'
        digest = hashlib.sha256(json.dumps(document['payload'], ensure_ascii=False, sort_keys=True,
            separators=(',', ':')).encode('utf-8')).hexdigest()
        document['payload_sha256'] = digest
        document['consent_scope']['payload_sha256'] = digest
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, document)

    def test_current_provider_endpoint_and_model_are_bound(self):
        document = self.document()
        for config in (replace(self.config, provider_id='other-provider'),
                       replace(self.config, model='other-model'),
                       replace(self.config, endpoint='https://example.invalid/other')):
            self.assert_code('PREPARED_REQUEST_STALE', self.complete, document, config=config)
        normalized = replace(self.config, endpoint='https://example.invalid/title')
        self.assertEqual(self.complete(document), self.complete(document, config=normalized))

    def test_frozen_payload_and_consent_identity_match_exact_prepare_contract(self):
        prepared = self.prepared('web-branch')
        document = adapter.request_document(prepared, self.config)
        self.assertEqual(document['payload_sha256'], hashlib.sha256(prepared.payload).hexdigest())
        self.assertEqual(document['consent_scope'], adapter.consent_scope(prepared, self.config))
        self.assertEqual(document['payload'], json.loads(prepared.payload))
        self.assertEqual(document['consent_scope']['endpoint'], 'https://example.invalid/title')
        self.assertNotIn('evidence_context', document['payload'])
        self.assertEqual(document, self.cli(*self.flags('web-branch'), 'prepare'))

    def test_scope_and_explicit_node_cannot_be_silently_changed(self):
        document = self.document('web-branch')
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, document)
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, document, scope='web-branch', node='old')
        alternate = self.document('web-branch', node='old')
        proposal = self.complete(alternate, dict(title='Abandoned plan', evidence_message_ids=['old']),
                                 scope='web-branch', node='old')
        self.assertEqual(proposal['evidence_message_ids'], ['old'])

    def test_offbranch_change_and_reimport_invalidates_saved_snapshot(self):
        raw, scoped = self.document(), self.document('web-branch')
        self.data[0]['mapping']['new-old'] = dict(parent='old', message=dict(author=dict(role='user'),
            content=dict(parts=['Another abandoned request'])))
        self.web()
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, raw)
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, scoped, scope='web-branch')
        self.complete(self.document('web-branch'), scope='web-branch')

    def test_unimported_scoped_bytes_fail_source_check_before_comparison(self):
        document = self.document('web-branch')
        self.path.write_text(json.dumps(self.data, indent=2), encoding='utf-8')
        self.assert_code('SOURCE_ERROR', self.complete, document, scope='web-branch')
        import_export(self.db, 'synthetic-source', self.path, 'web')
        self.assert_code('PREPARED_REQUEST_STALE', self.complete, document, scope='web-branch')

    def test_identical_source_renamed_file_is_not_a_new_request_identity(self):
        document = self.document('web-branch')
        new_path = self.path.with_name('renamed-synthetic.json')
        self.path.rename(new_path)
        self.path = new_path
        self.assertEqual(document, self.document('web-branch'))
        self.complete(document, scope='web-branch')

    def test_completion_requires_external_kind_but_not_enable_or_consent(self):
        document = self.document()
        for kind in ('local', 'mock'):
            self.assert_code('CONFIG_INVALID', self.complete, document, config=adapter.AdapterConfig(kind=kind))
        self.assertEqual(self.complete(document), self.complete(document,
            config=replace(self.config, external_enabled=True)))
        for endpoint in ('http://example.invalid/title', '', 'https://example.invalid/title?secret=x',
                         'https://example.invalid/#fragment', 'https://synthetic:invalid@localhost/title'):
            self.assert_code('CONFIG_INVALID', self.complete, document, config=replace(self.config, endpoint=endpoint))

    def test_external_generation_stays_disabled_or_unconfigured(self):
        prepared = self.prepared()
        consent = dict(approved=True, **adapter.consent_scope(prepared, self.config))
        self.assert_code('EXTERNAL_DISABLED', adapter.generate, prepared, self.config, consent=consent)
        self.assert_code('EXTERNAL_NOT_CONFIGURED', adapter.generate, prepared,
            replace(self.config, external_enabled=True), consent=consent)

    def test_response_fields_and_evidence_are_whitelisted(self):
        document = self.document('web-branch')
        response = dict(self.response, provider='CLAIMED_REAL_PROVIDER', provider_execution='PERFORMED',
            response_origin='network', evidence_context={'injected': True}, raw_private_body='PRIVATE_MARKER')
        result = self.complete(document, response, scope='web-branch')
        self.assertEqual(result['provider'], 'external-adapter')
        self.assertEqual(result['provider_execution'], 'NOT_PERFORMED')
        self.assertEqual(result['response_origin'], 'supplied_local_file')
        self.assertEqual(result['evidence_context'], document['evidence_context'])
        self.assertNotIn('PRIVATE_MARKER', json.dumps(result))
        for evidence in ([], ['old'], ['missing'], ['active', 'active'], 'active', [1], [None]):
            self.assert_code('INVALID_RESPONSE', self.complete, document,
                dict(self.response, evidence_message_ids=evidence), scope='web-branch')
        for title in ('', '\ud800', 'line\nbreak'):
            self.assert_code('INVALID_RESPONSE', self.complete, document,
                dict(self.response, title=title), scope='web-branch')

    def test_api_objects_are_strict_bounded_json_before_database_access(self):
        document = self.document()
        bad_documents = [None, [], 'PRIVATE_MARKER', {'bad': float('nan')}, {'bad': float('inf')},
                         {'bad': '\ud800'}, {'bad': object()}, {'bad': 'x' * (8 * 1024 * 1024)}]
        bad_responses = [None, [], 'PRIVATE_MARKER', {'bad': float('nan')}, {'bad': float('inf')},
                         {'bad': '\ud800'}, {'bad': object()}, dict(self.response, extra='x' * 16384)]
        with patch('sqlite3.connect', side_effect=AssertionError('no database access')):
            for value in bad_documents:
                self.assert_code('REQUEST_INVALID', adapter.complete_response, self.db, 'synthetic-source',
                                 'synthetic', value, self.response, self.config)
            for value in bad_responses:
                self.assert_code('INVALID_RESPONSE', adapter.complete_response, self.db, 'synthetic-source',
                                 'synthetic', document, value, self.config)
        self.assertEqual(adapter.MAX_PREPARED_DOCUMENT_BYTES, 8 * 1024 * 1024)
        self.assertEqual(adapter.MAX_RESPONSE_BYTES, 16384)

    def test_cli_malformed_or_oversized_files_fail_before_missing_database(self):
        document = self.save('prepared.json', self.document())
        response = self.save('response.json', self.response)
        missing_db = self.directory / 'PRIVATE_MISSING.sqlite'
        bad = [b'PRIVATE_MARKER', b'[]', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}',
               b'{"x":"\\ud800"}', b'\xff', b'{"x":']
        for target, code, limit in ((document, 'REQUEST_INVALID', 8 * 1024 * 1024),
                                    (response, 'INVALID_RESPONSE', 16384)):
            good = target.read_bytes()
            for payload in [*bad, b' ' * (limit + 1)]:
                with self.subTest(target=target.name, size=len(payload)):
                    target.write_bytes(payload)
                    self.cli(*self.flags(db=missing_db), 'complete-response', document, response, code=code)
                    self.assertFalse(missing_db.exists())
            target.write_bytes(good)
        document.unlink()
        self.cli(*self.flags(db=missing_db), 'complete-response', document, response, code='REQUEST_INVALID')
        self.assertFalse(missing_db.exists())

    def test_unicode_cli_completion_fresh_preview_apply_and_search(self):
        original = self.path.read_bytes()
        document = self.cli(*self.flags('web-branch'), 'prepare')
        request_file = self.save('prepared.json', document)
        response_file = self.save('response.json', self.response)
        before = self.db.read_bytes()
        proposal = self.cli(*self.flags('web-branch'), 'complete-response', request_file, response_file)
        self.assertEqual(proposal['title'], self.response['title'])
        self.assertEqual(self.db.read_bytes(), before)
        proposal_file = self.save('proposal.json', proposal)
        reviewed = self.cli('--db', self.db, 'preview', proposal_file, script='title_proposal.py')
        review_file = self.save('reviewed.json', reviewed)
        self.cli('--db', self.db, 'apply', review_file, script='title_proposal.py')
        found = self.cli('--db', self.db, 'find', self.response['title'], script='recap.py')
        self.assertEqual(found['total_matches'], 1)
        self.assertEqual(self.path.read_bytes(), original)

    def test_cli_complete_rejects_local_mock_and_accepts_external_enable_states(self):
        request_file = self.save('prepared.json', self.document())
        response_file = self.save('response.json', self.response)
        for kind in ('local', 'mock'):
            self.cli(*self.flags(config=adapter.AdapterConfig(kind=kind)), 'complete-response',
                     request_file, response_file, code='CONFIG_INVALID')
        for enabled in (False, True):
            result = self.cli(*self.flags(config=replace(self.config, external_enabled=enabled)),
                              'complete-response', request_file, response_file)
            self.assertEqual(result['provider_execution'], 'NOT_PERFORMED')

    def test_canonical_comparison_rejects_numeric_type_substitution(self):
        document = self.document('web-branch')
        for replacement in (True, 1.0):
            changed = copy.deepcopy(document)
            changed['evidence_context']['adapter_selection']['included_messages'] = replacement
            self.assert_code('PREPARED_REQUEST_STALE', self.complete, changed, scope='web-branch')
        reordered = dict(reversed(list(document.items())))
        self.assertEqual(self.complete(document, scope='web-branch'),
                         self.complete(reordered, scope='web-branch'))

    def test_response_limit_counts_utf8_bytes_not_characters(self):
        document = self.document()
        response = dict(self.response, ignored='한' * 6000)
        self.assertLess(len(json.dumps(response, ensure_ascii=False)), adapter.MAX_RESPONSE_BYTES)
        self.assert_code('INVALID_RESPONSE', self.complete, document, response)

    def test_preview_content_and_revision_guards_survive_completion(self):
        document = self.document()
        proposal = self.complete(document)
        reviewed = preview(self.db, proposal)
        titles(self.db, 'synthetic-source', 'synthetic', 'Independent reviewed title', 0)
        with self.assertRaises(ValueError):
            apply_preview(self.db, reviewed)
        # A title revision is not a content mutation: a fresh preview still works.
        self.assertEqual(self.complete(document), proposal)
        current = preview(self.db, proposal)
        self.data[0]['mapping']['new'] = dict(parent='active', message=dict(author=dict(role='user'),
            content=dict(parts=['Additional synthetic detail'])))
        self.web()
        with self.assertRaises(ValueError):
            preview(self.db, proposal)
        with self.assertRaises(ValueError):
            apply_preview(self.db, current)

    def test_generate_cli_provider_input_combinations_remain_fail_closed(self):
        response_file = self.save('response.json', self.response)
        consent_file = self.save('consent.json', dict(approved=True,
            **adapter.consent_scope(self.prepared(), self.config)))
        for kind in ('local', 'mock', 'external'):
            config = self.config if kind == 'external' else adapter.AdapterConfig(kind=kind)
            for has_response in (False, True):
                for has_consent in (False, True):
                    with self.subTest(kind=kind, response=has_response, consent=has_consent):
                        extras = []
                        if has_response:
                            extras.extend(['--response', response_file])
                        if has_consent:
                            extras.extend(['--consent', consent_file])
                        if has_response and kind != 'mock' or has_consent and kind != 'external':
                            code = 'CONFIG_INVALID'
                        elif kind == 'external':
                            code = 'EXTERNAL_DISABLED'
                        elif kind == 'mock' and not has_response:
                            code = 'INVALID_RESPONSE'
                        else:
                            code = None
                        result = self.cli(*self.flags(config=config), 'generate', *extras, code=code)
                        if code is None:
                            self.assertNotIn('provider_execution', result)

    def test_documented_argument_substitution_preserves_windows_paths(self):
        for scratch in ('/tmp/synthetic directory', r'C:\synthetic directory\response'):
            args = documented_arguments('python recap.py --db ../recap-response-demo/archive.sqlite '
                'find "experimental design" > ../recap-response-demo/result.json', scratch)
            self.assertEqual(args[3], scratch + '/archive.sqlite')
            self.assertEqual(args[5], 'experimental design')
            self.assertEqual(args[-1], scratch + '/result.json')

    def test_documented_saved_response_commands_require_explicit_review(self):
        document = (ROOT / 'docs/SAVED_TITLE_RESPONSE.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', document, re.S)
        self.assertEqual(len(blocks), 2)
        scratch = self.directory / 'documented demo'
        source = ROOT / 'examples/web-export.json'
        response = ROOT / 'examples/synthetic-title-response.json'
        originals = {path: path.read_bytes() for path in (source, response)}
        review_checked = applied = searched = False
        native_saved = 0
        for line in '\n'.join(blocks).splitlines():
            if not line.strip():
                continue
            args = documented_arguments(line, scratch)
            if args[0] == 'mkdir':
                self.assertEqual(args, ['mkdir', str(scratch)])
                scratch.mkdir()
                continue
            self.assertEqual(args[0], 'python')
            self.assertIn(args[1], ('recap.py', 'title_adapter.py'))
            args[0] = sys.executable
            self.assertNotIn('>', args, 'documented flow must use native saving')
            if 'apply-title' in args:
                prepared = json.loads((scratch / 'prepared.json').read_bytes())
                reviewed = json.loads((scratch / 'reviewed.json').read_bytes())
                self.assertEqual(prepared['source'], 'demo')
                self.assertEqual(prepared['conversation'], 'synthetic-chat')
                self.assertEqual(prepared['evidence_context']['mode'], 'web-branch')
                self.assertEqual(prepared['evidence_context']['selection']['branch_context']['node_ids'], ['m1', 'm2'])
                self.assertEqual(prepared['evidence_context']['selection']['branch_context']['original_sha256'],
                                 hashlib.sha256(originals[source]).hexdigest())
                self.assertEqual([row['message_id'] for row in prepared['payload']['messages']], ['m1'])
                self.assertEqual(reviewed['proposal']['source'], 'demo')
                self.assertEqual(reviewed['proposal']['conversation'], 'synthetic-chat')
                self.assertEqual(reviewed['proposal']['title'], 'Synthetic orchard experimental design')
                self.assertEqual(reviewed['proposal']['response_origin'], 'supplied_local_file')
                self.assertEqual(reviewed['proposal']['provider_execution'], 'NOT_PERFORMED')
                self.assertEqual(reviewed['previous_title'], 'New chat')
                self.assertEqual(reviewed['expected_revision'], 0)
                self.assertEqual(titles(scratch / 'archive.sqlite', 'demo', 'synthetic-chat')['revision'], 0)
                review_checked = True
            native_output = Path(args[args.index('--output') + 1]) if '--output' in args else None
            before_db = (scratch / 'archive.sqlite').read_bytes() if (scratch / 'archive.sqlite').exists() else None
            result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=30,
                                    env=dict(os.environ, PYTHONIOENCODING='ascii'))
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            if native_output is not None:
                native_saved += 1
                raw = native_output.read_bytes()
                expected_kind = ('request' if 'prepare' in args else 'preview' if 'preview-title' in args else 'proposal')
                self.assertEqual(value['status'], 'SAVED')
                self.assertEqual(value['document_kind'], expected_kind)
                self.assertEqual(value['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(value['bytes'], len(raw))
                self.assertEqual(value['encoding'], 'UTF-8')
                self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
                self.assertNotIn(str(native_output), json.dumps(value))
                self.assertEqual((scratch / 'archive.sqlite').read_bytes(), before_db)
            if 'apply-title' in args:
                self.assertTrue(review_checked)
                self.assertEqual(value['display_title'], 'Synthetic orchard experimental design')
                applied = True
            if 'find' in args:
                self.assertTrue(applied)
                self.assertEqual(value['total_matches'], 1)
                searched = True
        self.assertTrue(review_checked and applied and searched)
        self.assertEqual(native_saved, 3)
        for path, before in originals.items():
            self.assertEqual(path.read_bytes(), before)

    def test_default_prepare_output_remains_byte_contract_compatible(self):
        config = adapter.AdapterConfig()
        prepared = self.prepared(config=config)
        expected = dict(source=prepared.source, conversation=prepared.conversation,
            content_sha256=prepared.content_sha256, payload_sha256=prepared.payload_sha256,
            payload=json.loads(prepared.payload),
            warning='PRIVATE USER TEXT: local preparation only; no transmission performed')
        self.assertEqual(adapter.request_document(prepared), expected)
        self.assertEqual(self.cli(*self.flags(config=config), 'prepare'), expected)
        self.assertNotIn('consent_scope', expected)
        self.assertNotIn('evidence_context', expected)


if __name__ == '__main__':
    unittest.main()
