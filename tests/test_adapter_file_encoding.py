"""Editor-saved adapter input files, synthetic data only and no external provider."""
from codecs import BOM_UTF8
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recaplib import title_adapter as adapter
from recaplib.conversation_search import find
from recaplib.session_workflow import import_export, titles
from recaplib.strict_json import loads
from recaplib.title_proposal import apply_preview, preview, read_document

ROOT = Path(__file__).resolve().parents[1]


class AdapterFileEncodingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root/'archive.sqlite'
        self.source = ROOT/'examples/web-export.json'
        self.conversation = 'synthetic-chat'; self.scope = 'web-branch'
        self.config = adapter.AdapterConfig(kind='external', provider_id='synthetic-provider',
            model='synthetic-model', endpoint='https://example.invalid/title')
        self.response = dict(title='합성 과수원 🌱 검토', evidence_message_ids=['m1'])
        import_export(self.db, 'demo', self.source, 'web')

    def options(self):
        return dict(evidence_scope=self.scope, input_path=self.source,
                    node='m2' if self.scope == 'web-branch' else None)

    def prepare(self, config=None):
        config = config or self.config
        return adapter.prepare_request(self.db, 'demo', self.conversation, config, **self.options())

    def save(self, name, value, prefix=BOM_UTF8):
        path = self.root/name
        path.write_bytes(prefix+json.dumps(value, ensure_ascii=False).encode('utf-8')+b'\r\n')
        return path

    def flags(self, config=None):
        config = config or self.config
        args = ['--db', str(self.db), '--source', 'demo', '--conversation', self.conversation,
                '--kind', config.kind, '--provider-id', config.provider_id, '--model', config.model,
                '--evidence-scope', self.scope, '--input', str(self.source)]
        if self.scope == 'web-branch': args += ['--node', 'm2']
        if config.endpoint: args += ['--endpoint', config.endpoint]
        if config.external_enabled: args += ['--allow-external']
        return args

    def cli(self, *args, config=None, error=None):
        result = subprocess.run([sys.executable, str(ROOT/'title_adapter.py'), *self.flags(config), *map(str,args)],
            capture_output=True, text=True, encoding='ascii', timeout=30,
            env=dict(os.environ, PYTHONIOENCODING='ascii'))
        if error:
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(result.stderr, error+'\n')
            return result
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(adapter.AdapterError) as caught: function(*args, **kwargs)
        self.assertEqual(str(caught.exception), code)

    def completion_files(self):
        document = adapter.request_document(self.prepare(), self.config)
        return self.save('prepared.json', document), self.save('response.json', self.response)

    def test_all_scopes_editor_saved_completion_remains_readonly_until_explicit_apply(self):
        cases = [
            ('raw', 'web-export.json', 'web', 'synthetic-chat', 'm1'),
            ('web-branch', 'web-export.json', 'web', 'synthetic-chat', 'm1'),
            ('local-replay', 'rollback-session.jsonl', 'local-codex', 'synthetic-rollout', 'u1'),
            ('local-attributed', 'source-attributed-session.jsonl', 'local-codex', 'synthetic-attributed', 'synthetic-u1')]
        for index, (scope, filename, kind, identity, message) in enumerate(cases):
            with self.subTest(scope=scope):
                self.db = self.root/f'archive-{index}.sqlite'
                self.scope, self.conversation, self.source = scope, identity, ROOT/'examples'/filename
                import_export(self.db, 'demo', self.source, kind)
                options = {} if scope == 'raw' else self.options()
                prepared = adapter.prepare_request(self.db, 'demo', identity, self.config, **options)
                document = adapter.request_document(prepared, self.config)
                message = document['payload']['messages'][0]['message_id']
                response = dict(title=f'합성 과수원 {index} 🌱', evidence_message_ids=[message])
                request_file = self.save(f'request-{index}.json', document)
                response_file = self.save(f'response-{index}.json', response)
                before = self.db.read_bytes(); source_bytes = self.source.read_bytes()
                original = (request_file.read_bytes(), response_file.read_bytes())
                with (patch('recaplib.title_adapter.generate', side_effect=AssertionError('no provider')),
                      patch('recaplib.title_adapter.multiprocessing.get_context', side_effect=AssertionError('no worker')),
                      patch('socket.socket', side_effect=AssertionError('no transport'))):
                    decoded = adapter._read_object(request_file, adapter.MAX_PREPARED_DOCUMENT_BYTES, 'REQUEST_INVALID')
                    decoded_response = adapter._read_object(response_file, adapter.MAX_RESPONSE_BYTES, 'INVALID_RESPONSE')
                    proposal = adapter.complete_response(self.db, 'demo', identity, decoded,
                        decoded_response, self.config, **options)
                    plain = adapter.complete_response(self.db, 'demo', identity, document, response, self.config, **options)
                self.assertEqual(proposal, plain)
                self.assertEqual(proposal['request_sha256'], prepared.payload_sha256)
                reviewed = preview(self.db, proposal, with_evidence=True)
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(titles(self.db, 'demo', identity)['revision'], 0)
                self.assertEqual(apply_preview(self.db, reviewed)['display_title'], response['title'])
                self.assertEqual(find(self.db, response['title'], source='demo')['total_matches'], 1)
                self.assertEqual(self.source.read_bytes(), source_bytes)
                self.assertEqual((request_file.read_bytes(), response_file.read_bytes()), original)

    def test_cli_native_output_and_editor_bom_roundtrip(self):
        request = self.root/'native-request.json'
        receipt = self.cli('prepare', '--output', request)
        raw = request.read_bytes(); self.assertFalse(raw.startswith(BOM_UTF8))
        self.assertEqual(receipt['sha256'], hashlib.sha256(raw).hexdigest())
        request.write_bytes(BOM_UTF8+raw)
        response = self.save('response.json', self.response)
        before = self.db.read_bytes(); output = self.root/'proposal.json'
        receipt = self.cli('complete-response', request, response, '--output', output)
        result = output.read_bytes(); self.assertFalse(result.startswith(BOM_UTF8))
        self.assertEqual(receipt['document_kind'], 'proposal')
        self.assertEqual(receipt['sha256'], hashlib.sha256(result).hexdigest())
        proposal = read_document(output)
        self.assertEqual(proposal['title'], self.response['title'])
        self.assertEqual(proposal['provider_execution'], 'NOT_PERFORMED')
        self.assertEqual(self.db.read_bytes(), before)

    def test_exact_original_byte_budget_includes_signature(self):
        value = {'title': 'Synthetic'}
        plain = json.dumps(value).encode()
        for code in ('REQUEST_INVALID', 'INVALID_RESPONSE', 'CONSENT_REQUIRED'):
            for prefix in (b'', BOM_UTF8):
                raw = prefix+plain+b' \r\n'
                path = self.root/'bounded.json'; path.write_bytes(raw)
                with self.subTest(code=code, prefix=prefix):
                    self.assertEqual(adapter._read_object(path, len(raw), code), value)
                    self.assert_code(code, adapter._read_object, path, len(raw)-1, code)
                    self.assertEqual(path.read_bytes(), raw)
        path.write_bytes(BOM_UTF8+plain)
        self.assert_code('INVALID_RESPONSE', adapter._read_object, path, len(plain), 'INVALID_RESPONSE')

    def test_bounded_reader_reads_once_and_no_more_than_limit_plus_one(self):
        raw = BOM_UTF8+b'{"title":"Synthetic"}'
        class Stream(io.BytesIO):
            def __init__(self, data): super().__init__(data); self.sizes = []
            def read(self, size=-1): self.sizes.append(size); return super().read(size)
        stream = Stream(raw)
        with patch.object(Path, 'open', return_value=stream) as opened:
            self.assertEqual(adapter._read_object(self.root/'never-opened.json', len(raw), 'REQUEST_INVALID'),
                             {'title':'Synthetic'})
        self.assertEqual(opened.call_count, 1); self.assertEqual(stream.sizes, [len(raw)+1])
        self.assertTrue(stream.closed)

    def test_signature_is_only_framing_and_embedded_feff_stays_data(self):
        value = {'\ufeffkey': ['A\ufeffB', '\ufeff', 'e\u0301', '한글 🌱']}
        for prefix in (b'', BOM_UTF8):
            path = self.save('value.json', value, prefix)
            before = path.read_bytes()
            self.assertEqual(adapter._read_object(path, 1000, 'INVALID_RESPONSE'), value)
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_encodings_and_json_remain_fixed_errors(self):
        valid = b'{"title":"SYNTHETIC_PRIVATE"}'
        invalid = [BOM_UTF8+BOM_UTF8+valid, b' '+BOM_UTF8+valid,
                   valid+BOM_UTF8, b'{'+BOM_UTF8+b'"x":1}', b'\xef', b'\xef\xbb',
                   b'\xff'+valid, valid.decode().encode('utf-16'), valid.decode().encode('utf-32'),
                   BOM_UTF8+b'{"x":"\xff"}', BOM_UTF8+b'{"a":1,"a":2}',
                   BOM_UTF8+b'{"x":"\\ud800"}', BOM_UTF8+b'{"x":NaN}',
                   BOM_UTF8+b'{"x":1e999}', BOM_UTF8+b'[]',
                   BOM_UTF8+b'{"x":'+b'['*10000+b'0'+b']'*10000+b'}']
        path = self.root/'invalid.json'
        for code in ('REQUEST_INVALID', 'INVALID_RESPONSE', 'CONSENT_REQUIRED'):
            for index, raw in enumerate(invalid):
                with self.subTest(code=code, case=index):
                    path.write_bytes(raw)
                    self.assert_code(code, adapter._read_object, path, len(raw)+10, code)
                    self.assertEqual(path.read_bytes(), raw)

    def test_invalid_input_precedes_archive_access_and_output_creation(self):
        request, response = self.completion_files()
        for target, code in ((request, 'REQUEST_INVALID'), (response, 'INVALID_RESPONSE')):
            original = target.read_bytes(); target.write_bytes(BOM_UTF8+BOM_UTF8+original)
            output = self.root/'not-created.json'; before = self.db.read_bytes()
            with patch('recaplib.title_adapter.prepare_request', side_effect=AssertionError('no archive read')):
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch('sys.argv', ['title_adapter.py', *self.flags(), 'complete-response',
                                        str(request), str(response), '--output', str(output)]), redirect_stdout(stdout), redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as caught: adapter.main()
            self.assertEqual(caught.exception.code, 1)
            self.assertEqual(stdout.getvalue(), ''); self.assertEqual(stderr.getvalue(), code+'\n')
            self.assertFalse(output.exists()); self.assertEqual(self.db.read_bytes(), before)
            target.write_bytes(original)

    def test_bom_does_not_hide_stale_preparation_or_forged_evidence(self):
        request, response = self.completion_files(); before = self.db.read_bytes()
        document = read_document(request); document['payload']['messages'][0]['text'] += ' altered'
        self.save(request.name, document)
        self.cli('complete-response', request, response, error='PREPARED_REQUEST_STALE')
        request, response = self.completion_files()
        self.save(response.name, dict(self.response, evidence_message_ids=['missing']))
        self.cli('complete-response', request, response, error='INVALID_RESPONSE')
        self.assertEqual(self.db.read_bytes(), before)

    def test_original_export_bom_still_requires_exact_imported_provenance(self):
        request, response = self.completion_files()
        copied = self.root/'web-source.json'; copied.write_bytes(BOM_UTF8+self.source.read_bytes())
        self.source = copied
        self.cli('complete-response', request, response, error='SOURCE_ERROR')
        # Reimport identical text adds the new bytes' provenance, not new messages.
        self.assertEqual(import_export(self.db, 'demo', copied, 'web')['inserted'], 0)
        self.cli('complete-response', request, response, error='PREPARED_REQUEST_STALE')

    def test_mock_file_accepts_one_signature_but_direct_string_contract_does_not(self):
        config = adapter.AdapterConfig(kind='mock', provider_id='synthetic-mock', model='synthetic-model')
        path = self.save('mock.json', self.response)
        before = self.db.read_bytes()
        result = self.cli('generate', '--response', path, config=config)
        self.assertEqual(result['title'], self.response['title']); self.assertEqual(result['provider'], 'synthetic-mock')
        self.assert_code('INVALID_RESPONSE', adapter.generate, self.prepare(config), config,
                         mock_response='\ufeff'+json.dumps(self.response))
        path.write_bytes(BOM_UTF8+path.read_bytes())
        self.cli('generate', '--response', path, config=config, error='INVALID_RESPONSE')
        self.assertEqual(self.db.read_bytes(), before)

    def test_consent_file_signature_does_not_enable_external_execution(self):
        config = replace(self.config, external_enabled=True)
        consent = dict(approved=True, **adapter.consent_scope(self.prepare(config), config))
        path = self.save('consent.json', consent); before = self.db.read_bytes()
        for cfg, code in ((config, 'EXTERNAL_NOT_CONFIGURED'), (self.config, 'EXTERNAL_DISABLED')):
            self.cli('generate', '--consent', path, config=cfg, error=code)
        for change in ({'approved':False}, {'model':'different'}, {'payload_sha256':'0'*64}):
            self.save(path.name, dict(consent, **change))
            self.cli('generate', '--consent', path, config=config, error='CONSENT_REQUIRED')
        self.save(path.name, consent); path.write_bytes(BOM_UTF8+path.read_bytes())
        self.cli('generate', '--consent', path, config=config, error='CONSENT_REQUIRED')
        self.assertEqual(self.db.read_bytes(), before)

    def test_cli_response_and_consent_limits_count_original_signature_bytes(self):
        request, response = self.completion_files()
        raw = response.read_bytes()
        response.write_bytes(raw+b' '*(adapter.MAX_RESPONSE_BYTES-len(raw)))
        self.cli('complete-response', request, response)
        response.write_bytes(response.read_bytes()+b' ')
        self.cli('complete-response', request, response, error='INVALID_RESPONSE')
        config = replace(self.config, external_enabled=True)
        consent = dict(approved=True, **adapter.consent_scope(self.prepare(config), config))
        path = self.save('bounded-consent.json', consent)
        raw = path.read_bytes(); path.write_bytes(raw+b' '*(8192-len(raw)))
        self.cli('generate', '--consent', path, config=config, error='EXTERNAL_NOT_CONFIGURED')
        path.write_bytes(path.read_bytes()+b' ')
        self.cli('generate', '--consent', path, config=config, error='CONSENT_REQUIRED')

    def test_canonical_object_budget_still_applies_after_decoding(self):
        # Exponent-form JSON numbers can expand when the object is serialized.
        raw = BOM_UTF8+b'{"x":[1e5,1e5]}'
        path = self.root/'canonical-limit.json'; path.write_bytes(raw)
        value = loads(adapter._read_bounded(path, len(raw), 'INVALID_RESPONSE'))
        self.assertEqual(value, {'x':[100000.0,100000.0]})
        self.assert_code('INVALID_RESPONSE', adapter._read_object, path, len(raw), 'INVALID_RESPONSE')

    def test_payload_bytes_and_shared_parser_do_not_gain_bom_tolerance(self):
        prepared = self.prepare()
        self.assert_code('REQUEST_INVALID', adapter.request_document,
                         replace(prepared, payload=BOM_UTF8+prepared.payload), self.config)
        with self.assertRaises(ValueError): loads('\ufeff{"title":"Synthetic"}')


if __name__ == '__main__':
    unittest.main()
