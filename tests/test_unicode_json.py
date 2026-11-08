"""Synthetic Unicode-scalar validation before any archive mutation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from recap import ingest
from recaplib.session_workflow import import_export, inspect_export, normalize
from recaplib.strict_json import loads


class UnicodeJsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.json'
        self.db = Path(self.tmp.name) / 'archive.sqlite'

    def write(self, kind, text, extra=None):
        if kind == 'normalized':
            record = dict(conversation_id='c', message_id='m', role='user',
                          timestamp='synthetic', text=text)
            if extra is not None:
                record['extra'] = extra
            records = [record]
        elif kind in ('local', 'local-codex'):
            record = dict(type='response_item', payload=dict(type='message', id='m',
                          role='user', content=[dict(type='input_text', text=text)]))
            if extra is not None:
                record['extra'] = extra
            records = [dict(type='session_meta', payload=dict(id='c')), record]
        else:
            record = dict(id='c', mapping=dict(m=dict(parent=None, message=dict(
                          author=dict(role='user'), content=dict(content_type='text', parts=[text])))))
            if extra is not None:
                record['extra'] = extra
            self.path.write_text(json.dumps([record], ensure_ascii=True), encoding='utf-8')
            return
        self.path.write_text(''.join(json.dumps(record, ensure_ascii=True) + '\n' for record in records),
                             encoding='utf-8')

    def import_file(self, kind):
        if kind == 'normalized':
            return ingest(self.db, 'demo', self.path)
        return import_export(self.db, 'demo', self.path, kind)

    def test_loader_rejects_unpaired_surrogates_at_every_depth(self):
        for value in ('\ud800', '\udfff', 'prefix\ud800suffix', '\ud800x\udc00',
                      '\udc00\ud800', ['nested', {'key': '\ud800'}],
                      {'outer': [{'PRIVATE_SYNTHETIC\udfff': 'value'}]}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError) as caught:
                    loads(json.dumps(value, ensure_ascii=True))
                self.assertNotIsInstance(caught.exception, UnicodeError)
                self.assertNotIn('PRIVATE_SYNTHETIC', str(caught.exception))
                self.assertNotIn('prefix', str(caught.exception))

    def test_loader_preserves_valid_surrogate_pairs_emoji_and_korean(self):
        raw = r'{"\ud83d\ude00":["\ud83d\ude00","\ud800\udc00","\udbff\udfff","한글"]}'
        self.assertEqual(loads(raw), {'😀': ['😀', '\U00010000', '\U0010ffff', '한글']})
        value = {'한글 😀': ['문장', '😀', 'a\u2028b', '\ud7ff\ue000']}
        self.assertEqual(loads(json.dumps(value, ensure_ascii=False)), value)

    def test_all_import_formats_reject_before_database_creation(self):
        for kind in ('normalized', 'local', 'local-codex', 'web'):
            for text, extra in (('PRIVATE_SYNTHETIC\ud800', None),
                                ('Synthetic', {'nested': [{'PRIVATE_SYNTHETIC\udfff': 'value'}]})):
                with self.subTest(kind=kind, extra=extra is not None):
                    self.write(kind, text, extra)
                    with self.assertRaises(ValueError) as caught:
                        self.import_file(kind)
                    self.assertNotIsInstance(caught.exception, UnicodeError)
                    self.assertNotIn('PRIVATE_SYNTHETIC', str(caught.exception))
                    self.assertFalse(self.db.exists())

    def test_invalid_reimports_leave_existing_archive_bytes_unchanged(self):
        for kind in ('normalized', 'local', 'local-codex', 'web'):
            with self.subTest(kind=kind):
                self.db = Path(self.tmp.name) / (kind + '.sqlite')
                self.write(kind, 'Synthetic valid')
                self.import_file(kind)
                before = self.db.read_bytes()
                self.write(kind, 'PRIVATE_SYNTHETIC\udfff')
                with self.assertRaises(ValueError):
                    self.import_file(kind)
                self.assertEqual(self.db.read_bytes(), before)

    def test_inspection_and_import_consistently_reject_invalid_unicode(self):
        for kind in ('local', 'local-codex', 'web'):
            self.write(kind, 'PRIVATE_SYNTHETIC\ud800')
            with self.assertRaises(ValueError) as inspection:
                inspect_export(self.path, kind)
            with self.assertRaises(ValueError) as importing:
                self.import_file(kind)
            self.assertEqual(type(inspection.exception), type(importing.exception))
            self.assertFalse(self.db.exists())

    def test_valid_unicode_imports_and_inspection_reports_match(self):
        text = '한글 😀 \U00010000'
        for kind in ('normalized', 'local', 'local-codex', 'web'):
            with self.subTest(kind=kind):
                self.db = Path(self.tmp.name) / (kind + '.sqlite')
                self.write(kind, text)
                if kind != 'normalized':
                    self.assertEqual(normalize(self.path, kind)[0]['text'], text)
                    report = inspect_export(self.path, kind); report.pop('mode')
                receipt = self.import_file(kind)
                self.assertEqual(receipt['inserted'], 1)
                if kind != 'normalized':
                    self.assertEqual(receipt['coverage'], report)

    def test_cli_diagnostics_are_clean_and_omit_input_content(self):
        for kind in ('normalized', 'local', 'local-codex', 'web'):
            self.write(kind, 'PRIVATE_SYNTHETIC\ud800')
            commands = [[sys.executable, 'recap.py', '--db', str(self.db),
                         'ingest' if kind == 'normalized' else 'import', str(self.path), '--source', 'demo']]
            if kind != 'normalized':
                commands[0] += ['--format', kind]
                commands.append([sys.executable, 'recap.py', 'inspect', str(self.path), '--format', kind])
                commands.append([sys.executable, 'session_workflow.py', '--db', str(self.db), 'import',
                                 str(self.path), '--source', 'demo', '--format', kind])
            for command in commands:
                with self.subTest(kind=kind, command=command[1:3]):
                    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertTrue(result.stderr.strip())
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertNotIn('PRIVATE_SYNTHETIC', result.stderr)
                    self.assertNotIn('UnicodeEncodeError', result.stderr)
                    self.assertFalse(self.db.exists())


if __name__ == '__main__':
    unittest.main()
