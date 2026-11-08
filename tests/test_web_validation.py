"""Synthetic web-export rejection and provenance boundaries."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from recaplib.session_workflow import import_export, normalize
from recap import ingest


def message(text='Synthetic request', role='user', timestamp=0):
    return dict(author=dict(role=role), create_time=timestamp, content=dict(parts=[text]))


class WebValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'web.json'
        self.db = Path(self.tmp.name) / 'archive.sqlite'

    def write(self, mapping):
        self.path.write_text(json.dumps([dict(id='synthetic', mapping=mapping)]), encoding='utf-8')

    def reject(self, mapping):
        self.write(mapping)
        with self.assertRaises(ValueError):
            import_export(self.db, 'web', self.path, 'web')
        self.assertFalse(self.db.exists())

    def test_cycles_including_nodes_without_messages_are_rejected(self):
        for mapping in (
            {'a': dict(parent='a', message=message())},
            {'a': dict(parent='b'), 'b': dict(parent='a')},
            {'root': dict(parent=None), 'a': dict(parent='b'), 'b': dict(parent='a')},
        ):
            with self.subTest(mapping=mapping):
                self.reject(mapping)

    def test_invalid_node_and_parent_shapes(self):
        for mapping in ({'': {}}, {'a': None}, {'a': dict(parent=7)}, {'a': dict(parent='missing')}):
            with self.subTest(mapping=mapping):
                self.reject(mapping)

    def test_long_parent_chain_does_not_recurse(self):
        mapping = {str(i): dict(parent=str(i - 1) if i else None) for i in range(4000)}
        mapping['3999']['message'] = message()
        self.write(mapping)
        rows = normalize(self.path, 'web')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['parent_id'], '3998')

    def test_valid_forks_keep_original_node_order_and_parent_ids(self):
        self.write({'answer-b': dict(parent='root', message=message('Branch B', 'assistant')),
                    'root': dict(parent=None, message=message()),
                    'answer-a': dict(parent='root', message=message('Branch A', 'assistant'))})
        rows = normalize(self.path, 'web')
        self.assertEqual([r['message_id'] for r in rows], ['answer-b', 'root', 'answer-a'])
        self.assertEqual([r['parent_id'] for r in rows], ['root', None, 'root'])

    def test_duplicate_keys_fail_before_any_database_write(self):
        for raw in ('[{"id":"first","id":"second","mapping":{}}]',
                    '[{"id":"synthetic","mapping":{"a":{},"a":{}}}]'):
            self.path.write_text(raw)
            with self.assertRaises(ValueError):
                import_export(self.db, 'web', self.path, 'web')
            self.assertFalse(self.db.exists())

    def test_bad_export_leaves_existing_archive_unchanged(self):
        import_export(self.db, 'demo', 'examples/web-export.json', 'web')
        before = self.db.read_bytes()
        self.write({'a': dict(parent='a', message=message())})
        with self.assertRaises(ValueError):
            import_export(self.db, 'web', self.path, 'web')
        self.assertEqual(before, self.db.read_bytes())

    def test_zero_timestamp_and_bad_timestamp_shapes(self):
        self.write({'a': dict(message=message(timestamp=0))})
        self.assertEqual(normalize(self.path, 'web')[0]['timestamp'], '0')
        for value in ('', True, {}, [], float('nan'), float('inf')):
            with self.subTest(value=value):
                self.reject({'a': dict(message=message(timestamp=value))})

    def test_legacy_zero_timestamp_conflicts_without_rewriting_evidence(self):
        self.write({'a': dict(message=message(timestamp=0))})
        row = normalize(self.path, 'web')[0]
        row['timestamp'] = 'unknown'  # Representation produced before this fix.
        legacy = Path(self.tmp.name) / 'legacy.jsonl'
        legacy.write_text(json.dumps(row) + '\n', encoding='utf-8')
        ingest(self.db, 'web', legacy, provenance=[row])
        before = self.db.read_bytes()
        with self.assertRaisesRegex(ValueError, 'conflicting message identity'):
            import_export(self.db, 'web', self.path, 'web')
        self.assertEqual(before, self.db.read_bytes())

    def test_bad_authors_and_false_messages_report_clean_cli_errors(self):
        for author in (None, 'user', [], {}, {'role': 'unsupported'}):
            value = message(); value['author'] = author
            self.reject({'a': dict(message=value)})
        self.reject({'a': dict(message=False)})
        self.write({'a': dict(message=dict(content=dict(parts=['Synthetic']), author='user'))})
        result = subprocess.run([sys.executable, 'session_workflow.py', '--db', str(self.db),
                                 'import', str(self.path), '--format', 'web', '--source', 'web'],
                                capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(self.db.exists())
