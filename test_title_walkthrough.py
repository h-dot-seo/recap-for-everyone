"""Synthetic two-format entry flow and review/apply failure boundaries."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TitleWalkthroughTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.saved = Path(self.tmp.name) / 'document.json'

    def call(self, *args, script='recap.py', ok=True, ascii_output=False):
        env = dict(os.environ)
        if ascii_output: env['PYTHONIOENCODING'] = 'ascii'
        result = subprocess.run([sys.executable, script, *map(str, args)],
                                capture_output=True, text=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return json.loads(result.stdout) if ok else result

    def save(self, value):
        self.saved.write_text(json.dumps(value), encoding='utf-8')
        return self.saved

    def test_two_format_walkthrough_and_stale_repeat(self):
        cases = [('web', 'examples/web-export.json', 'synthetic-chat', 'suggest-branch-title',
                  ['--node', 'm2'], 'Design a synthetic orchard experiment', 'orchard'),
                 ('local-codex', 'examples/rollback-session.jsonl', 'synthetic-rollout', 'suggest-replay-title',
                  [], 'Synthetic question retained', 'discarded')]
        for kind, path, conversation, command, extra, title, query in cases:
            with self.subTest(kind=kind):
                original = Path(path).read_bytes()
                self.call('inspect', path, '--format', kind)
                if kind == 'local-codex':
                    projection = self.call('replay-local', path)
                    self.assertTrue(projection['supported']); self.assertEqual(projection['rolled_back_turns'], 1)
                else:
                    self.call('web-branch', path, '--conversation', conversation, *extra)
                self.call('--db', self.db, 'import', path, '--format', kind, '--source', kind)
                before = self.db.read_bytes()
                proposal = self.call('--db', self.db, command, path, '--source', kind, '--conversation', conversation, *extra)
                self.assertEqual(proposal['title'], title)
                reviewed = self.call('--db', self.db, 'preview-title', self.save(proposal))
                self.assertEqual(reviewed, self.call('--db', self.db, 'preview', self.saved, script='title_proposal.py'))
                self.assertEqual(reviewed['expected_revision'], 0); self.assertEqual(before, self.db.read_bytes())
                self.call('--db', self.db, 'apply-title', self.save(reviewed))
                self.assertEqual(self.call('--db', self.db, 'list', '--source', kind)['conversations'][0]['display_title'], title)
                self.assertEqual(self.call('--db', self.db, 'find', query, '--source', kind)['total_matches'], 1)
                after = self.db.read_bytes()
                self.call('--db', self.db, 'apply-title', self.saved, ok=False)
                self.assertEqual(after, self.db.read_bytes()); self.assertEqual(original, Path(path).read_bytes())

    def test_wrong_documents_and_duplicate_keys_are_clean_failures(self):
        self.call('--db', self.db, 'import', 'examples/web-export.json', '--format', 'web', '--source', 'web')
        before = self.db.read_bytes()
        for command in ('preview-title', 'apply-title'):
            for value in (None, [], 3, 'PRIVATE sentinel', {}, {'proposal': [], 'expected_revision': 0}):
                result = self.call('--db', self.db, command, self.save(value), ok=False)
                self.assertNotIn('PRIVATE sentinel', result.stderr)
            self.saved.write_text('{"title":"x","title":"y"}', encoding='utf-8')
            self.call('--db', self.db, command, self.saved, ok=False)
        self.assertEqual(before, self.db.read_bytes())

    def test_missing_database_not_created(self):
        proposal = dict(source='web', conversation='synthetic-chat', title='Synthetic title',
                        content_sha256='0'*64, evidence_message_ids=['m1'], provider='operator')
        for command, document in (('preview-title', proposal),
                                  ('apply-title', dict(proposal=proposal, expected_revision=0))):
            self.call('--db', self.db, command, self.save(document), ok=False)
        self.assertFalse(self.db.exists())

    def test_ascii_stdout_and_standalone_equivalence(self):
        self.call('--db', self.db, 'import', 'examples/web-export.json', '--format', 'web', '--source', 'web')
        proposal = self.call('--db', self.db, 'suggest-title', '--source', 'web', '--conversation', 'synthetic-chat')
        proposal['title'] = '합성 제목'
        reviewed = self.call('--db', self.db, 'preview-title', self.save(proposal), ascii_output=True)
        self.assertEqual(reviewed, self.call('--db', self.db, 'preview', self.saved, script='title_proposal.py', ascii_output=True))
        applied = self.call('--db', self.db, 'apply-title', self.save(reviewed), ascii_output=True)
        self.assertEqual(applied['display_title'], proposal['title'])
