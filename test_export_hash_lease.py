"""Whole-file hash leases bind discovery to one immutable synthetic export snapshot."""
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from conversation_view import conversation, conversations
from export_inventory import list_export
from session_workflow import import_export, inspect_export, normalize


class ExportHashLeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic-export.json'
        self.db = Path(self.tmp.name) / 'archive.sqlite'

    def write(self, kind='web'):
        if kind == 'web':
            records = [dict(id=identity, title='Synthetic ' + identity, mapping={
                'm': dict(parent=None, message=dict(author=dict(role='user'),
                    content=dict(parts=['Synthetic body ' + identity])))})
                for identity in ('alpha', 'beta')]
            raw = json.dumps(records).encode('utf-8')
        else:
            records = []
            for identity in ('alpha', 'beta'):
                records.extend([dict(type='session_meta', payload=dict(id=identity)),
                    dict(type='response_item', payload=dict(type='message', role='user',
                        content=[dict(type='input_text', text='Synthetic body ' + identity)]))])
            raw = ('\r\n'.join(json.dumps(row) for row in records) + '\r\n').encode('utf-8')
        self.path.write_bytes(raw)
        return raw, hashlib.sha256(raw).hexdigest()

    def calls(self, kind, token):
        return [lambda: normalize(self.path, kind, expected_export_sha256=token),
                lambda: inspect_export(self.path, kind, expected_export_sha256=token),
                lambda: list_export(self.path, kind, expected_export_sha256=token),
                lambda: import_export(self.db, 'synthetic', self.path, kind,
                                      expected_export_sha256=token)]

    def assert_mismatch(self, call):
        with self.assertRaises(ValueError) as caught:
            call()
        self.assertEqual(str(caught.exception),
                         'export changed after inspection; inspect and select again')

    def cli(self, script, args, ok=True):
        result = subprocess.run([sys.executable, str(Path(__file__).parent / script),
                                 *map(str, args)], capture_output=True, text=True,
                                encoding='utf-8', cwd=self.tmp.name, timeout=20)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return json.loads(result.stdout) if ok else result

    def test_documented_copyable_inspection_matches_shipped_example(self):
        root = Path(__file__).parent
        lines = (root / 'docs' / 'INPUT_SCOPE.md').read_text(encoding='utf-8').splitlines()
        commands = [shlex.split(line) for line in lines
                    if line.startswith('python recap.py inspect examples/web-export.json ')
                    and '--expected-export-sha256' in line]
        self.assertEqual(len(commands), 1)
        command, = commands
        digest = command[command.index('--expected-export-sha256') + 1]
        self.assertEqual(digest, hashlib.sha256((root / 'examples' / 'web-export.json').read_bytes()).hexdigest())
        result = subprocess.run([sys.executable, *command[1:]], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['expected_export_sha256'], digest)
        self.assertEqual(report['original_sha256'], digest)
        self.assertEqual(report['selection']['conversation'], 'synthetic-chat')

    def test_matching_hash_all_formats_receipts_and_original_hash(self):
        for kind in ('web', 'local', 'local-codex'):
            with self.subTest(kind=kind):
                raw, digest = self.write(kind)
                rows, report = normalize(self.path, kind, True, 'alpha', digest)
                self.assertEqual(len(rows), 1)
                for receipt in (report, inspect_export(self.path, kind, 'alpha', digest),
                                list_export(self.path, kind, 50, 0, digest)['coverage']):
                    self.assertEqual(receipt['expected_export_sha256'], digest)
                    self.assertEqual(receipt['original_sha256'], digest)
                    self.assertEqual(receipt['original_bytes'], len(raw))
                self.assertEqual(self.path.read_bytes(), raw)
                self.assertFalse(self.db.exists())

    def test_no_hash_and_explicit_none_preserve_shapes(self):
        for kind in ('web', 'local', 'local-codex'):
            self.write(kind)
            self.assertEqual(normalize(self.path, kind), normalize(self.path, kind, expected_export_sha256=None))
            self.assertIsInstance(normalize(self.path, kind), list)
            self.assertIsInstance(normalize(self.path, kind, True), tuple)
            self.assertEqual(inspect_export(self.path, kind), inspect_export(self.path, kind, expected_export_sha256=None))
            self.assertEqual(list_export(self.path, kind), list_export(self.path, kind, expected_export_sha256=None))
            self.assertNotIn('expected_export_sha256', inspect_export(self.path, kind))
            self.assertNotIn('expected_export_sha256', list_export(self.path, kind)['coverage'])

    def test_invalid_tokens_fail_before_read_or_parse_or_ingest(self):
        invalid = ['', 'a' * 63, 'a' * 65, 'A' * 64, 'g' * 64,
                   ' ' + 'a' * 64, 'a' * 64 + '\n', 1, True, [], {}, b'a' * 64]
        for token in invalid:
            for call in self.calls('web', token):
                with self.subTest(token=repr(token)), \
                     patch.object(Path, 'read_bytes', side_effect=AssertionError('read before validation')), \
                     patch('session_workflow._normalize_bytes', side_effect=AssertionError('parsed')), \
                     patch('session_workflow.ingest_bytes', side_effect=AssertionError('database touched')):
                    with self.assertRaises(ValueError):
                        call()
                self.assertFalse(self.db.exists())

    def test_stale_malformed_bytes_fail_hash_before_parser_or_database(self):
        for kind in ('web', 'local', 'local-codex'):
            _, digest = self.write(kind)
            malformed = b'\xffSYNTHETIC_PRIVATE_MALFORMED_BYTES'
            self.path.write_bytes(malformed)
            for call in self.calls(kind, digest):
                with patch('session_workflow._normalize_bytes', side_effect=AssertionError('parsed')), \
                     patch('export_inventory._normalize_bytes', side_effect=AssertionError('parsed')), \
                     patch('session_workflow.ingest_bytes', side_effect=AssertionError('database touched')):
                    self.assert_mismatch(call)
                self.assertFalse(self.db.exists())
                self.assertEqual(self.path.read_bytes(), malformed)

    def test_selected_and_unselected_content_changes_invalidate_whole_file(self):
        for kind in ('web', 'local', 'local-codex'):
            for changed in ('alpha', 'beta'):
                with self.subTest(kind=kind, changed=changed):
                    raw, digest = self.write(kind)
                    self.path.write_bytes(raw.replace(('Synthetic body ' + changed).encode(), b'Changed synthetic body'))
                    self.assert_mismatch(lambda: inspect_export(self.path, kind, 'alpha', digest))
                    self.assert_mismatch(lambda: import_export(self.db, 'synthetic', self.path, kind, 'alpha', digest))
                    self.assertFalse(self.db.exists())

    def test_whitespace_only_change_invalidates_hash(self):
        raw, digest = self.write()
        self.path.write_bytes(raw + b'\n')
        for call in self.calls('web', digest):
            self.assert_mismatch(call)
        self.assertEqual(normalize(self.path, 'web'), normalize(self.path, 'web', expected_export_sha256=hashlib.sha256(raw + b'\n').hexdigest()))

    def test_changed_input_does_not_modify_existing_database(self):
        raw, digest = self.write()
        import_export(self.db, 'synthetic', self.path, 'web')
        before = self.db.read_bytes()
        changed = raw + b'\n'
        self.path.write_bytes(changed)
        self.assert_mismatch(lambda: import_export(self.db, 'synthetic', self.path, 'web', 'alpha', digest))
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), changed)

    def test_selected_bound_import_retains_whole_file_provenance(self):
        for kind in ('web', 'local', 'local-codex'):
            with self.subTest(kind=kind):
                raw, digest = self.write(kind)
                db = self.db.with_name(kind + '.sqlite')
                receipt = import_export(db, 'synthetic', self.path, kind, 'alpha', digest)
                self.assertEqual(receipt['inserted'], 1)
                self.assertEqual(receipt['coverage']['expected_export_sha256'], digest)
                self.assertEqual(receipt['coverage']['original_sha256'], digest)
                self.assertEqual(receipt['coverage']['selection']['excluded_messages'], 1)
                self.assertEqual(len(conversations(db)['conversations']), 1)
                archive = conversation(db, 'synthetic', 'alpha')
                self.assertNotIn('Synthetic body beta', json.dumps(archive))
                for message in archive['messages']:
                    self.assertEqual(message['export_provenance'][0]['original_sha256'], digest)
                self.assertEqual(self.path.read_bytes(), raw)

    def test_renamed_unchanged_source_hash_remains_valid(self):
        for kind in ('web', 'local', 'local-codex'):
            raw, digest = self.write(kind)
            renamed = self.path.with_name('renamed-export.json')
            renamed.write_bytes(raw)
            self.assertEqual(inspect_export(renamed, kind, expected_export_sha256=digest)['original_sha256'], digest)
            self.assertEqual(list_export(renamed, kind, expected_export_sha256=digest)['original_sha256'], digest)

    def test_pagination_continuation_is_bound_to_original_bytes(self):
        raw, digest = self.write()
        first = list_export(self.path, 'web', limit=1)
        self.assertEqual(first['original_sha256'], digest)
        second = list_export(self.path, 'web', 1, first['next_offset'], digest)
        self.assertEqual(second['conversations'][0]['conversation'], 'beta')
        self.path.write_bytes(raw + b' ')
        self.assert_mismatch(lambda: list_export(self.path, 'web', 1, first['next_offset'], digest))

    def test_single_source_read_snapshot_coherence_for_normalize_inventory_import(self):
        reader = Path.read_bytes
        for kind in ('web', 'local', 'local-codex'):
            for operation in ('normalize', 'inventory', 'import'):
                with self.subTest(kind=kind, operation=operation):
                    raw, digest = self.write(kind)
                    reads = []
                    def mutate_after_read(path):
                        data = reader(path)
                        if path == self.path:
                            reads.append(path)
                            path.write_bytes(b'changed invalid synthetic bytes')
                        return data
                    with patch.object(Path, 'read_bytes', mutate_after_read):
                        if operation == 'normalize':
                            rows, report = normalize(self.path, kind, True, 'alpha', digest)
                            self.assertEqual(len(rows), 1)
                        elif operation == 'inventory':
                            result = list_export(self.path, kind, expected_export_sha256=digest)
                            self.assertEqual(result['total_conversations'], 2)
                            report = result['coverage']
                        else:
                            db = self.db.with_name('snapshot-' + kind + '.sqlite')
                            result = import_export(db, 'synthetic', self.path, kind, 'alpha', digest)
                            self.assertEqual(result['inserted'], 1)
                            report = result['coverage']
                    self.assertEqual(len(reads), 1)
                    self.assertEqual(report['original_sha256'], digest)
                    self.assertEqual(report['expected_export_sha256'], digest)
                    self.assertEqual(report['original_bytes'], len(raw))

    def test_matching_hash_does_not_bypass_semantic_validation(self):
        self.path.write_bytes(b'{"synthetic": "not a web export array"}')
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        for call in self.calls('web', digest):
            with self.assertRaises(ValueError) as caught:
                call()
            self.assertNotIn('export changed after inspection', str(caught.exception))
        self.assertFalse(self.db.exists())

    def test_cli_matching_inspection_inventory_and_selected_import_parity(self):
        for kind in ('web', 'local', 'local-codex'):
            raw, digest = self.write(kind)
            common = [self.path, '--format', kind, '--expected-export-sha256', digest]
            api = inspect_export(self.path, kind, 'alpha', digest)
            for script in ('recap.py', 'session_workflow.py'):
                self.assertEqual(self.cli(script, ['inspect', *common, '--conversation', 'alpha']), api)
                db = self.db.with_name(script + '-' + kind + '.sqlite')
                receipt = self.cli(script, ['--db', db, 'import', *common, '--source', 'synthetic', '--conversation', 'alpha'])
                self.assertEqual(receipt['coverage']['expected_export_sha256'], digest)
                self.assertEqual(receipt['inserted'], 1)
            inventory = list_export(self.path, kind, 1, 1, digest)
            self.assertEqual(self.cli('recap.py', ['list-export', *common, '--limit', 1, '--offset', 1]), inventory)
            self.assertEqual(self.cli('export_inventory.py', [*common, '--limit', 1, '--offset', 1]), inventory)
            self.assertEqual(self.path.read_bytes(), raw)

    def test_all_cli_entrypoints_reject_stale_hash_without_leaking_or_creating_db(self):
        _, digest = self.write()
        self.path.write_bytes(b'\xffPRIVATE_SYNTHETIC_INPUT')
        common = [self.path, '--format', 'web', '--expected-export-sha256', digest]
        entries = [('recap.py', ['inspect', *common]),
                   ('session_workflow.py', ['inspect', *common]),
                   ('recap.py', ['list-export', *common]),
                   ('export_inventory.py', common)]
        entries.extend((script, ['--db', self.db, 'import', *common, '--source', 'synthetic'])
                       for script in ('recap.py', 'session_workflow.py'))
        for script, args in entries:
            result = self.cli(script, args, ok=False)
            self.assertEqual(result.stderr.strip(), 'export changed after inspection; inspect and select again')
            self.assertEqual(result.stdout, '')
            self.assertFalse(self.db.exists())

    def test_all_cli_entrypoints_validate_token_before_missing_file(self):
        missing = self.path.with_name('missing-synthetic-export.json')
        common = [missing, '--format', 'web', '--expected-export-sha256', 'Z' * 64]
        entries = [('recap.py', ['inspect', *common]), ('session_workflow.py', ['inspect', *common]),
                   ('recap.py', ['list-export', *common]), ('export_inventory.py', common)]
        entries.extend((script, ['--db', self.db, 'import', *common, '--source', 'synthetic'])
                       for script in ('recap.py', 'session_workflow.py'))
        for script, args in entries:
            result = self.cli(script, args, ok=False)
            self.assertNotIn('No such file', result.stderr)
            self.assertNotIn(str(missing), result.stderr)
            self.assertNotIn('Z' * 64, result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertFalse(self.db.exists())


if __name__ == '__main__':
    unittest.main()
