import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from recap import ingest
from session_workflow import titles
from title_proposal import preview, apply_preview
from title_suggestion import suggest


class LocalSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.path = Path(self.tmp.name) / 'synthetic.jsonl'

    def load(self, messages):
        rows = [dict(conversation_id='synthetic', message_id=str(i), role=role,
                     timestamp='synthetic', title='New chat', text=text)
                for i, (role, text) in enumerate(messages)]
        self.path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        ingest(self.db, 'demo', self.path)

    def test_greeting_skipped_and_evidence_bound_before_review(self):
        self.load([('user', 'Hello!'), ('assistant', 'Synthetic response'),
                   ('user', 'Plan a synthetic orchard experiment')])
        before = self.db.read_bytes()
        proposal = suggest(self.db, 'demo', 'synthetic')
        self.assertEqual(proposal['title'], 'Plan a synthetic orchard experiment')
        self.assertEqual(proposal['evidence_message_ids'], ['2'])
        self.assertEqual(proposal['provider'], 'local-extractive')
        self.assertEqual(proposal, suggest(self.db, 'demo', 'synthetic'))
        self.assertEqual(self.db.read_bytes(), before)
        reviewed = preview(self.db, proposal)
        self.assertEqual(titles(self.db, 'demo', 'synthetic')['display_title'], 'New chat')
        self.assertEqual(apply_preview(self.db, reviewed)['display_title'], proposal['title'])

    def test_korean_greeting_controls_and_long_excerpt(self):
        self.load([('user', '안녕하세요!'), ('user', '합성\n\t과수원\x00 계획\u202e ' + '검토 ' * 60)])
        proposal = suggest(self.db, 'demo', 'synthetic')
        self.assertTrue(proposal['title'].startswith('합성 과수원 계획'))
        self.assertLessEqual(len(proposal['title']), 80)
        self.assertTrue(proposal['truncated'])
        self.assertNotIn('\u202e', proposal['title'])
        self.assertEqual(proposal['evidence_message_ids'], ['1'])
        preview(self.db, proposal)

    def test_greeting_fallback_is_explicit(self):
        self.load([('user', 'Hi!'), ('user', 'Thanks')])
        proposal = suggest(self.db, 'demo', 'synthetic')
        self.assertEqual(proposal['title'], 'Hi!')
        self.assertEqual(proposal['selection_method'], 'first_user_greeting_fallback')

    def test_no_user_evidence_and_missing_conversation(self):
        self.load([('assistant', 'Only synthetic assistant content'), ('user', '\n\x00?!')])
        with self.assertRaises(ValueError):
            suggest(self.db, 'demo', 'synthetic')
        with self.assertRaises(ValueError):
            suggest(self.db, 'other', 'synthetic')

    def test_changed_content_rejects_generated_proposal(self):
        messages = [('user', 'Synthetic orchard plan')]
        self.load(messages)
        proposal = suggest(self.db, 'demo', 'synthetic')
        self.load(messages + [('user', 'Additional synthetic constraint')])
        with self.assertRaises(ValueError):
            preview(self.db, proposal)

    def test_cli_generates_proposal_without_renaming(self):
        self.load([('user', 'Synthetic orchard plan')])
        result = subprocess.run([sys.executable, 'title_suggestion.py', '--db', str(self.db),
                                 '--source', 'demo', '--conversation', 'synthetic'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['provider'], 'local-extractive')
        self.assertEqual(titles(self.db, 'demo', 'synthetic')['revision'], 0)
