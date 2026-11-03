"""Synthetic typed local content profile based on the public Codex model."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from session_workflow import normalize, import_export, inspect_export


class LocalCodexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'session.jsonl'; self.db = Path(self.tmp.name) / 'archive.sqlite'

    def write(self, parts):
        records = [dict(type='session_meta', payload=dict(id='synthetic-typed')),
                   dict(type='response_item', timestamp='2026-01-01T00:00:00Z', payload=dict(
                        type='message', id='typed-user', role='user', content=parts))]
        self.path.write_text(''.join(json.dumps(r) + '\n' for r in records))

    def test_typed_text_preserves_whitespace_and_skips_metadata_text(self):
        self.write([dict(type='input_text', text='  Synthetic code\n'),
                    dict(type='input_image', text='DO_NOT_EXTRACT', image_url='synthetic-image'),
                    dict(type='output_text', text='\tsecond line  '), dict(text='UNTYPED')])
        rows, report = normalize(self.path, 'local-codex', include_report=True)
        self.assertEqual(rows[0]['text'], '  Synthetic code\n\n\tsecond line  ')
        self.assertEqual(rows[0]['origin_locator'], 'line:2')
        self.assertEqual(report['skipped_content_parts'], 2)
        self.assertEqual(report['local_content_profile'], 'codex')
        self.assertTrue(report['warnings'])
        self.assertNotIn('DO_NOT_EXTRACT', json.dumps(report))
        self.assertNotIn('UNTYPED', rows[0]['text'])

    def test_legacy_profile_keeps_original_behavior(self):
        self.write([dict(text='  Legacy untyped text  ')])
        self.assertEqual(normalize(self.path, 'local')[0]['text'], 'Legacy untyped text')
        self.assertEqual(normalize(self.path, 'local-codex'), [])
        self.assertEqual(inspect_export(self.path, 'local-codex')['skipped_content_parts'], 1)

    def test_whitespace_only_and_nontext_messages_are_not_extracted(self):
        self.write([dict(type='input_text', text=' \n\t'), dict(type='input_audio', audio_url='synthetic')])
        report = inspect_export(self.path, 'local-codex')
        self.assertEqual(report['extracted_messages'], 0)
        self.assertEqual(report['records_without_extracted_message'], 2)
        self.assertEqual(report['skipped_content_parts'], 1)
        self.assertTrue(report['warnings'])

    def test_malformed_known_parts_fail_before_database_creation(self):
        for content in (None, {}, ['text'], [dict(type='input_text')], [dict(type='output_text', text=42)]):
            with self.subTest(content=content):
                self.write(content)
                with self.assertRaises(ValueError): import_export(self.db, 'typed', self.path, 'local-codex')
                self.assertFalse(self.db.exists())

    def test_profile_switch_conflicts_without_rewriting_existing_evidence(self):
        self.write([dict(type='input_text', text='  Synthetic indented text  ')])
        import_export(self.db, 'same-source', self.path, 'local'); before = self.db.read_bytes()
        with self.assertRaisesRegex(ValueError, 'conflicting message identity'):
            import_export(self.db, 'same-source', self.path, 'local-codex')
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(import_export(self.db, 'typed-source', self.path, 'local-codex')['inserted'], 1)

    def test_typed_e2e_import_suggest_preview_apply_plan_and_check(self):
        self.write([dict(type='input_text', text='  Synthetic orchard plan  ')])
        original = self.path.read_bytes()
        def call(script, *args):
            r = subprocess.run([sys.executable, script, *map(str, args)], capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr); return json.loads(r.stdout)
        call('recap.py', 'inspect', self.path, '--format', 'local-codex')
        receipt = call('recap.py', '--db', self.db, 'import', self.path, '--format', 'local-codex', '--source', 'typed')
        self.assertEqual(receipt['inserted'], 1)
        identity = ('--source', 'typed', '--conversation', 'synthetic-typed')
        proposal = call('recap.py', '--db', self.db, 'suggest-title', *identity)
        path = Path(self.tmp.name) / 'proposal.json'; path.write_text(json.dumps(proposal))
        reviewed = call('title_proposal.py', '--db', self.db, 'preview', path); path.write_text(json.dumps(reviewed))
        call('title_proposal.py', '--db', self.db, 'apply', path)
        plan = call('recap.py', '--db', self.db, 'export-title-plan', self.path, '--format', 'local-codex', *identity)
        path.write_text(json.dumps(plan))
        self.assertTrue(call('recap.py', '--db', self.db, 'check-title-plan', self.path, path)['valid'])
        self.assertEqual(self.path.read_bytes(), original)

    def test_reimport_is_idempotent_and_inspection_matches_receipt(self):
        self.write([dict(type='output_text', text='Synthetic output')])
        report = inspect_export(self.path, 'local-codex'); report.pop('mode')
        first = import_export(self.db, 'typed', self.path, 'local-codex')
        self.assertEqual(first['coverage'], report)
        self.assertEqual(import_export(self.db, 'typed', self.path, 'local-codex')['inserted'], 0)
