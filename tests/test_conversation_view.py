import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from recaplib.conversation_view import conversations, conversation
from recap import ingest, search
from recaplib.session_workflow import import_export, titles


class ConversationViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        import_export(self.db, 'web', 'examples/web-export.json', 'web')

    def test_title_override_is_visible_without_rewriting_evidence(self):
        before = conversation(self.db, 'web', 'synthetic-chat')
        title = '합성 과수원 계획'
        change = titles(self.db, 'web', 'synthetic-chat', title, 0)
        after = conversation(self.db, 'web', 'synthetic-chat')
        self.assertEqual(after['display_title'], title)
        self.assertEqual(after['revision'], change['revision'])
        self.assertEqual(before['messages'], after['messages'])
        self.assertEqual(after['original_title'], 'New chat')
        self.assertEqual(search(self.db, 'orchard')[0]['title'], 'New chat')
        self.assertEqual(conversations(self.db)['conversations'][0]['display_title'], title)

    def test_provenance_and_parent_are_retained(self):
        result = conversation(self.db, 'web', 'synthetic-chat')
        self.assertEqual(result['message_count'], 2)
        expected = hashlib.sha256(Path('examples/web-export.json').read_bytes()).hexdigest()
        provenance = result['messages'][1]['export_provenance'][0]
        self.assertEqual(provenance, dict(original_sha256=expected, locator='mapping:m2', parent_id='m1'))
        self.assertIn('not an active-branch', result['branch_scope'])

    def test_normalized_archive_without_optional_tables(self):
        db = Path(self.tmp.name) / 'normalized.sqlite'
        ingest(db, 'normalized', 'examples/conversations.jsonl')
        listing = conversations(db)
        row = listing['conversations'][0]
        result = conversation(db, row['source'], row['conversation'])
        self.assertEqual(result['revision'], 0)
        self.assertTrue(all(m['export_provenance'] == [] for m in result['messages']))

    def test_source_isolation_pagination_and_no_mutation(self):
        import_export(self.db, 'another', 'examples/web-export.json', 'web')
        titles(self.db, 'web', 'synthetic-chat', 'Only web', 0)
        before = self.db.read_bytes()
        listing = conversations(self.db, limit=1)
        self.assertEqual(listing['total'], 2)
        self.assertEqual(listing['conversations'][0]['source'], 'another')
        self.assertEqual(listing['conversations'][0]['display_title'], 'New chat')
        self.assertEqual(conversations(self.db, offset=1)['conversations'][0]['display_title'], 'Only web')
        self.assertEqual(conversations(self.db, 'web')['total'], 1)
        self.assertEqual(conversations(self.db, "' OR 1=1 --")['total'], 0)
        self.assertEqual(conversations(self.db, offset=99)['conversations'], [])
        conversation(self.db, 'web', 'synthetic-chat')
        self.assertEqual(self.db.read_bytes(), before)

    def test_local_locator_and_deterministic_view(self):
        import_export(self.db, 'local', 'examples/local-session.jsonl', 'local')
        row = conversations(self.db, 'local')['conversations'][0]
        result = conversation(self.db, 'local', row['conversation'])
        self.assertEqual(result, conversation(self.db, 'local', row['conversation']))
        self.assertEqual(result['messages'][0]['export_provenance'][0]['locator'], 'line:2')

    def test_multiple_export_hashes_remain_visible(self):
        path = Path(self.tmp.name) / 'same-messages.json'
        path.write_text(json.dumps(json.loads(Path('examples/web-export.json').read_text())), encoding='utf-8')
        import_export(self.db, 'web', path, 'web')
        result = conversation(self.db, 'web', 'synthetic-chat')
        self.assertEqual(len(result['messages'][0]['export_provenance']), 2)

    def test_invalid_requests_and_missing_database(self):
        for options in ({'limit': 0}, {'limit': 1001}, {'offset': -1}, {'offset': 2**63}, {'limit': True}):
            with self.assertRaises(ValueError):
                conversations(self.db, **options)
        with self.assertRaises(ValueError):
            conversation(self.db, 'missing', 'synthetic-chat')
        missing = Path(self.tmp.name) / 'missing.sqlite'
        result = subprocess.run([sys.executable, 'conversation_view.py', '--db', str(missing), 'list'],
                                capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(missing.exists())

    def test_cli_list_and_show(self):
        for args in (['list', '--source', 'web'], ['show', '--source', 'web', '--conversation', 'synthetic-chat']):
            result = subprocess.run([sys.executable, 'conversation_view.py', '--db', str(self.db), *args],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['scope'], 'local archive only')

    def test_oversized_offset_cli_is_a_clean_failure(self):
        before = self.db.read_bytes()
        for script in ('recap.py', 'conversation_view.py'):
            result = subprocess.run([sys.executable, script, '--db', str(self.db), 'list', '--offset', str(2**63)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 1); self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(result.stdout, '')
        self.assertEqual(self.db.read_bytes(), before)
