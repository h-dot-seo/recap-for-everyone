import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class UnifiedCliTests(unittest.TestCase):
    def call(self, *args, script='recap.py', success=True):
        result = subprocess.run([sys.executable, script, *map(str, args)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        if success:
            return json.loads(result.stdout)
        self.assertNotIn('Traceback', result.stderr)
        return result.stderr

    def test_import_browse_suggest_and_checked_title_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'archive.sqlite'
            prefix = ('--db', db)
            receipt = self.call(*prefix, 'import', 'examples/web-export.json', '--format', 'web', '--source', 'demo')
            self.assertEqual(receipt['inserted'], 2)
            self.assertEqual(self.call(*prefix, 'stats')['messages'], 2)
            self.assertEqual(self.call(*prefix, 'list')['conversations'][0]['display_title'], 'New chat')
            identity = ('--source', 'demo', '--conversation', 'synthetic-chat')
            detail = self.call(*prefix, 'show', *identity)
            self.assertEqual(detail['messages'][1]['export_provenance'][0]['parent_id'], 'm1')
            self.assertEqual(self.call(*prefix, 'suggest-title', *identity)['provider'], 'local-extractive')
            self.assertEqual(self.call(*prefix, 'title', *identity)['revision'], 0)
            self.call(*prefix, 'title', *identity, '--set', 'Reviewed orchard', success=False)
            changed = self.call(*prefix, 'title', *identity, '--set', 'Reviewed orchard', '--expected-revision', 0)
            self.assertGreater(changed['revision'], 0)
            self.assertEqual(self.call(*prefix, 'find', 'reviewed')['total_matches'], 1)
            self.assertEqual(self.call(*prefix, 'search', 'orchard')[0]['title'], 'New chat')
            self.call(*prefix, 'title', *identity, '--set', 'Stale label', '--expected-revision', 0, success=False)

    def test_standalone_read_commands_remain_equivalent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'archive.sqlite'
            prefix = ('--db', db)
            self.call(*prefix, 'import', 'examples/web-export.json', '--format', 'web', '--source', 'demo')
            identity = ('--source', 'demo', '--conversation', 'synthetic-chat')
            self.assertEqual(self.call(*prefix, 'show', *identity),
                             self.call(*prefix, 'show', *identity, script='conversation_view.py'))
            self.assertEqual(self.call(*prefix, 'find', 'orchard'),
                             self.call(*prefix, 'orchard', script='conversation_search.py'))
            self.assertEqual(self.call(*prefix, 'suggest-title', *identity),
                             self.call(*prefix, *identity, script='title_suggestion.py'))

    def test_inspect_works_without_db_and_other_commands_require_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'missing.sqlite'
            report = self.call('--db', db, 'inspect', 'examples/local-session.jsonl', '--format', 'local')
            self.assertEqual(report['extracted_messages'], 1)
            self.assertFalse(db.exists())
            self.assertEqual(report, self.call('inspect', 'examples/local-session.jsonl', '--format', 'local'))
            self.assertIn('--db is required', self.call('list', success=False))
            self.call('--db', db, 'list', success=False)
            self.assertFalse(db.exists())

    def test_legacy_normalized_ingest_is_still_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'archive.sqlite'
            result = self.call('--db', db, 'ingest', 'examples/conversations.jsonl', '--source', 'legacy')
            self.assertGreater(result['inserted'], 0)
            self.assertTrue(self.call('--db', db, 'search', 'orchard'))
