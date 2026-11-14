"""Synthetic adapter replay with explicit parsing labels and platform-independent bytes."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from contextlib import closing

from recaplib.session_workflow import import_export, import_export_bytes, _normalized_bytes, normalize
from recaplib.recovery import declare_recovery, rehearse_recovery

ROOT = Path(__file__).resolve().parents[1]


def rows(db, table):
    with closing(sqlite3.connect(db)) as connection:
        return connection.execute('SELECT * FROM ' + table + ' ORDER BY 1, 2').fetchall()


class ByteReplayTests(unittest.TestCase):
    def test_default_path_parity_all_formats_and_no_input_file(self):
        for kind, name in [('web', 'web-export.json'), ('local', 'local-session.jsonl'), ('local-codex', 'local-session.jsonl')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                path = ROOT / 'examples' / name
                expected = import_export(root / 'old.sqlite', 'demo', path, kind)
                raw = path.read_bytes()
                with patch.object(Path, 'read_bytes', side_effect=AssertionError('no input file read')):
                    actual = import_export_bytes(root / 'new.sqlite', 'demo', raw, name, kind,
                                                 newline='crlf' if os.linesep == '\r\n' else 'lf')
                self.assertEqual({k: v for k, v in actual.items() if k != 'replay'}, expected)
                for table in ['messages', 'artifacts', 'export_provenance', 'export_occurrences']:
                    self.assertEqual(rows(root / 'old.sqlite', table), rows(root / 'new.sqlite', table))

    def test_explicit_newline_is_deterministic_and_wrong_replay_fails(self):
        raw = (ROOT / 'examples/web-export.json').read_bytes()
        parsed = normalize(ROOT / 'examples/web-export.json', 'web')
        lf = _normalized_bytes(parsed, '\n')
        crlf = _normalized_bytes(parsed, '\r\n')
        self.assertEqual(crlf, lf.replace(b'\n', b'\r\n'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, newline in [('reference', 'lf'), ('same', 'lf'), ('other', 'crlf')]:
                import_export_bytes(root / (name + '.sqlite'), 'demo', raw, None, 'web', newline=newline)
            declare_recovery(root / 'reference.sqlite', root / 'manifest.json')
            same = rehearse_recovery(root / 'manifest.json', root / 'same.sqlite', root / 'same.json')
            self.assertEqual(same['status'], 'RECOVERY_REHEARSAL_PASSED')
            other = rehearse_recovery(root / 'manifest.json', root / 'other.sqlite', root / 'other.json')
            self.assertIn('messages_digest', other['failed_checks'])
            self.assertIn('artifact_rows', other['failed_checks'])

    def test_original_local_label_not_object_filename_preserves_identity(self):
        raw = (ROOT / 'examples/local-session.jsonl').read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, label in [('first', 'original.jsonl'), ('renamed', 'original.jsonl'), ('wrong', 'other.jsonl')]:
                import_export_bytes(root / (name + '.sqlite'), 'demo', raw, label, 'local', newline='lf')
            self.assertEqual(rows(root / 'first.sqlite', 'messages'), rows(root / 'renamed.sqlite', 'messages'))
            self.assertNotEqual(rows(root / 'first.sqlite', 'messages'), rows(root / 'wrong.sqlite', 'messages'))

    def test_selection_and_provenance_match_file_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = ROOT / 'examples/web-export.json'
            expected = import_export(root / 'file.sqlite', 'demo', path, 'web', conversation='synthetic-chat')
            actual = import_export_bytes(root / 'bytes.sqlite', 'demo', path.read_bytes(), None, 'web',
                                         conversation='synthetic-chat', newline='crlf' if os.linesep == '\r\n' else 'lf')
            self.assertEqual(expected['coverage'], actual['coverage'])
            self.assertEqual(rows(root / 'file.sqlite', 'export_occurrences'), rows(root / 'bytes.sqlite', 'export_occurrences'))

    def test_bad_arguments_and_duplicate_selection_never_open_database(self):
        raw = (ROOT / 'examples/web-export.json').read_bytes()
        defaults = dict(source='demo', raw=raw, label=None, kind='web', newline='lf')
        cases = [dict(raw=bytearray(raw)), dict(newline=None), dict(newline='native'), dict(kind='normalized'),
                 dict(source=''), dict(kind='local'), dict(label=3), dict(label=''), dict(label='\ud800'),
                 dict(conversation='unknown'), dict(conversation=True)]
        duplicate = json.loads(raw)
        cases.append(dict(raw=json.dumps(duplicate + duplicate).encode(), conversation='synthetic-chat'))
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / 'absent.sqlite'
            for changes in cases:
                with self.subTest(changes=changes.keys()), self.assertRaises(ValueError):
                    import_export_bytes(db, **dict(defaults, **changes))
                self.assertFalse(db.exists())

    def test_parser_significant_label_retains_metadata_only_admission(self):
        raw = (ROOT / 'examples/local-session.jsonl').read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = import_export_bytes(root / 'metadata.sqlite', 'demo', raw,
                                         'agents/synthetic/raw/export.jsonl', 'local', newline='lf')
            self.assertEqual(result['inserted'], 0)
            self.assertEqual(result['coverage']['reason_code'], 'agent_raw_evidence')
            self.assertEqual(result['coverage']['parser_admission_status'], 'accepted_metadata_only')
            with self.assertRaises(ValueError):
                import_export_bytes(root / 'never.sqlite', 'demo', raw,
                                    'session_index.jsonl', 'local', newline='lf')
            self.assertFalse((root / 'never.sqlite').exists())

    def test_existing_archive_uses_normal_transaction_and_deduplication(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Path(temporary) / 'archive.sqlite'
            raw = (ROOT / 'examples/web-export.json').read_bytes()
            first = import_export_bytes(db, 'demo', raw, None, 'web', newline='lf')
            second = import_export_bytes(db, 'demo', raw, None, 'web', newline='lf')
            self.assertEqual(first['inserted'], 2)
            self.assertEqual(second['inserted'], 0)
            with closing(sqlite3.connect(db)) as connection, connection:
                connection.execute("CREATE TRIGGER reject_replay BEFORE INSERT ON export_provenance BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                import_export_bytes(db, 'new', raw, None, 'web', newline='lf')
            self.assertEqual(len(rows(db, 'messages')), 2)
            self.assertEqual(len(rows(db, 'artifacts')), 1)

class ByteReplayGuideTests(unittest.TestCase):
    def test_documented_cli_and_python_example(self):
        import re
        import shlex
        import subprocess
        import sys
        document = (ROOT / 'docs/EXPORT_BYTE_REPLAY.md').read_text(encoding='utf-8')
        shell = re.findall(r'```sh\n(.*?)```', document, re.S)
        python = re.findall(r'```python\n(.*?)```', document, re.S)
        self.assertEqual((len(shell), len(python)), (1, 1))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'example output'
            output.mkdir()
            tokens = shlex.split(shell[0].strip())
            argv = [sys.executable] + [token.replace('OUTPUT', str(output)) for token in tokens[1:]]
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            # Replace the Python string literal, not unescaped native path text.
            script = python[0].replace("'OUTPUT/replayed.sqlite'", repr(str(output / 'replayed.sqlite')))
            result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            for table in ['messages', 'artifacts', 'export_occurrences']:
                self.assertEqual(rows(output / 'reference.sqlite', table), rows(output / 'replayed.sqlite', table))


if __name__ == '__main__':
    unittest.main()
