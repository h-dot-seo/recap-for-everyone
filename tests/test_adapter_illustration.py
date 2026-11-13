"""Execute the invented adapter, not a claim of real-vendor compatibility."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recap import ingest, validate_normalized
from recaplib.import_check import check_import

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('adapter_illustration', ROOT / 'examples/adapter_illustration.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def command_tokens(line, output, digest):
    # Split portable document syntax FIRST; never reparse native paths as POSIX.
    tokens = shlex.split(line)
    result = []
    for token in tokens:
        if token == 'OUTPUT':
            token = str(output)
        elif token.startswith('OUTPUT/'):
            token = str(output / token[len('OUTPUT/'):])
        elif token == 'HASH':
            token = digest
        result.append(token)
    return result


class AdapterIllustrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = self.home / 'foreign.json'
        self.output = self.home / 'normalized.jsonl'
        self.document = json.loads((ROOT / 'examples/foreign-sample.json').read_text(encoding='utf-8'))

    def write(self, document=None):
        self.source.write_text(json.dumps(self.document if document is None else document), encoding='utf-8')

    def reject(self):
        with self.assertRaises(ValueError):
            adapter.convert(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_sample_receipt_and_roundtrip(self):
        source = ROOT / 'examples/foreign-sample.json'
        before = source.read_bytes()
        receipt = adapter.convert(source, self.output)
        raw = self.output.read_bytes()
        rows, coverage = validate_normalized(raw)
        self.assertEqual(receipt['source_sha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual(receipt['normalized_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt['source_bytes'], len(before))
        self.assertEqual(receipt['normalized_bytes'], len(raw))
        self.assertEqual(receipt['records'], 2)
        self.assertFalse(receipt['database_access'])
        self.assertFalse(receipt['remote_mutation'])
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r', raw)
        self.assertEqual(len(raw.splitlines()), 2)
        self.assertEqual(rows[0][0]['text'], self.document['threads'][0]['entries'][0]['body'])
        db = self.home / 'archive.sqlite'
        result = ingest(db, 'synthetic', self.output, expected_sha256=receipt['normalized_sha256'])
        self.assertEqual(result['inserted'], 2)
        self.assertEqual(check_import(db, 'synthetic', self.output, 'normalized')['status'], 'NO_CONFLICTS')
        self.assertEqual(source.read_bytes(), before)
        rendered = json.dumps(receipt)
        for secret in ('synthetic-orchard', 'question-1', 'Invented orchard plan', '가상의'):
            self.assertNotIn(secret, rendered)

    def test_bom_source_keeps_original_hash_not_output_bom(self):
        self.source.write_bytes(b'\xef\xbb\xbf' + json.dumps(self.document).encode())
        raw = self.source.read_bytes()
        result = adapter.convert(self.source, self.output)
        self.assertEqual(result['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertFalse(self.output.read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_single_source_read(self):
        raw = json.dumps(self.document).encode()
        with patch.object(Path, 'read_bytes', return_value=raw) as reader:
            adapter.convert(self.source, self.output)
            self.assertEqual(reader.call_count, 1)

    def test_empty_inputs_and_empty_threads(self):
        for threads in ([], [dict(key='empty', label='', entries=[])]):
            self.write(dict(format='invented-chat-demo.v1', threads=threads))
            result = adapter.convert(self.source, self.output)
            self.assertEqual(result['records'], 0)
            self.assertEqual(self.output.read_bytes(), b'')
            self.output.unlink()

    def test_all_roles_and_supplied_order(self):
        entries = self.document['threads'][0]['entries']
        entries[:] = [dict(key=str(i), speaker=role, when=str(4-i), body=' \t')
                      for i, role in enumerate(('user', 'assistant', 'system', 'tool'))]
        self.write()
        adapter.convert(self.source, self.output)
        rows = [json.loads(line) for line in self.output.read_text().splitlines()]
        self.assertEqual([row['role'] for row in rows], ['user', 'assistant', 'system', 'tool'])
        self.assertEqual([row['timestamp'] for row in rows], ['4', '3', '2', '1'])
        self.assertEqual([row['text'] for row in rows], [' \t']*4)

    def test_bad_json_duplicate_keys_and_nonfinite(self):
        for raw in (b'{', b'\xff', b'\x00', b'[]',
                    b'{"format":"invented-chat-demo.v1","format":"invented-chat-demo.v1","threads":[]}',
                    b'{"format":"invented-chat-demo.v1","threads":[],"unused":NaN}'):
            self.source.write_bytes(raw)
            self.reject()

    def test_invalid_top_level_shapes(self):
        for document in (None, [], {}, dict(format='vendor', threads=[]),
                         dict(format='invented-chat-demo.v1', threads={}),
                         dict(format='invented-chat-demo.v1', threads=[], extra='not ignored')):
            self.source.write_text(json.dumps(document))
            self.reject()

    def test_invalid_thread_shapes_and_fields(self):
        for thread in (None, {}, dict(key='', label='', entries=[]),
                       dict(key='x', label=None, entries=[]), dict(key='x', label='\ud800', entries=[]),
                       dict(key='x', label='', entries={}), dict(key='x', label='', entries=[], extra=1)):
            self.write(dict(format='invented-chat-demo.v1', threads=[thread]))
            self.reject()

    def test_invalid_entry_fields(self):
        valid = dict(key='x', speaker='user', when='supplied', body='synthetic')
        invalid = [None, {}, dict(valid, extra=1)]
        for key in valid:
            for value in (None, '', 0, '\ud800'):
                invalid.append(dict(valid, **{key: value}))
        invalid.append(dict(valid, speaker='human'))
        for entry in invalid:
            self.document['threads'][0]['entries'] = [entry]
            self.write()
            self.reject()

    def test_duplicate_thread_or_message_ids_are_not_guessed(self):
        thread = self.document['threads'][0]
        self.document['threads'].append(thread)
        self.write(); self.reject()
        self.document['threads'].pop()
        thread['entries'].append(thread['entries'][0])
        self.write(); self.reject()

    def test_same_message_id_in_distinct_threads(self):
        other = json.loads(json.dumps(self.document['threads'][0]))
        other['key'] = 'different-thread'
        self.document['threads'].append(other)
        self.write()
        self.assertEqual(adapter.convert(self.source, self.output)['records'], 4)

    def test_existing_output_and_input_are_not_overwritten(self):
        self.write()
        before = self.source.read_bytes()
        with self.assertRaises(FileExistsError):
            adapter.convert(self.source, self.source)
        self.assertEqual(self.source.read_bytes(), before)
        self.output.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            adapter.convert(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b'existing')

    def test_missing_parent_not_created(self):
        self.write()
        parent = self.home / 'missing'
        with self.assertRaises(FileNotFoundError):
            adapter.convert(self.source, parent / 'out.jsonl')
        self.assertFalse(parent.exists())

    def test_final_symlink_not_followed(self):
        self.write()
        target = self.home / 'target'
        target.write_bytes(b'existing')
        try:
            self.output.symlink_to(target)
        except OSError:
            self.skipTest('symlink creation unavailable on this host')
        with self.assertRaises(FileExistsError):
            adapter.convert(self.source, self.output)
        self.assertEqual(target.read_bytes(), b'existing')

    def test_cli_error_does_not_echo_input_or_paths(self):
        self.source.write_text('{secret invalid input')
        result = subprocess.run([sys.executable, str(ROOT/'examples/adapter_illustration.py'),
                                 str(self.source), '--output', str(self.output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('secret', result.stderr)
        self.assertNotIn(str(self.source), result.stderr)
        self.assertFalse(self.output.exists())

    def test_placeholder_substitution_keeps_spaces_and_backslashes(self):
        for value in ('folder with spaces', r'C:\Users\Synthetic Person\Output'):
            output = Path(value)
            tokens = command_tokens('python recap.py inspect "OUTPUT/normalized.jsonl" --format normalized --expected-export-sha256 HASH', output, 'a'*64)
            self.assertEqual(tokens[3], str(output/'normalized.jsonl'))
            self.assertEqual(tokens[-1], 'a'*64)
            self.assertEqual(len(tokens), 8)
        self.assertEqual(command_tokens('mkdir "OUTPUT"', Path('two words'), 'hash'), ['mkdir', 'two words'])

    def test_documented_walkthrough_in_fresh_checkout(self):
        checkout = self.home / 'checkout with spaces'
        shutil.copytree(ROOT, checkout, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        output = self.home / 'output with spaces'
        sample = checkout / 'examples/foreign-sample.json'
        before = sample.read_bytes()
        blocks = re.findall(r'```sh\n(.*?)```', (checkout/'docs/ADAPTER_GUIDE.md').read_text(), re.S)
        self.assertEqual(len(blocks), 1)
        lines = blocks[0].strip().splitlines()
        self.assertEqual(len(lines), 4)
        digest = ''
        receipts = []
        for line in lines:
            self.assertNotIn('>', line)
            args = command_tokens(line, output, digest)
            if args[0] == 'mkdir':
                Path(args[1]).mkdir()
                continue
            self.assertEqual(args[0], 'python')
            result = subprocess.run([sys.executable, *args[1:]], cwd=checkout, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            receipts.append(receipt)
            if 'normalized_sha256' in receipt:
                digest = receipt['normalized_sha256']
        self.assertEqual(receipts[1]['original_sha256'], digest)
        self.assertEqual(receipts[2]['source_sha256'], digest)
        self.assertEqual(receipts[2]['inserted'], 2)
        self.assertEqual(sample.read_bytes(), before)
        self.assertEqual({p.name for p in output.iterdir()}, {'normalized.jsonl', 'archive.sqlite'})

    def test_script_runs_without_repository_imports(self):
        script = self.home / 'standalone.py'
        shutil.copyfile(ROOT/'examples/adapter_illustration.py', script)
        self.write()
        result = subprocess.run([sys.executable, '-I', str(script), str(self.source),
                                 '--output', str(self.output)], cwd=self.home,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['records'], 2)
