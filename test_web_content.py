"""Synthetic explicit web content variants and full offline CLI round trip."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from session_workflow import normalize, import_export, inspect_export


class WebContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'web.json'
        self.db = Path(self.tmp.name) / 'archive.sqlite'

    def write(self, contents):
        mapping = {str(i): dict(parent=str(i-1) if i else None,
                    message=dict(author=dict(role='user' if i == 0 else 'tool'),
                                 content=content)) for i, content in enumerate(contents)}
        self.path.write_text(json.dumps([dict(id='synthetic', title='New chat', mapping=mapping)]))

    def call(self, script, *args, success=True):
        result = subprocess.run([sys.executable, script, *map(str, args)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return json.loads(result.stdout) if success else result.stderr

    def test_explicit_code_and_output_preserve_exact_text(self):
        self.write([dict(content_type='code', text='print("synthetic orchard")\n'),
                    dict(content_type='execution_output', text='synthetic orchard\n')])
        rows = normalize(self.path, 'web')
        self.assertEqual([r['text'] for r in rows], ['print("synthetic orchard")\n', 'synthetic orchard\n'])
        self.assertEqual(inspect_export(self.path, 'web')['text_field_messages'], 2)
        self.assertEqual(import_export(self.db, 'web', self.path, 'web')['inserted'], 2)
        self.assertEqual(import_export(self.db, 'web', self.path, 'web')['inserted'], 0)

    def test_whitespace_only_text_is_counted_but_not_extracted(self):
        self.write([dict(content_type='code', text=' \n\t')])
        rows, report = normalize(self.path, 'web', include_report=True)
        self.assertEqual(rows, [])
        self.assertEqual(report['text_field_messages'], 1)
        self.assertEqual(report['nodes_without_extracted_text'], 1)
        self.assertTrue(report['warnings'])

    def test_unknown_text_and_nontext_metadata_are_not_stringified(self):
        self.write([dict(content_type='unrecognized', text='NEVER_EXTRACT'),
                    dict(parts=['visible', dict(text='NEVER_EXTRACT', asset='PRIVATE_ASSET')])])
        rows, report = normalize(self.path, 'web', include_report=True)
        self.assertEqual([r['text'] for r in rows], ['visible'])
        self.assertEqual(report['unsupported_text_fields'], 1)
        self.assertEqual(report['nontext_parts_skipped'], 1)
        self.assertNotIn('NEVER_EXTRACT', json.dumps(report))
        self.assertNotIn('PRIVATE_ASSET', json.dumps(report))
        self.assertTrue(report['warnings'])

    def test_bad_and_ambiguous_text_shapes_fail_before_db_creation(self):
        for content in [dict(content_type='code'), dict(content_type='code', text=5),
                        dict(content_type='execution_output', text=None),
                        dict(content_type='code', text='synthetic', parts=['ambiguous'])]:
            with self.subTest(content=content):
                self.write([content])
                with self.assertRaises(ValueError):
                    import_export(self.db, 'web', self.path, 'web')
                self.assertFalse(self.db.exists())

    def test_fork_coverage_warns_without_exposing_ids(self):
        self.write([dict(parts=['synthetic'])] * 3)
        data = json.loads(self.path.read_text())
        data[0]['mapping']['2']['parent'] = '0'
        data[0]['current_node'] = '2'
        self.path.write_text(json.dumps(data))
        report = inspect_export(self.path, 'web')
        self.assertEqual(report['forked_conversations'], 1)
        self.assertEqual(report['extracted_messages'], 3)
        self.assertIn('all branches', report['warnings'][0])

    def test_new_shape_import_generate_preview_apply_search_restore_cli(self):
        self.write([dict(content_type='code', text='Synthetic orchard sorting plan'),
                    dict(content_type='execution_output', text='Synthetic tool result')])
        source = self.path.read_bytes()
        self.assertEqual(self.call('recap.py', 'inspect', self.path, '--format', 'web')['extracted_messages'], 2)
        self.call('recap.py', '--db', self.db, 'import', self.path, '--format', 'web', '--source', 'web')
        baseline = self.db.read_bytes()
        identity = ('--source', 'web', '--conversation', 'synthetic')
        proposal = self.call('title_adapter.py', '--db', self.db, *identity, 'generate')
        self.assertEqual(self.db.read_bytes(), baseline)
        self.assertEqual(proposal['evidence_message_ids'], ['0'])
        path = Path(self.tmp.name) / 'proposal.json'
        path.write_text(json.dumps(proposal))
        preview = self.call('title_proposal.py', '--db', self.db, 'preview', path)
        self.assertEqual(self.db.read_bytes(), baseline)
        path.write_text(json.dumps(preview))
        changed = self.call('title_proposal.py', '--db', self.db, 'apply', path)
        self.call('title_proposal.py', '--db', self.db, 'apply', path, success=False)
        self.assertEqual(self.call('recap.py', '--db', self.db, 'find', 'orchard')['total_matches'], 1)
        detail = self.call('recap.py', '--db', self.db, 'show', *identity)
        self.assertEqual(len(detail['messages']), 2)
        self.call('recap.py', '--db', self.db, 'title', *identity, '--set', 'New chat',
                  '--expected-revision', changed['revision'])
        self.assertEqual(self.path.read_bytes(), source)
