"""Synthetic source-label Unicode boundaries before source or archive access."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from conversation_search import find
from import_check import check_import
from recap import ingest, ingest_bytes, search
from session_workflow import import_export, titles
from title_proposal import apply_preview, preview
from title_suggestion import suggest


SURROGATES = ('\ud800', '\udfff', 'PRIVATE_SYNTHETIC\udc80', '\ud83c\udf31')
VALID_LABELS = ('한글 출처', 'e\u0301', 'é', 'source 🌱', '  padded source  ', 'nul\x00source')
INVALID_LABELS = (None, '', ' \t\n', False, 0, 1, b'source', [], {})


class SourceLabelValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.missing = self.root / 'missing.sqlite'
        self.normalized = self.root / 'normalized.jsonl'
        self.raw = (json.dumps(dict(conversation_id='synthetic', message_id='u',
            role='user', timestamp='0', title='Original', text='Synthetic orchard plan 🌱'),
            ensure_ascii=False) + '\n').encode('utf-8')
        self.normalized.write_bytes(self.raw)
        self.web = self.root / 'web.json'
        self.web.write_text(json.dumps([dict(id='synthetic', title='Original', mapping={
            'u': dict(parent=None, message=dict(author=dict(role='user'), create_time=0,
                content=dict(parts=['Synthetic orchard plan 🌱'])))} )]), encoding='utf-8')
        self.local = self.root / 'local.jsonl'
        self.local.write_text('\n'.join(json.dumps(record) for record in [
            dict(type='session_meta', payload=dict(id='synthetic')),
            dict(type='response_item', timestamp=0, payload=dict(type='message', role='user',
                id='u', content=[dict(type='input_text', text='Synthetic orchard plan 🌱')]))
        ]) + '\n', encoding='utf-8')
        ingest_bytes(self.db, 'baseline', self.raw)

    def operations(self, db, source):
        yield 'ingest', lambda: ingest(db, source, self.normalized)
        yield 'ingest_bytes', lambda: ingest_bytes(db, source, self.raw)
        for kind, path in (('web', self.web), ('local', self.local), ('local-codex', self.local)):
            yield 'import-' + kind, lambda kind=kind, path=path: import_export(db, source, path, kind)
            yield 'check-' + kind, lambda kind=kind, path=path: check_import(db, source, path, kind)

    def assert_rejected_before_access(self, sources, message):
        before = {path: path.read_bytes() for path in (self.db, self.normalized, self.web, self.local)}
        with patch('sqlite3.connect', side_effect=AssertionError('database accessed')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('source read')), \
             patch.object(Path, 'open', side_effect=AssertionError('source opened')):
            for source in sources:
                for db in (self.db, self.missing):
                    for name, operation in self.operations(db, source):
                        with self.subTest(source=repr(source), db=db.name, operation=name):
                            with self.assertRaises(ValueError) as caught:
                                operation()
                            self.assertEqual(str(caught.exception), message)
        self.assertFalse(self.missing.exists())
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_surrogates_rejected_before_source_and_database_access(self):
        self.assert_rejected_before_access(SURROGATES, 'source must contain valid Unicode text')

    def test_empty_and_nontext_rejected_before_source_and_database_access(self):
        self.assert_rejected_before_access(INVALID_LABELS, 'source must be nonempty text')

    def test_surrogate_validation_precedes_invalid_byte_payload(self):
        with patch('sqlite3.connect', side_effect=AssertionError('database accessed')):
            for raw in (None, 'not bytes', b'not JSON', bytearray(self.raw)):
                with self.subTest(payload_type=type(raw).__name__), self.assertRaisesRegex(
                        ValueError, '^source must contain valid Unicode text$'):
                    ingest_bytes(self.missing, 'bad\ud800', raw)
        self.assertFalse(self.missing.exists())

    def test_valid_labels_preserved_exactly_in_normalized_file_and_byte_import(self):
        for index, source in enumerate(VALID_LABELS):
            for function in (ingest, ingest_bytes):
                with self.subTest(source=repr(source), operation=function.__name__):
                    db = self.root / ('normalized-%s-%s.sqlite' % (index, function.__name__))
                    result = function(db, source, self.normalized if function is ingest else self.raw)
                    self.assertEqual(result['inserted'], 1)
                    self.assertEqual(search(db, 'orchard')[0]['source_id'], source)
                    with closing(sqlite3.connect(db)) as connection:
                        stored = connection.execute('SELECT source_id FROM artifacts').fetchone()[0]
                        self.assertEqual(stored.encode('utf-8'), source.encode('utf-8'))
                    self.assertEqual(function(db, source, self.normalized if function is ingest else self.raw)['inserted'], 0)
        self.assertEqual(self.normalized.read_bytes(), self.raw)

    def test_valid_labels_preserved_in_all_export_formats_and_conflict_checks(self):
        for index, source in enumerate(VALID_LABELS):
            for kind, path in (('web', self.web), ('local', self.local), ('local-codex', self.local)):
                with self.subTest(source=repr(source), kind=kind):
                    db = self.root / ('export-%s-%s.sqlite' % (index, kind))
                    before = path.read_bytes()
                    self.assertEqual(import_export(db, source, path, kind)['inserted'], 1)
                    archive_before = db.read_bytes()
                    checked = check_import(db, source, path, kind)
                    self.assertEqual(checked['status'], 'NO_CONFLICTS')
                    self.assertEqual(checked['archive_comparison'], dict(new=0, identical=1, conflicting=0))
                    self.assertEqual(db.read_bytes(), archive_before)
                    self.assertEqual(path.read_bytes(), before)
                    self.assertEqual(search(db, 'orchard')[0]['source_id'].encode('utf-8'), source.encode('utf-8'))

    def test_unicode_labels_remain_distinct_without_normalization_or_trimming(self):
        for source in ('e\u0301', 'é', 'label', ' label ', 'nul\x00one', 'nul\x00two'):
            self.assertEqual(ingest_bytes(self.db, source, self.raw)['inserted'], 1)
        actual = {row['source_id'] for row in search(self.db, 'orchard')}
        self.assertEqual(actual, {'baseline', 'e\u0301', 'é', 'label', ' label ', 'nul\x00one', 'nul\x00two'})

    def test_unicode_label_import_preview_explicit_apply_search_roundtrip(self):
        source = '  합성 e\u0301 🌱  '
        source_before = self.web.read_bytes()
        import_export(self.db, source, self.web, 'web')
        archive_before = self.db.read_bytes()
        proposal = suggest(self.db, source, 'synthetic')
        reviewed = preview(self.db, proposal, replacement_title='합성 과수원 계획 🌱', with_evidence=True)
        self.assertEqual(reviewed['proposal']['source'], source)
        self.assertEqual(self.db.read_bytes(), archive_before)
        self.assertEqual(titles(self.db, source, 'synthetic')['revision'], 0)
        self.assertEqual(find(self.db, '과수원 계획', source=source)['total_matches'], 0)
        applied = apply_preview(self.db, reviewed)
        self.assertEqual(applied['display_title'], '합성 과수원 계획 🌱')
        self.assertGreater(applied['revision'], 0)
        found = find(self.db, '과수원 계획', source=source)
        self.assertEqual(found['total_matches'], 1)
        hit = found['matches'][0]
        self.assertEqual(hit['source_id'], source)
        self.assertEqual(hit['conversation_id'], 'synthetic')
        self.assertEqual(hit['display_title'], '합성 과수원 계획 🌱')
        self.assertEqual(hit['title_revision'], applied['revision'])
        self.assertTrue(hit['matched_title'])
        self.assertEqual(hit['message_match_count'], 0)
        self.assertIn(source, {row['source_id'] for row in search(self.db, 'orchard')})
        self.assertEqual(self.web.read_bytes(), source_before)
        with self.assertRaisesRegex(ValueError, 'stale title preview'):
            apply_preview(self.db, reviewed)

    @unittest.skipIf(os.name == 'nt', 'Windows argv cannot represent POSIX undecodable byte arguments')
    def test_posix_invalid_byte_argv_is_clean_and_never_creates_database(self):
        root = Path(__file__).resolve().parent
        entries = [
            ('recap.py', ['--db', self.missing, 'ingest', self.normalized]),
            ('recap.py', ['--db', self.missing, 'import', self.web, '--format', 'web']),
            ('session_workflow.py', ['--db', self.missing, 'import', self.local, '--format', 'local-codex']),
            ('recap.py', ['--db', self.missing, 'check-import', self.web, '--format', 'web']),
            ('import_check.py', ['--db', self.missing, self.local, '--format', 'local'])]
        before = {path: path.read_bytes() for path in (self.db, self.normalized, self.web, self.local)}
        for script, args in entries:
            command = [os.fsencode(sys.executable), b'-B', os.fsencode(root / script)]
            command += [os.fsencode(str(arg)) for arg in args] + [b'--source', b'PRIVATE_SYNTHETIC\xff']
            with self.subTest(script=script, command=args):
                result = subprocess.run(command, capture_output=True, cwd=self.root, timeout=20,
                                        env=dict(os.environ, PYTHONUTF8='1'))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b'')
                self.assertEqual(result.stderr, b'source must contain valid Unicode text\n')
                self.assertFalse(self.missing.exists())
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
