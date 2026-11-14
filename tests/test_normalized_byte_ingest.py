"""Synthetic file/byte ingestion parity without temporary normalized exports."""
from codecs import BOM_UTF8
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recap import ingest, ingest_bytes, search
from recaplib.session_workflow import _normalized_bytes, import_export, normalize, titles
from recaplib.title_proposal import preview, apply_preview
from recaplib.title_suggestion import suggest


def row(**changes):
    value = dict(conversation_id='synthetic', message_id='u', role='user',
                 timestamp='0', title='Original synthetic title', text='합성 orchard plan 🌱')
    value.update(changes); return value


def encoded(rows):
    return ''.join(json.dumps(value, ensure_ascii=False)+'\n' for value in rows).encode()


def tables(db):
    with closing(sqlite3.connect(db)) as connection:
        names = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: sorted(connection.execute('SELECT * FROM "'+name.replace('"', '""')+'"').fetchall(), key=repr) for name in names}


class NormalizedByteIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root/'archive.sqlite'; self.path = self.root/'normalized.jsonl'

    def test_raw_file_and_byte_paths_keep_identical_receipts_tables_fts_and_bom_hash(self):
        value = row(text='합성\u2028orchard\tplan 🌱')
        raw = BOM_UTF8+b'\r\n'+json.dumps(value, ensure_ascii=False).encode()+b'\r\r\n'+encoded([value])
        self.path.write_bytes(raw); file_db = self.root/'file.sqlite'
        expected = ingest(file_db, 'demo', self.path)
        actual = ingest_bytes(self.db, 'demo', raw)
        self.assertEqual(actual, expected); self.assertEqual(tables(self.db), tables(file_db))
        self.assertEqual(actual['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual((actual['records'], actual['inserted']), (2, 1)); self.assertTrue(actual['utf8_bom_present'])
        self.assertEqual(search(self.db, 'orchard'), search(file_db, 'orchard'))
        self.assertEqual(self.path.read_bytes(), raw)

    def test_byte_ingest_needs_no_input_open_read_write_or_temporary_file(self):
        raw = encoded([row()])
        with patch.object(Path, 'open', side_effect=AssertionError('no input file')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('no input read')), \
             patch.object(Path, 'write_bytes', side_effect=AssertionError('no input write')), \
             patch('tempfile.TemporaryDirectory', side_effect=PermissionError('synthetic unavailable temp')), \
             patch('tempfile.NamedTemporaryFile', side_effect=PermissionError('synthetic unavailable temp')):
            result = ingest_bytes(self.db, 'demo', raw)
        self.assertEqual(result['inserted'], 1); self.assertTrue(self.db.exists())

    def test_file_wrapper_reads_one_snapshot_and_preserves_original_bytes(self):
        raw = encoded([row()]); self.path.write_bytes(raw); reader = Path.read_bytes; calls = []
        def read(path):
            calls.append(path); return reader(path)
        with patch.object(Path, 'read_bytes', read):
            result = ingest(self.db, 'demo', self.path)
        self.assertEqual(calls, [self.path]); self.assertEqual(result['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.path.read_bytes(), raw)

    def test_nonbyte_input_and_nontext_sources_fail_before_file_or_database_access(self):
        raw = encoded([row()])
        with patch('sqlite3.connect', side_effect=AssertionError('no database')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('validate source before reading')):
            for value in (None, raw.decode(), bytearray(raw), memoryview(raw), False, [], {}):
                with self.subTest(raw_type=type(value).__name__), self.assertRaises(ValueError):
                    ingest_bytes(self.db, 'demo', value)
            for source in (None, '', ' \n', False, 1, b'demo', [], {}):
                with self.subTest(source=source):
                    with self.assertRaisesRegex(ValueError, 'source must be nonempty text'):
                        ingest_bytes(self.db, source, raw)
                    with self.assertRaisesRegex(ValueError, 'source must be nonempty text'):
                        ingest(self.db, source, self.path)
        self.assertFalse(self.db.exists())

    def test_invalid_records_and_conflicting_input_reject_before_database_creation(self):
        cases = [b'\xff', b'[]\n', b'{"x":1,"x":2}\n', b'{"x":"\\ud800"}\n',
                 b'{"nested":'+b'['*10000+b'0'+b']'*10000+b'}',
                 encoded([row(role='unknown')]), encoded([row(timestamp=0)]),
                 encoded([row(), row(text='Conflicting text')])]
        with patch('sqlite3.connect', side_effect=AssertionError('no database before validation')):
            for raw in cases:
                with self.subTest(raw=raw[:50]), self.assertRaises(ValueError):
                    ingest_bytes(self.db, 'demo', raw)
        self.assertFalse(self.db.exists())

    def test_archive_conflict_rolls_back_all_new_rows_artifacts_and_fts(self):
        ingest_bytes(self.db, 'demo', encoded([row()]))
        before = tables(self.db); raw = encoded([row(message_id='new', text='Extra synthetic flower'), row(text='Conflict')])
        with self.assertRaisesRegex(ValueError, 'conflicting message identity'):
            ingest_bytes(self.db, 'demo', raw)
        self.assertEqual(tables(self.db), before); self.assertEqual(search(self.db, 'flower'), [])

    def test_empty_and_identical_reimports_keep_existing_receipt_policy(self):
        empty = ingest_bytes(self.db, 'empty', b'')
        self.assertEqual(empty, dict(source_sha256=hashlib.sha256(b'').hexdigest(), records=0, inserted=0))
        raw = encoded([row(), row()]); first = ingest_bytes(self.db, 'demo', raw)
        repeat = ingest_bytes(self.db, 'demo', raw)
        self.assertEqual((first['records'], first['inserted'], repeat['records'], repeat['inserted']), (2,1,2,0))

    def test_accepted_source_labels_remain_exact_without_coercion_or_normalization(self):
        raw = encoded([row()])
        for source in ('demo', ' demo ', '합성 🌱'):
            ingest_bytes(self.db, source, raw)
        with closing(sqlite3.connect(self.db)) as connection:
            sources = {r[0] for r in connection.execute('SELECT source_id FROM messages')}
        self.assertEqual(sources, {'demo', ' demo ', '합성 🌱'})


class ExportByteIngestWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = [('web', Path('examples/web-export.json'), 'synthetic-chat'),
                       ('local', Path('examples/local-session.jsonl'), 'synthetic-local'),
                       ('local-codex', Path('examples/source-attributed-session.jsonl'), 'synthetic-attributed')]

    def test_actual_legacy_text_writer_and_new_import_match_in_every_supported_format(self):
        for kind, path, identity in self.inputs:
            for selection in (None, identity):
                with self.subTest(kind=kind, selection=selection):
                    rows, coverage = normalize(path, kind, True, selection)
                    # This is the exact previous staging serialization, including
                    # the running OS's TextIOWrapper newline conversion.
                    staged = self.root/'old-normalized.jsonl'
                    staged.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows), encoding='utf-8')
                    old_raw = staged.read_bytes()
                    self.assertEqual(_normalized_bytes(rows), old_raw)
                    suffix = kind+('-selected' if selection else '-whole')
                    old_db = self.root/(suffix+'-old.sqlite'); new_db = self.root/(suffix+'-new.sqlite')
                    expected = ingest(old_db, 'demo', staged, provenance=rows)
                    actual = import_export(new_db, 'demo', path, kind, selection)
                    self.assertEqual(actual['coverage'], coverage)
                    self.assertEqual({k:v for k,v in actual.items() if k!='coverage'}, expected)
                    self.assertEqual(actual['source_sha256'], hashlib.sha256(old_raw).hexdigest())
                    actual_tables = tables(new_db)
                    if kind == 'web':
                        # Explicit web import now retains ID-only source topology;
                        # legacy normalized staging cannot reconstruct textless nodes.
                        topology = {name: actual_tables.pop(name) for name in
                                    ('export_nodes', 'export_conversations')}
                        self.assertTrue(topology['export_nodes'])
                        self.assertTrue(topology['export_conversations'])
                    self.assertEqual(actual_tables, tables(old_db))
                    self.assertEqual(search(new_db, 'synthetic'), search(old_db, 'synthetic'))

    def test_normalized_memory_writer_preserves_text_bytes_and_never_adds_a_bom(self):
        rows = [row(text='한글\r\nnewline\u2028separator 🌱', title='é e\u0301'), row(message_id='a')]
        untouched = copy.deepcopy(rows)
        expected = self.root/'old.jsonl'
        expected.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows), encoding='utf-8')
        raw = _normalized_bytes(rows)
        self.assertEqual(raw, expected.read_bytes()); self.assertFalse(raw.startswith(BOM_UTF8))
        self.assertEqual(rows, untouched); self.assertEqual(_normalized_bytes([]), b'')
        self.assertIn('한글'.encode(), raw); self.assertIn('\u2028'.encode(), raw)

    def test_three_format_import_and_review_work_without_python_temporary_staging(self):
        db = self.root/'archive.sqlite'; originals = {path:path.read_bytes() for _,path,_ in self.inputs}
        with patch('tempfile.TemporaryDirectory', side_effect=PermissionError('synthetic unavailable temp')), \
             patch('tempfile.NamedTemporaryFile', side_effect=PermissionError('synthetic unavailable temp')), \
             patch.object(Path, 'write_text', side_effect=AssertionError('no normalized file')), \
             patch.object(Path, 'write_bytes', side_effect=AssertionError('no source file')):
            for kind, path, identity in self.inputs:
                result = import_export(db, kind, path, kind)
                self.assertGreater(result['inserted'], 0)
                proposal = suggest(db, kind, identity); reviewed = preview(db, proposal)
                self.assertEqual(titles(db, kind, identity)['revision'], 0)
                applied = apply_preview(db, reviewed)
                self.assertEqual(applied['display_title'], proposal['title'])
        for path, raw in originals.items(): self.assertEqual(path.read_bytes(), raw)

    def test_reimport_adds_original_occurrences_without_rewriting_first_message_artifact(self):
        path = self.root/'web.json'; path.write_bytes(self.inputs[0][1].read_bytes()); db = self.root/'archive.sqlite'
        first_raw = path.read_bytes(); first = import_export(db, 'demo', path, 'web')
        with closing(sqlite3.connect(db)) as connection:
            before = connection.execute('SELECT message_id,source_sha256,source_line FROM messages ORDER BY message_pk').fetchall()
        path.write_bytes(first_raw+b'\n'); second_raw = path.read_bytes()
        second = import_export(db, 'demo', path, 'web')
        self.assertEqual(second['inserted'], 0); self.assertNotEqual(first['source_sha256'], second['source_sha256'])
        with closing(sqlite3.connect(db)) as connection:
            self.assertEqual(connection.execute('SELECT message_id,source_sha256,source_line FROM messages ORDER BY message_pk').fetchall(), before)
            hashes = {r[0] for r in connection.execute('SELECT DISTINCT original_hash FROM export_occurrences')}
            self.assertEqual(connection.execute('SELECT count(*) FROM export_occurrences').fetchone()[0], 4)
        self.assertEqual(hashes, {hashlib.sha256(first_raw).hexdigest(), hashlib.sha256(second_raw).hexdigest()})

    def test_provenance_failure_rolls_back_artifacts_messages_and_fts(self):
        kind,path,_ = self.inputs[0]; db = self.root/'archive.sqlite'; import_export(db, 'demo', path, kind)
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("CREATE TRIGGER reject_occurrence BEFORE INSERT ON export_occurrences BEGIN SELECT RAISE(ABORT, 'synthetic rejected occurrence'); END")
            connection.commit()
        before = tables(db); rows = normalize(path, kind)
        with self.assertRaises(sqlite3.IntegrityError): ingest_bytes(db, 'other', _normalized_bytes(rows), rows)
        self.assertEqual(tables(db), before)

    def test_cli_import_succeeds_with_staging_factory_denied_and_preserves_exit_contract(self):
        code = """import sys,tempfile,recap

def denied(*args, **kwargs): raise PermissionError('synthetic unavailable temporary directory')
tempfile.TemporaryDirectory=denied
tempfile.NamedTemporaryFile=denied
sys.argv=['recap.py',*sys.argv[1:]]
recap.main()
"""
        db = self.root/'cli.sqlite'
        for kind,path,_ in self.inputs:
            result = subprocess.run([sys.executable, '-c', code, '--db', str(db), 'import', str(path), '--format', kind, '--source', kind],
                capture_output=True, env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr); result.stdout.decode('ascii')
            self.assertGreater(json.loads(result.stdout)['inserted'], 0)


if __name__ == '__main__':
    unittest.main()
