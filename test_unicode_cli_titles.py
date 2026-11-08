"""Unicode title writes must not report failure after committing successfully."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from recap import ingest
from session_workflow import titles


class UnicodeCliTitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root / 'archive.sqlite'
        path = self.root / 'synthetic.jsonl'
        path.write_text(json.dumps(dict(conversation_id='synthetic', message_id='u', role='user',
            timestamp='synthetic', title='원래 제목 🌱', text='합성 과수원 계획 🌱'))+'\n')
        ingest(self.db, 'demo', path)

    def call(self, script, *args):
        result = subprocess.run([sys.executable, script, '--db', str(self.db), *args],
            env=dict(os.environ, PYTHONIOENCODING='ascii'), capture_output=True, text=True,
            encoding='ascii', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return json.loads(result.stdout)

    def check_title_write(self, script):
        result = self.call(script, 'title', '--source', 'demo', '--conversation', 'synthetic',
                           '--set', '검토한 제목 🌱', '--expected-revision', '0')
        self.assertEqual(result['display_title'], '검토한 제목 🌱')
        self.assertGreater(result['revision'], 0)
        self.assertEqual(titles(self.db, 'demo', 'synthetic')['revision'], result['revision'])
        before = self.db.read_bytes()
        current = self.call(script, 'title', '--source', 'demo', '--conversation', 'synthetic')
        self.assertEqual(current['display_title'], result['display_title'])
        self.assertEqual(current['revision'], result['revision'])
        self.assertEqual(self.db.read_bytes(), before)

    def test_unified_title_write_reports_success_after_commit(self):
        self.check_title_write('recap.py')

    def test_standalone_title_write_reports_success_after_commit(self):
        self.check_title_write('session_workflow.py')

    def test_both_suggestion_clis_preserve_unicode_without_writes(self):
        before = self.db.read_bytes()
        identity = ('--source', 'demo', '--conversation', 'synthetic')
        unified = self.call('recap.py', 'suggest-title', *identity)
        standalone = self.call('title_suggestion.py', *identity)
        self.assertEqual(unified, standalone)
        self.assertEqual(unified['title'], '합성 과수원 계획 🌱')
        self.assertEqual(self.db.read_bytes(), before)

    def test_listing_clis_preserve_unicode_without_writes(self):
        before = self.db.read_bytes()
        unified = self.call('recap.py', 'list')
        standalone = self.call('conversation_view.py', 'list')
        self.assertEqual(unified, standalone)
        self.assertEqual(unified['conversations'][0]['display_title'], '원래 제목 🌱')
        self.assertEqual(self.db.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
