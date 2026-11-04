"""Synthetic first-run checks: no exports, archive databases or network needed."""
import contextlib
import io
import json
import re
import shlex
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import runtime_check


class RuntimeCheckTests(unittest.TestCase):
    def fake_sqlite(self, failure=None, row=('synthetic runtime probe',)):
        connection = Mock(spec=['execute', 'close'])
        cursor = Mock(spec=['fetchone'])
        cursor.fetchone.return_value = row
        connection.execute.return_value = cursor
        module = types.SimpleNamespace(sqlite_version='3.42.0', Error=sqlite3.Error,
                                       connect=Mock(return_value=connection))
        error = sqlite3.OperationalError('/private/synthetic/PRIVATE_PATH: 秘密')
        if failure == 'connect':
            module.connect.side_effect = error
        elif failure in ('create', 'insert', 'query'):
            index = ('create', 'insert', 'query').index(failure)
            connection.execute.side_effect = [cursor] * index + [error]
        elif failure == 'fetch':
            cursor.fetchone.side_effect = error
        elif failure == 'close':
            connection.close.side_effect = error
        return module, connection

    def run_fake(self, module):
        with patch.object(runtime_check.importlib, 'import_module', return_value=module) as importer:
            result = runtime_check.check_runtime()
        importer.assert_called_once_with('sqlite3')
        return result

    def assert_fixed_fields(self, result):
        self.assertEqual(set(result), {'schema', 'status', 'python', 'sqlite', 'reason_codes',
                                      'archive_access', 'network_access', 'scope', 'limitations'})
        self.assertEqual(result['schema'], 'recap.runtime-check.v1')
        self.assertIs(result['archive_access'], False)
        self.assertIs(result['network_access'], False)
        self.assertEqual(result['scope'], 'this interpreter and one synthetic in-memory FTS5 round trip only')
        self.assertEqual(result['limitations'], 'Not a full test suite, checkout verification, shell-encoding check, filesystem-permission check or export-compatibility guarantee.')
        self.assertEqual(result['python']['minimum'], '3.10')
        self.assertNotIn('PRIVATE_PATH', json.dumps(result))
        self.assertNotIn('/private/', json.dumps(result))

    def test_actual_runtime(self):
        result = runtime_check.check_runtime()
        self.assert_fixed_fields(result)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['reason_codes'], [])
        self.assertEqual(result['python']['version'], '.'.join(map(str, sys.version_info[:3])))
        self.assertEqual(result['sqlite'], {'available': True, 'version': sqlite3.sqlite_version,
                                          'fts5_probe': 'PASS'})

    def test_unsupported_python_never_imports_sqlite(self):
        for version in ((2, 7, 18), (3, 8, 20), (3, 9, 99)):
            with self.subTest(version=version), patch.object(runtime_check.sys, 'version_info', version), \
                    patch.object(runtime_check.importlib, 'import_module') as importer:
                result = runtime_check.check_runtime()
                importer.assert_not_called()
                self.assert_fixed_fields(result)
                self.assertFalse(result['python']['supported'])
                self.assertEqual(result['status'], 'UNSUPPORTED_RUNTIME')
                self.assertEqual(result['reason_codes'], ['PYTHON_TOO_OLD'])
                self.assertEqual(result['sqlite'], {'available': None, 'version': None, 'fts5_probe': 'NOT_RUN'})

    def test_supported_version_boundaries(self):
        for version in ((3, 10, 0), (3, 10, 99), (3, 11, 0), (3, 14, 0), (4, 0, 0)):
            with self.subTest(version=version), patch.object(runtime_check.sys, 'version_info', version):
                module, connection = self.fake_sqlite()
                result = self.run_fake(module)
                self.assertEqual(result['status'], 'READY')
                self.assertTrue(result['python']['supported'])
                self.assertEqual(result['python']['version'], '.'.join(map(str, version)))
                connection.close.assert_called_once_with()

    def test_missing_sqlite_is_sanitized(self):
        for error in (ImportError('/private/synthetic/PRIVATE_PATH'),
                      ModuleNotFoundError('PRIVATE_PATH 秘密'), OSError('PRIVATE_PATH.dll')):
            with self.subTest(error=type(error)), \
                    patch.object(runtime_check.importlib, 'import_module', side_effect=error):
                result = runtime_check.check_runtime()
                self.assert_fixed_fields(result)
                self.assertEqual(result['status'], 'UNSUPPORTED_RUNTIME')
                self.assertEqual(result['reason_codes'], ['SQLITE_IMPORT_UNAVAILABLE'])
                self.assertEqual(result['sqlite'], {'available': False, 'version': None, 'fts5_probe': 'NOT_RUN'})

    def test_synthetic_round_trip_and_single_memory_connection(self):
        module, connection = self.fake_sqlite()
        result = self.run_fake(module)
        self.assert_fixed_fields(result)
        self.assertEqual(result['status'], 'READY')
        module.connect.assert_called_once_with(':memory:')
        calls = connection.execute.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertIn('USING fts5', calls[0].args[0])
        self.assertEqual(calls[1].args[1], ('synthetic runtime probe',))
        self.assertIn('MATCH ?', calls[2].args[0])
        self.assertEqual(calls[2].args[1], ('synthetic',))
        connection.close.assert_called_once_with()
        self.assertEqual([call[0] for call in connection.mock_calls],
                         ['execute', 'execute', 'execute', 'execute().fetchone', 'close'])

    def test_sqlite_errors_fail_closed_and_cleanup(self):
        for failure in ('connect', 'create', 'insert', 'query', 'fetch', 'close'):
            with self.subTest(failure=failure):
                module, connection = self.fake_sqlite(failure=failure)
                result = self.run_fake(module)
                self.assert_fixed_fields(result)
                self.assertEqual(result['status'], 'UNSUPPORTED_RUNTIME')
                self.assertEqual(result['reason_codes'], ['SQLITE_FTS5_PROBE_FAILED'])
                self.assertEqual(result['sqlite']['fts5_probe'], 'FAIL')
                module.connect.assert_called_once_with(':memory:')
                if failure == 'connect':
                    connection.close.assert_not_called()
                else:
                    connection.close.assert_called_once_with()

    def test_unexpected_results_fail_and_close(self):
        for row in (None, (), ('wrong',), ('synthetic runtime probe', 'extra'), ['synthetic runtime probe']):
            with self.subTest(row=row):
                module, connection = self.fake_sqlite(row=row)
                result = self.run_fake(module)
                self.assert_fixed_fields(result)
                self.assertEqual(result['status'], 'UNSUPPORTED_RUNTIME')
                self.assertEqual(result['reason_codes'], ['FTS5_UNEXPECTED_RESULT'])
                self.assertEqual(result['sqlite']['fts5_probe'], 'FAIL')
                connection.close.assert_called_once_with()
                module.connect.assert_called_once_with(':memory:')

    def test_non_sqlite_exception_still_closes_without_retry(self):
        module, connection = self.fake_sqlite()
        connection.execute.side_effect = RuntimeError('synthetic implementation failure')
        with self.assertRaises(RuntimeError):
            self.run_fake(module)
        connection.close.assert_called_once_with()
        module.connect.assert_called_once_with(':memory:')

    def test_main_ascii_json_and_exit_codes(self):
        for status, expected in (('READY', 0), ('UNSUPPORTED_RUNTIME', 1)):
            with self.subTest(status=status), patch.object(sys, 'argv', ['runtime_check.py']), \
                    patch.object(runtime_check, 'check_runtime', return_value={'status': status, 'synthetic': '秘密'}), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runtime_check.main(), expected)
                rendered = output.getvalue()
                self.assertTrue(rendered.isascii())
                self.assertEqual(json.loads(rendered), {'status': status, 'synthetic': '秘密'})

    def test_help_and_bad_arguments_never_probe(self):
        for args, expected in ((['--help'], 0), (['--archive', 'synthetic.sqlite'], 2),
                               (['synthetic.json'], 2), (['--unknown'], 2)):
            with self.subTest(args=args), patch.object(sys, 'argv', ['runtime_check.py'] + args), \
                    patch.object(runtime_check, 'check_runtime') as check, \
                    contextlib.redirect_stdout(io.StringIO()) as stdout, \
                    contextlib.redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as exc:
                    runtime_check.main()
                self.assertEqual(exc.exception.code, expected)
                check.assert_not_called()
                self.assertNotIn('Traceback', stdout.getvalue() + stderr.getvalue())
                if expected == 0:
                    self.assertIn('in-memory', stdout.getvalue())

    def test_cli_from_empty_temporary_directory(self):
        script = str(Path(runtime_check.__file__).resolve())
        with tempfile.TemporaryDirectory() as cwd:
            for args, code in (([], 0), (['--help'], 0), (['unexpected'], 2)):
                with self.subTest(args=args):
                    result = subprocess.run([sys.executable, '-B', script] + args, cwd=cwd,
                                            capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertTrue(result.stdout.isascii())
                    self.assertEqual(list(Path(cwd).iterdir()), [])
                    if not args:
                        self.assertEqual(json.loads(result.stdout)['status'], 'READY')
                        self.assertEqual(result.stderr, b'')

    def test_probe_audit_rejects_disk_network_process_and_extensions(self):
        # Preload imports before the audit boundary: interpreter module loading
        # itself is not archive access. Audit hooks live only in this child.
        root = str(Path(runtime_check.__file__).resolve().parent)
        code = '''
import sys, sqlite3, json
sys.path.insert(0, ROOT)
import runtime_check
seen = []
def audit(event, args):
    if event == 'sqlite3.connect':
        # CPython 3.10 can report the encoded filename in this audit event.
        # Accept only these two exact in-memory representations, never a URI
        # or filesystem path and never a generalized bytes decode/fallback.
        assert (type(args) is tuple and len(args) == 1 and
                (type(args[0]) is str and args[0] == ':memory:' or
                 type(args[0]) is bytes and args[0] == b':memory:')), args
        seen.append(event)
    if event in ('open', 'os.listdir', 'os.scandir', 'os.system', 'subprocess.Popen',
                 'sqlite3.enable_load_extension', 'sqlite3.load_extension') or event.startswith('socket.'):
        raise AssertionError('unexpected external operation: ' + event)
for args in ((':memory:',), (b':memory:',)):
    audit('sqlite3.connect', args)
for args in (('synthetic.sqlite',), (b'synthetic.sqlite',), ('file::memory:',),
             (b'file::memory:',), ('',), (None,), (), (':memory:', 'extra'),
             [':memory:'], (bytearray(b':memory:'),), (memoryview(b':memory:'),)):
    try:
        audit('sqlite3.connect', args)
    except AssertionError:
        pass
    else:
        raise AssertionError('nonliteral memory target accepted')
seen.clear()
sys.addaudithook(audit)
result = runtime_check.check_runtime()
assert result['status'] == 'READY', result
assert seen == ['sqlite3.connect'], seen
print(json.dumps(result))
'''.replace('ROOT', repr(root))
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run([sys.executable, '-B', '-c', code], cwd=cwd,
                                    capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'READY')
            self.assertEqual(list(Path(cwd).iterdir()), [])


class DocumentedRuntimeEntryTests(unittest.TestCase):
    """Validate documented argv with this interpreter, not literal shell support."""

    root = Path(runtime_check.__file__).resolve().parent

    def shell_lines(self, document):
        return [line.strip() for block in re.findall(r'```sh\n(.*?)```', document, re.S)
                for line in block.splitlines() if line.strip()]

    def test_install_branch_and_safe_entry_commands(self):
        document = (self.root / 'docs/INSTALL.md').read_text(encoding='utf-8')
        commands = [shlex.split(line) for line in self.shell_lines(document)]
        clones = [args for args in commands if args[:2] == ['git', 'clone']]
        self.assertEqual(clones, [[
            'git', 'clone', '--branch', 'codex/core-workflows-20261103', '--single-branch',
            'https://github.com/h-dot-seo/recap-for-everyone.git', 'recap-for-everyone-workflows']])
        # Clone is inspected as text only. No Git command or network operation runs.
        for expected in (['python', 'runtime_check.py'], ['python', 'recap.py', '--help']):
            self.assertEqual(commands.count(expected), 1)
            argv = [sys.executable, '-B', str(self.root / expected[1])] + expected[2:]
            with tempfile.TemporaryDirectory() as cwd:
                result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                        encoding='utf-8', timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')
                self.assertEqual(list(Path(cwd).iterdir()), [])
            if expected[1] == 'runtime_check.py':
                self.assertEqual(json.loads(result.stdout)['status'], 'READY')
            else:
                for command in ('inspect', 'import', 'review-titles', 'preview-title'):
                    self.assertIn(command, result.stdout)
        # Manifest verification is intentionally deferred until publication freeze.
        self.assertIn(['python', 'verify_manifest.py'], commands)
        self.assertIn('chosen launcher', document)
        self.assertIn('py -3', document)
        self.assertIn('not** prove', document)
        for relative in ('README.md', 'docs/START_HERE.md', 'docs/TITLE_WALKTHROUGH.md'):
            linked = (self.root / relative).read_text(encoding='utf-8')
            self.assertIn('INSTALL.md', linked)
            self.assertIn('launcher', linked)

    def test_readme_normalized_quickstart_with_synthetic_copy(self):
        readme = (self.root / 'README.md').read_text(encoding='utf-8')
        section = readme.split('## Quick start for already-normalized JSONL', 1)[1].split('## ', 1)[0]
        lines = self.shell_lines(section)
        self.assertEqual(len(lines), 5)
        self.assertEqual(shlex.split(lines[0]), ['mkdir', '../recap-normalized-demo'])
        source = self.root / 'examples/conversations.jsonl'
        source_bytes = source.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / 'checkout'
            examples = checkout / 'examples'
            examples.mkdir(parents=True)
            fixture = examples / 'conversations.jsonl'
            fixture.write_bytes(source_bytes)
            outputs = []
            for line in lines:
                args = shlex.split(line)
                if args == ['python', '-m', 'unittest', 'discover', '-v']:
                    continue  # Never recursively invoke the containing suite.
                if args[0] == 'mkdir':
                    (checkout / args[1]).mkdir()
                    continue
                self.assertEqual(args[:2], ['python', 'recap.py'])
                self.assertEqual(args[2:4], ['--db', '../recap-normalized-demo/archive.sqlite'])
                # Substitute the chosen launcher and script location only; all
                # documented workflow arguments and relative paths stay intact.
                argv = [sys.executable, '-B', str(self.root / args[1])] + args[2:]
                result = subprocess.run(argv, cwd=checkout, capture_output=True, text=True,
                                        encoding='utf-8', timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')
                outputs.append((args[4], result.stdout))
            self.assertEqual([command for command, _ in outputs], ['ingest', 'search', 'stats'])
            self.assertIn('demo-conversation', outputs[1][1])
            self.assertIn('orchard', outputs[1][1].lower())
            self.assertEqual(json.loads(outputs[2][1]), {'messages': 2, 'artifacts': 1})
            self.assertTrue((root / 'recap-normalized-demo/archive.sqlite').is_file())
            self.assertEqual(fixture.read_bytes(), source_bytes)
            self.assertEqual(sorted(path.relative_to(checkout).as_posix()
                                    for path in checkout.rglob('*') if path.is_file()),
                             ['examples/conversations.jsonl'])
        self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == '__main__':
    unittest.main()
