"""Independent synthetic checks for offline adapter native JSON saving."""
import hashlib
import io
from tests._cli import run_cli
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from recaplib import title_adapter as adapter
from recaplib import title_document_output as output
from recaplib.session_workflow import import_export, titles
from tests.test_attributed_title import label, message, text_part
from tests.test_branch_title import fixture
from tests.test_replay_local import event, turn
from recaplib.title_proposal import apply_preview, preview

ROOT = Path(__file__).resolve().parents[1]


class AdapterNativeOutputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = self.root / 'synthetic.sqlite'
        self.source = 'SYNTHETIC_PRIVATE_SOURCE'
        self.config = adapter.AdapterConfig(kind='external', provider_id='SYNTHETIC_PRIVATE_PROVIDER',
            model='synthetic-model', endpoint='https://example.invalid/private-endpoint')
        self.path = self.root / 'synthetic-web.json'
        self.data = fixture()
        self.data[0]['mapping']['active']['message']['content']['parts'] = ['합성 과수원 계획 🌱']
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        import_export(self.db, self.source, self.path, 'web')
        self.response = dict(title='검토할 합성 제목 🌱', evidence_message_ids=['active'])

    def local(self, scope):
        self.path = self.root / (scope + '.jsonl')
        meta = dict(type='session_meta', payload=dict(id='synthetic'))
        if scope == 'local-replay':
            rows = [meta, *turn('a'), *turn('b'), event('thread_rolled_back', num_turns=1)]
            identity = 'au'
        else:
            rows = [meta, message([text_part('SYNTHETIC_HARNESS_PRIVATE'), text_part('합성 과수원 계획 🌱')],
                                 [label('harness'), label('user')], identity='u')]
            identity = 'u'
        self.path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
        import_export(self.db, self.source, self.path, 'local-codex')
        self.response['evidence_message_ids'] = [identity]

    def flags(self, scope='raw'):
        flags = ['--db', str(self.db), '--source', self.source, '--conversation', 'synthetic',
                 '--kind', 'external', '--provider-id', self.config.provider_id,
                 '--model', self.config.model, '--endpoint', self.config.endpoint]
        if scope != 'raw':
            flags += ['--evidence-scope', scope, '--input', str(self.path)]
        return flags

    def call(self, *arguments, code=None):
        result = run_cli(adapter.main, list(map(str, arguments)))
        self.assertNotIn('Traceback', result.stderr)
        if code is not None:
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(result.stderr, code + '\n')
            return result
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def in_process(self, arguments, code=None):
        result = run_cli(adapter.main, list(map(str, arguments)))
        self.assertEqual(result.returncode, 0 if code is None else 1, result.stderr)
        if code is not None:
            self.assertEqual(result.stdout, '')
            self.assertEqual(result.stderr, code + '\n')
            return
        self.assertEqual(result.stderr, '')
        result.stdout.encode('ascii')
        return json.loads(result.stdout)

    def save(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return path

    def inputs(self, scope='raw'):
        request = self.call(*self.flags(scope), 'prepare')
        return self.save('prepared.json', request), self.save('response.json', self.response)

    def assert_receipt(self, receipt, path, kind):
        raw = path.read_bytes()
        self.assertEqual(receipt['schema'], 'recap.saved-title-json.v1')
        self.assertEqual(receipt['status'], 'SAVED')
        self.assertEqual(receipt['document_kind'], kind)
        self.assertEqual(receipt['bytes'], len(raw))
        self.assertEqual(receipt['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt['encoding'], 'UTF-8')
        self.assertTrue(receipt['staging_cleanup_complete'])
        self.assertIsNone(receipt['remaining_staging_file'])
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        self.assertTrue(raw.endswith(b'\n'))
        self.assertFalse(raw.endswith(b'\n\n'))
        self.assertNotIn(b'\r\n', raw)
        rendered = json.dumps(receipt, ensure_ascii=False)
        rendered.encode('ascii')
        for private in (str(self.root), str(path), self.source, self.config.provider_id,
                        self.config.endpoint, self.response['title'], '합성 과수원 계획',
                        'SYNTHETIC_HARNESS_PRIVATE'):
            self.assertNotIn(private, rendered)
        for field in ('payload', 'source', 'conversation', 'evidence_context', 'title', 'consent_scope'):
            self.assertNotIn(field, receipt)
        self.assertEqual(list(self.root.glob('.recap-title-*')), [])

    def archive_evidence(self):
        with closing(sqlite3.connect(self.db)) as connection:
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                     if row[0] in ('messages', 'export_provenance', 'export_occurrences', 'exports')]
            return {name: connection.execute('SELECT * FROM ' + name).fetchall() for name in names}

    def test_all_four_scopes_save_same_documents_and_require_separate_apply(self):
        for scope in ('raw', 'web-branch', 'local-replay', 'local-attributed'):
            with self.subTest(scope=scope):
                self.db = self.root / (scope + '.sqlite')
                if scope.startswith('local-'):
                    self.local(scope)
                else:
                    import_export(self.db, self.source, self.path, 'web')
                before, original = self.db.read_bytes(), self.path.read_bytes()
                evidence = self.archive_evidence()
                expected_request = self.call(*self.flags(scope), 'prepare')
                request = self.root / (scope + '-요청 #%.json')
                receipt = self.call(*self.flags(scope), 'prepare', '--output', request)
                self.assert_receipt(receipt, request, 'request')
                saved_request = json.loads(request.read_bytes())
                self.assertEqual(saved_request, expected_request)
                response = self.save(scope + '-response.json', self.response)
                expected_proposal = self.call(*self.flags(scope), 'complete-response', request, response)
                proposal = self.root / (scope + '-제안 #%.json')
                receipt = self.call(*self.flags(scope), 'complete-response', request, response, '--output', proposal)
                self.assert_receipt(receipt, proposal, 'proposal')
                self.assertIn(self.response['title'].encode('utf-8'), proposal.read_bytes())
                saved_proposal = json.loads(proposal.read_bytes())
                self.assertEqual(saved_proposal, expected_proposal)
                self.assertEqual(saved_proposal['request_sha256'], saved_request['payload_sha256'])
                self.assertEqual(saved_proposal['provider_execution'], 'NOT_PERFORMED')
                self.assertEqual(saved_proposal['response_origin'], 'supplied_local_file')
                self.assertEqual(saved_proposal['semantic_validation'], 'NOT_PERFORMED')
                if scope != 'raw':
                    self.assertEqual(saved_proposal['evidence_context'], saved_request['evidence_context'])
                reviewed = preview(self.db, saved_proposal)
                self.assertEqual(titles(self.db, self.source, 'synthetic')['revision'], 0)
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(self.archive_evidence(), evidence)
                applied = apply_preview(self.db, reviewed)
                self.assertEqual(applied['display_title'], self.response['title'])
                self.assertEqual(titles(self.db, self.source, 'synthetic')['revision'], 1)
                self.assertEqual(self.archive_evidence(), evidence)
                self.assertEqual(self.path.read_bytes(), original)

    def test_existing_database_export_request_response_and_aliases_are_never_overwritten(self):
        request, response = self.inputs('web-branch')
        other = self.root / 'existing.json'; other.write_bytes(b'KEEP SYNTHETIC')
        paths = [self.db, self.path, request, response, other]
        originals = {path: path.read_bytes() for path in paths}
        targets = list(paths)
        for path in paths:
            for mode in ('hardlink', 'symlink'):
                alias = self.root / (path.name + '.' + mode)
                try:
                    os.link(path, alias) if mode == 'hardlink' else alias.symlink_to(path)
                except (OSError, NotImplementedError):
                    continue
                targets.append(alias)
        directory = self.root / 'directory'; directory.mkdir(); targets.append(directory)
        dangling = self.root / 'dangling'
        try:
            dangling.symlink_to(self.root / 'absent'); targets.append(dangling)
        except (OSError, NotImplementedError):
            pass
        for target in targets:
            for command in (['prepare'], ['complete-response', request, response]):
                with self.subTest(target=target.name, command=command[0]):
                    self.call(*self.flags('web-branch'), *command, '--output', target, code='OUTPUT_FAILED')
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(list(self.root.glob('.recap-title-*')), [])
        self.assertFalse((self.root / 'absent').exists())

    def test_local_and_mock_prepare_native_output_keep_default_stdout_shape(self):
        for kind in ('local', 'mock'):
            flags = ['--db', str(self.db), '--source', self.source, '--conversation', 'synthetic', '--kind', kind]
            target = self.root / (kind + '-request.json')
            expected = self.call(*flags, 'prepare')
            receipt = self.call(*flags, 'prepare', '--output', target)
            self.assert_receipt(receipt, target, 'request')
            self.assertEqual(json.loads(target.read_bytes()), expected)
            self.assertNotIn('consent_scope', expected)
            self.assertNotIn('evidence_context', expected)
            self.assertEqual(expected['warning'], 'PRIVATE USER TEXT: local preparation only; no transmission performed')

    def test_validation_errors_do_not_even_attempt_staging(self):
        request, response = self.inputs()
        target = self.root / 'not-created.json'
        malformed = self.save('bad.json', [])
        cases = [(['complete-response', malformed, response], 'REQUEST_INVALID'),
                 (['complete-response', request, malformed], 'INVALID_RESPONSE')]
        stale = json.loads(request.read_bytes())
        stale['payload_sha256'] = '0' * 64
        stale_path = self.save('stale.json', stale)
        cases.append((['complete-response', stale_path, response], 'PREPARED_REQUEST_STALE'))
        with patch.object(output.tempfile, 'NamedTemporaryFile', side_effect=AssertionError('must not stage')) as stage:
            for command, code in cases:
                self.in_process([*self.flags(), *command, '--output', target], code=code)
            stage.assert_not_called()
        self.assertFalse(target.exists())

    def test_missing_parent_fails_without_creating_directories(self):
        request, response = self.inputs()
        target = self.root / 'missing' / 'output.json'
        for command in (['prepare'], ['complete-response', request, response]):
            self.call(*self.flags(), *command, '--output', target, code='OUTPUT_FAILED')
        self.assertFalse(target.parent.exists())

    def test_source_validation_and_stale_prepared_request_never_stage(self):
        request, response = self.inputs('web-branch')
        target = self.root / 'not-created.json'
        self.path.write_bytes(self.path.read_bytes() + b'\n')
        for command in (['prepare'], ['complete-response', request, response]):
            self.call(*self.flags('web-branch'), *command, '--output', target, code='SOURCE_ERROR')
        import_export(self.db, self.source, self.path, 'web')
        self.call(*self.flags('web-branch'), 'complete-response', request, response,
                  '--output', target, code='PREPARED_REQUEST_STALE')
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob('.recap-title-*')), [])

    def test_invalid_inputs_fail_before_output_even_when_destination_exists(self):
        request, response = self.inputs()
        target = self.root / 'protected.json'; target.write_bytes(b'KEEP')
        for path, code in ((request, 'REQUEST_INVALID'), (response, 'INVALID_RESPONSE')):
            original = path.read_bytes()
            for invalid in (b'PRIVATE_MALFORMED', b'[]', b'{"a":1,"a":2}', b'{"x":NaN}'):
                path.write_bytes(invalid)
                self.call(*self.flags(), 'complete-response', request, response, '--output', target, code=code)
                self.assertEqual(target.read_bytes(), b'KEEP')
            path.write_bytes(original)
        self.assertEqual(list(self.root.glob('.recap-title-*')), [])

    def test_receipts_are_not_requests_proposals_or_external_consent(self):
        request, response = self.inputs()
        target = self.root / 'request-copy.json'
        receipt = self.call(*self.flags(), 'prepare', '--output', target)
        receipt_path = self.save('request-receipt.json', receipt)
        proposal_path = self.root / 'proposal.json'
        proposal_receipt = self.call(*self.flags(), 'complete-response', request, response, '--output', proposal_path)
        before = self.db.read_bytes()
        for value in (receipt, proposal_receipt):
            receipt_path.write_text(json.dumps(value), encoding='utf-8')
            missing = self.root / 'not-created.json'
            self.call(*self.flags(), 'complete-response', receipt_path, response,
                      '--output', missing, code='PREPARED_REQUEST_STALE')
            self.assertFalse(missing.exists())
            with self.assertRaises((ValueError, KeyError)):
                preview(self.db, value)
            with self.assertRaises((ValueError, KeyError)):
                apply_preview(self.db, value)
            self.call(*self.flags(), '--allow-external', 'generate', '--consent', receipt_path, code='CONSENT_REQUIRED')
        self.assertEqual(self.db.read_bytes(), before)

    def test_generate_rejects_output_before_source_access(self):
        destination = self.root / 'not-created.json'
        with patch.object(adapter, 'prepare_request', side_effect=AssertionError('must not prepare')):
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(sys, 'argv', ['title_adapter.py', *self.flags(), 'generate', '--output', str(destination)]), \
                 redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
                adapter.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertIn('unrecognized arguments: --output', stderr.getvalue())
        self.assertEqual(stdout.getvalue(), '')
        self.assertFalse(destination.exists())

    def test_native_save_never_calls_generation_subprocess_or_transport(self):
        response = self.save('response.json', self.response)
        request, proposal = self.root / 'request.json', self.root / 'proposal.json'
        with ExitStack() as stack:
            for name in ('recaplib.title_adapter.multiprocessing.get_context',
                         'subprocess.Popen', 'socket.socket', 'urllib.request.urlopen'):
                stack.enter_context(patch(name, side_effect=AssertionError('offline-only: ' + name)))
            with patch.object(adapter, 'generate', side_effect=AssertionError('no generation')):
                self.in_process([*self.flags(), 'prepare', '--output', request])
                self.in_process([*self.flags(), 'complete-response', request, response, '--output', proposal])
            self.in_process([*self.flags(), 'generate'], code='EXTERNAL_DISABLED')
            prepared = adapter.prepare_request(self.db, self.source, 'synthetic', self.config)
            consent = self.save('consent.json', dict(approved=True, **adapter.consent_scope(prepared, self.config)))
            self.in_process([*self.flags(), '--allow-external', 'generate', '--consent', consent],
                            code='EXTERNAL_NOT_CONFIGURED')
        self.assertEqual(json.loads(proposal.read_bytes())['provider_execution'], 'NOT_PERFORMED')

    def test_scoped_source_is_read_once_per_native_command(self):
        for scope in ('web-branch', 'local-replay', 'local-attributed'):
            with self.subTest(scope=scope):
                if scope.startswith('local-'):
                    self.local(scope)
                request, proposal = self.root / (scope + '-request.json'), self.root / (scope + '-proposal.json')
                response = self.save(scope + '-response.json', self.response)
                original_open = Path.open
                for command in (['prepare', '--output', request],
                                ['complete-response', request, response, '--output', proposal]):
                    reads = []
                    def checked_open(path, *args, **kwargs):
                        if path == self.path:
                            reads.append(path)
                        return original_open(path, *args, **kwargs)
                    with patch.object(Path, 'open', checked_open):
                        self.in_process([*self.flags(scope), *command])
                    self.assertEqual(reads, [self.path])

    def test_link_or_fsync_failure_uses_fixed_code_and_cleans_stage(self):
        request, response = self.inputs()
        before = self.db.read_bytes()
        target = self.root / 'not-created.json'
        for phase in ('fsync', 'link'):
            for command in (['prepare'], ['complete-response', request, response]):
                with self.subTest(phase=phase, command=command[0]), \
                     patch.object(output.os, phase, side_effect=OSError('PRIVATE_PATH_AND_PAYLOAD')):
                    self.in_process([*self.flags(), *command, '--output', target], code='OUTPUT_FAILED')
                self.assertFalse(target.exists())
                self.assertEqual(list(self.root.glob('.recap-title-*')), [])
        self.assertEqual(self.db.read_bytes(), before)

    def test_parent_symlink_loop_runtime_error_is_fixed_output_failure(self):
        request, response = self.inputs('web-branch')
        originals = {path: path.read_bytes() for path in (self.db, self.path, request, response)}
        target = self.root / 'not-created.json'
        commands = (['prepare'], ['complete-response', request, response])
        with patch.object(output, 'write_title_json', side_effect=RuntimeError('SYNTHETIC_PRIVATE_LOOP_PATH')) as writer:
            for command in commands:
                self.in_process([*self.flags('web-branch'), *command, '--output', target], code='OUTPUT_FAILED')
            self.assertEqual(writer.call_count, 2)
        self.assertFalse(target.exists())
        loop = self.root / 'looping-parent'
        try:
            loop.symlink_to(loop, target_is_directory=True)
        except (OSError, NotImplementedError):
            pass
        else:
            loop_target = loop / 'not-created.json'
            for command in commands:
                self.call(*self.flags('web-branch'), *command, '--output', loop_target, code='OUTPUT_FAILED')
            self.assertTrue(loop.is_symlink())
            self.assertFalse(os.path.lexists(loop_target))
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(list(self.root.glob('.recap-title-*')), [])

    def test_request_cleanup_failure_reports_saved_complete_target(self):
        target = self.root / 'request.json'
        original_unlink = Path.unlink
        def fail_stage(path, *args, **kwargs):
            if path.name.startswith('.recap-title-'):
                raise OSError('SYNTHETIC_PRIVATE_CLEANUP_FAILURE')
            return original_unlink(path, *args, **kwargs)
        expected = self.call(*self.flags(), 'prepare')
        with patch.object(Path, 'unlink', fail_stage):
            receipt = self.in_process([*self.flags(), 'prepare', '--output', target])
        self.assertEqual(receipt['status'], 'SAVED')
        self.assertEqual(receipt['document_kind'], 'request')
        self.assertFalse(receipt['staging_cleanup_complete'])
        stages = list(self.root.glob('.recap-title-*'))
        self.assertEqual(len(stages), 1)
        self.assertEqual(receipt['remaining_staging_file'], stages[0].name)
        self.assertEqual(stages[0].read_bytes(), target.read_bytes())
        self.assertEqual(json.loads(target.read_bytes()), expected)
        self.assertEqual(receipt['bytes'], len(target.read_bytes()))
        self.assertEqual(receipt['sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
        self.assertNotIn(str(self.root), json.dumps(receipt))
        self.assertNotIn('SYNTHETIC_PRIVATE_CLEANUP_FAILURE', json.dumps(receipt))
        self.assertEqual(titles(self.db, self.source, 'synthetic')['revision'], 0)

    def test_request_staging_is_closed_synced_same_directory_and_no_replace(self):
        factory, real_link, real_fsync = output.tempfile.NamedTemporaryFile, output.os.link, output.os.fsync
        streams, synced = [], []
        target = self.root / 'saved.json'
        def staged(*args, **kwargs):
            stream = factory(*args, **kwargs); streams.append(stream); return stream
        def sync(fd):
            synced.append(fd); return real_fsync(fd)
        def link(source, destination):
            self.assertTrue(streams[-1].closed)
            self.assertTrue(synced)
            self.assertTrue(Path(source).parent.samefile(target.parent))
            self.assertTrue(Path(destination).parent.samefile(target.parent))
            self.assertEqual(Path(destination).name, target.name)
            return real_link(source, destination)
        with patch.object(output.tempfile, 'NamedTemporaryFile', side_effect=staged), \
             patch.object(output.os, 'fsync', side_effect=sync), \
             patch.object(output.os, 'link', side_effect=link), \
             patch.object(output.os, 'replace', side_effect=AssertionError('no replace')), \
             patch.object(output.os, 'rename', side_effect=AssertionError('no rename')):
            receipt = self.in_process([*self.flags(), 'prepare', '--output', target])
        self.assert_receipt(receipt, target, 'request')
        self.assertIn('PRIVATE', receipt['warning'])
        self.assertIn('request', receipt['warning'].lower())
        self.assertIn('permission to send', receipt['warning'].lower())


if __name__ == '__main__':
    unittest.main()
