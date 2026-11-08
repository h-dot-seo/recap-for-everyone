import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from recap import ingest
from recaplib.session_workflow import import_export, titles
from recaplib.title_adapter import (AdapterConfig, AdapterError, MAX_REQUEST_BYTES, PreparedRequest,
                           check_external_consent, consent_scope, generate, normalized_endpoint,
                           prepare_request, response_proposal)
from recaplib.title_proposal import preview, apply_preview


def exit_worker_without_response(*args):
    os._exit(23)


class TitleAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        import_export(self.db, 'demo', 'examples/web-export.json', 'web')
        self.mock = AdapterConfig(kind='mock', provider_id='synthetic-mock', model='synthetic-v1')
        self.external = AdapterConfig(kind='external', provider_id='synthetic-provider',
                                      model='synthetic-model', endpoint='https://EXAMPLE.invalid:443/title', external_enabled=True)

    def prepared(self, config=AdapterConfig()):
        return prepare_request(self.db, 'demo', 'synthetic-chat', config)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(AdapterError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)

    def test_default_local_generation_is_readonly_and_requires_separate_apply(self):
        prepared = self.prepared()
        before = self.db.read_bytes()
        proposal = generate(prepared)
        self.assertEqual(proposal['provider'], 'local-extractive')
        self.assertEqual(proposal['semantic_validation'], 'NOT_PERFORMED')
        self.assertEqual(self.db.read_bytes(), before)
        reviewed = preview(self.db, proposal)
        self.assertEqual(titles(self.db, 'demo', 'synthetic-chat')['revision'], 0)
        self.assertEqual(apply_preview(self.db, reviewed)['display_title'], proposal['title'])

    def test_mock_response_is_whitelisted_and_bound_to_included_user_evidence(self):
        prepared = self.prepared(self.mock)
        raw = json.dumps(dict(title='Synthetic orchard design', evidence_message_ids=['m1'],
                              raw_private_body='SYNTHETIC_SECRET', provider='untrusted-provider'))
        proposal = generate(prepared, self.mock, mock_response=raw)
        self.assertEqual(proposal['provider'], 'synthetic-mock')
        self.assertNotIn('SYNTHETIC_SECRET', json.dumps(proposal))
        preview(self.db, proposal)
        for evidence in ([], ['m2'], ['missing'], ['m1', 'm1'], 'm1'):
            self.assert_code('INVALID_RESPONSE', response_proposal, prepared, self.mock,
                             dict(title='Synthetic title', evidence_message_ids=evidence))

    def test_request_is_bounded_user_only_and_deterministic(self):
        path = Path(self.tmp.name) / 'synthetic.jsonl'
        rows = [dict(conversation_id='c', message_id=str(i), role='user', timestamp='synthetic',
                     text='합성 사용자 요청 ' * 600) for i in range(25)]
        rows.append(dict(conversation_id='c', message_id='assistant', role='assistant',
                         timestamp='synthetic', text='SYNTHETIC_ASSISTANT_PRIVATE_MARKER'))
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        ingest(self.db, 'SYNTHETIC_SOURCE_PRIVATE_MARKER', path)
        prepared = prepare_request(self.db, 'SYNTHETIC_SOURCE_PRIVATE_MARKER', 'c', self.mock)
        self.assertLessEqual(len(prepared.payload), MAX_REQUEST_BYTES)
        self.assertNotIn(b'SYNTHETIC_ASSISTANT_PRIVATE_MARKER', prepared.payload)
        self.assertNotIn(b'SYNTHETIC_SOURCE_PRIVATE_MARKER', prepared.payload)
        self.assertEqual(prepared.payload, prepare_request(self.db, 'SYNTHETIC_SOURCE_PRIVATE_MARKER', 'c', self.mock).payload)
        body = json.loads(prepared.payload)
        self.assertTrue(all(row['role'] == 'user' for row in body['messages']))
        self.assertLessEqual(sum(len(row['text']) for row in body['messages']), 12000)
        self.assert_code('INVALID_RESPONSE', response_proposal, prepared, self.mock,
                         dict(title='Synthetic title', evidence_message_ids=['0']))

    def test_external_path_requires_both_setting_and_exact_consent_but_has_no_transport(self):
        prepared = self.prepared(self.external)
        consent = dict(approved=True, **consent_scope(prepared, self.external))
        with patch('recaplib.title_adapter.multiprocessing.get_context', side_effect=AssertionError('must not launch')):
            self.assert_code('EXTERNAL_DISABLED', generate, prepared, replace(self.external, external_enabled=False), consent=consent)
            self.assert_code('CONSENT_REQUIRED', generate, prepared, self.external)
            self.assert_code('EXTERNAL_NOT_CONFIGURED', generate, prepared, self.external, consent=consent)
        self.assertEqual(consent['endpoint'], 'https://example.invalid/title')

    def test_changed_provider_endpoint_model_or_payload_invalidates_consent(self):
        prepared = self.prepared(self.external)
        consent = dict(approved=True, **consent_scope(prepared, self.external))
        for config in (replace(self.external, provider_id='different-provider'),
                       replace(self.external, endpoint='https://example.invalid/other'),
                       replace(self.external, model='different-model')):
            request = self.prepared(config)
            self.assert_code('CONSENT_REQUIRED', check_external_consent, request, config, consent)
        body = json.loads(prepared.payload); body['messages'][0]['text'] += ' Synthetic update'
        changed = replace(prepared, payload=json.dumps(body).encode())
        self.assert_code('CONSENT_REQUIRED', check_external_consent, changed, self.external, consent)
        for approved in (False, None, 'yes', 1):
            self.assert_code('CONSENT_REQUIRED', check_external_consent, prepared, self.external,
                             dict(consent, approved=approved))

    def test_timeout_terminates_and_reaps_worker(self):
        config = replace(self.mock, timeout_seconds=0.2)
        prepared = self.prepared(config)
        before = {process.pid for process in multiprocessing.active_children()}
        started = time.monotonic()
        self.assert_code('TIMEOUT', generate, prepared, config,
                         mock_response='{}', mock_delay=5)
        self.assertLess(time.monotonic() - started, 4)
        self.assertEqual({process.pid for process in multiprocessing.active_children()}, before)

    def test_provider_exception_does_not_leak_child_output(self):
        code = """import sys
from recaplib.title_adapter import AdapterConfig, AdapterError, prepare_request, generate
if __name__ == '__main__':
    config = AdapterConfig(kind='mock', provider_id='synthetic-mock', model='synthetic-v1')
    prepared = prepare_request(sys.argv[1], 'demo', 'synthetic-chat', config)
    try:
        generate(prepared, config, mock_response='{}', mock_failure='SYNTHETIC_PRIVATE_ERROR_BODY')
    except AdapterError as error:
        print(error.code)
"""
        result = subprocess.run([sys.executable, '-c', code, str(self.db)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'PROVIDER_FAILED')
        self.assertEqual(result.stderr, '')
        self.assertNotIn('SYNTHETIC_PRIVATE_ERROR_BODY', result.stdout + result.stderr)

    def test_invalid_config_and_oversized_inputs_fail_closed(self):
        for timeout in (0, -1, True, float('nan'), float('inf'), 121, 10 ** 1000):
            self.assert_code('CONFIG_INVALID', self.prepared, replace(self.mock, timeout_seconds=timeout))
        for endpoint in ('http://example.invalid', 'https://user:password' + '@' + 'example.invalid',
                         'https://example.invalid/?key=synthetic', 'https://example.invalid/#fragment', 'https://bad host/title', 'https://example.invalid:0/', 'https://example.invalid:65536/'):
            self.assert_code('CONFIG_INVALID', normalized_endpoint, endpoint)
        prepared = self.prepared(self.mock)
        self.assert_code('REQUEST_INVALID', generate, replace(prepared, payload=b'x' * (MAX_REQUEST_BYTES + 1)), self.mock)
        self.assert_code('INVALID_RESPONSE', generate, prepared, self.mock, mock_response='x' * 20000)

    def test_generated_proposal_keeps_existing_content_and_revision_guards(self):
        proposal = generate(self.prepared(self.mock), self.mock,
                            mock_response=json.dumps(dict(title='Synthetic title', evidence_message_ids=['m1'])))
        reviewed = preview(self.db, proposal)
        titles(self.db, 'demo', 'synthetic-chat', 'Newer reviewed title', 0)
        with self.assertRaises(ValueError):
            apply_preview(self.db, reviewed)

    def test_new_content_invalidates_a_generated_proposal(self):
        proposal = generate(self.prepared(self.mock), self.mock,
                            mock_response=json.dumps(dict(title='Synthetic title', evidence_message_ids=['m1'])))
        path = Path(self.tmp.name) / 'new-message.jsonl'
        path.write_text(json.dumps(dict(conversation_id='synthetic-chat', message_id='m3', role='user',
                                        timestamp='synthetic', title='New chat', text='Additional synthetic detail')) + '\n')
        ingest(self.db, 'demo', path)
        with self.assertRaises(ValueError):
            preview(self.db, proposal)

    def test_malformed_mock_response_fails_without_echoing_content(self):
        self.assert_code('INVALID_RESPONSE', generate, self.prepared(self.mock), self.mock,
                         mock_response='SYNTHETIC_PRIVATE_MALFORMED_RESPONSE')

    def test_malformed_unicode_duplicate_keys_and_expanded_envelope_are_rejected(self):
        prepared = self.prepared(self.mock)
        for raw in ('\ud800', '{"title":"one","title":"two","evidence_message_ids":["m1"]}',
                    json.dumps(dict(title='\ud800', evidence_message_ids=['m1'])),
                    json.dumps(dict(title='Synthetic', evidence_message_ids=['m1'], ignored='한' * 3000), ensure_ascii=False)):
            self.assert_code('INVALID_RESPONSE', generate, prepared, self.mock, mock_response=raw)

    def test_worker_exit_without_response_is_sanitized_and_reaped(self):
        before = {process.pid for process in multiprocessing.active_children()}
        with patch('recaplib.title_adapter._worker', exit_worker_without_response):
            self.assert_code('PROVIDER_FAILED', generate, self.prepared(self.mock), self.mock, mock_response='{}')
        self.assertEqual({process.pid for process in multiprocessing.active_children()}, before)

    def test_cli_local_generation_and_safe_source_error(self):
        result = subprocess.run([sys.executable, 'title_adapter.py', '--db', str(self.db), '--source', 'demo',
                                 '--conversation', 'synthetic-chat', 'generate'], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['provider'], 'local-extractive')
        missing = Path(self.tmp.name) / 'SYNTHETIC_PRIVATE_PATH.sqlite'
        result = subprocess.run([sys.executable, 'title_adapter.py', '--db', str(missing), '--source', 'demo',
                                 '--conversation', 'synthetic-chat', 'generate'], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stderr.strip(), 'SOURCE_ERROR')
        self.assertFalse(missing.exists())

    def test_cli_unicode_proposals_work_with_ascii_stdout(self):
        response = Path(self.tmp.name) / 'synthetic-response.json'
        response.write_text(json.dumps(dict(title='합성 과수원 계획', evidence_message_ids=['m1'])), encoding='utf-8')
        result = subprocess.run([sys.executable, 'title_adapter.py', '--db', str(self.db), '--source', 'demo',
                                 '--conversation', 'synthetic-chat', '--kind', 'mock', '--provider-id', 'synthetic-mock',
                                 '--model', 'synthetic-v1', 'generate', '--response', str(response)],
                                capture_output=True, text=True, timeout=20,
                                env=dict(os.environ, PYTHONIOENCODING='ascii'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['title'], '합성 과수원 계획')
