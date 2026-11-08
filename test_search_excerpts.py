"""Synthetic, source-faithful excerpts for late and Unicode search matches."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from conversation_search import find
from recap import ingest
from session_workflow import import_export, titles


class SearchExcerptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'synthetic.sqlite'

    def load(self, text, title='Synthetic title'):
        path = self.root / 'messages.jsonl'
        path.write_text(json.dumps(dict(conversation_id='synthetic', message_id='u',
            role='user', timestamp='synthetic', title=title, text=text)) + '\n', encoding='utf-8')
        ingest(self.db, 'demo', path)

    def hit(self, query):
        return find(self.db, query)['matches'][0]['message_matches'][0]

    def assert_slice(self, text, hit):
        self.assertEqual(hit['snippet'], text[hit['snippet_start']:hit['snippet_end']])
        self.assertLessEqual(len(hit['snippet']), 240)
        self.assertEqual(hit['snippet_truncated_before'], hit['snippet_start'] > 0)
        self.assertEqual(hit['snippet_truncated_after'], hit['snippet_end'] < len(text))

    def test_late_match_is_visible_with_exact_source_offsets_and_no_mutation(self):
        text = ('Synthetic background. ' * 80) + 'TargetNEEDLE\n  original spacing\t' + 'tail ' * 80
        self.load(text)
        before = self.db.read_bytes()
        hit = self.hit('targetneedle')
        self.assert_slice(text, hit)
        self.assertIn('TargetNEEDLE', hit['snippet'])
        start = text.index('TargetNEEDLE')
        self.assertEqual(hit['first_match'], dict(term='targetneedle', start=start,
                                                end=start + 12, fully_visible=True))
        self.assertTrue(hit['snippet_truncated_before'])
        self.assertTrue(hit['snippet_truncated_after'])
        self.assertEqual(self.db.read_bytes(), before)

    def test_first_source_match_wins_over_query_order(self):
        text = 'Earlyneedle ' + 'padding ' * 80 + 'Lateneedle'
        self.load(text)
        hit = self.hit('lateneedle earlyneedle')
        self.assertEqual(hit['first_match']['term'], 'earlyneedle')
        self.assertEqual(hit['snippet_start'], 0)
        self.assert_slice(text, hit)

    def test_casefold_expansion_before_and_inside_match_keeps_original_offsets(self):
        text = 'ß' * 300 + ' Straße response'
        self.load(text)
        hit = self.hit('STRASSE')
        self.assert_slice(text, hit)
        self.assertIn('Straße', hit['snippet'])
        self.assertEqual(hit['first_match'], dict(term='strasse', start=301, end=307, fully_visible=True))

    def test_partial_casefold_expansion_maps_to_whole_original_character(self):
        self.load('İß')
        hit = self.hit('s')
        self.assertEqual(hit['first_match'], dict(term='s', start=1, end=2, fully_visible=True))
        self.assertEqual(hit['snippet'], 'İß')

    def test_korean_and_non_bmp_characters_use_codepoint_offsets(self):
        text = '🌱' * 300 + ' 기전 연구 계획'
        self.load(text)
        hit = self.hit('기전')
        self.assert_slice(text, hit)
        self.assertEqual(hit['first_match']['start'], 301)
        self.assertEqual(hit['first_match']['end'], 303)
        self.assertIn('기전', hit['snippet'])

    def test_long_term_is_bounded_and_explicitly_marked_partial(self):
        term = 'n' * 300
        text = 'padding ' * 100 + term
        self.load(text)
        hit = self.hit(term)
        self.assert_slice(text, hit)
        self.assertEqual(hit['snippet'], 'n' * 240)
        self.assertFalse(hit['first_match']['fully_visible'])
        self.assertEqual(hit['first_match']['end'] - hit['first_match']['start'], 300)

    def test_both_clis_emit_unicode_evidence_on_ascii_stdout(self):
        self.load('Synthetic 기전 🌱 evidence', title='기전 계획')
        expected = find(self.db, '기전')
        for script, args in [('recap.py', ['find']), ('conversation_search.py', [])]:
            result = subprocess.run([sys.executable, script, '--db', str(self.db),
                *args, '기전'], capture_output=True, text=True, encoding='ascii',
                env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)

    def test_title_only_match_has_no_invented_message_evidence(self):
        self.load('Unrelated message', title='Oldtitle')
        changed = titles(self.db, 'demo', 'synthetic', 'Currentneedle', 0)
        current = find(self.db, 'currentneedle')['matches'][0]
        self.assertTrue(current['matched_title'])
        self.assertEqual(current['message_matches'], [])
        titles(self.db, 'demo', 'synthetic', 'Different title', changed['revision'])
        historical = find(self.db, 'currentneedle', include_title_history=True)['matches'][0]
        self.assertTrue(historical['matched_historical_title'])
        self.assertEqual(historical['message_matches'], [])

    def test_web_and_local_sources_keep_provenance_and_cli_equivalence(self):
        text = 'padding ' * 100 + 'Syntheticneedle'
        web = self.root / 'web.json'
        web.write_text(json.dumps([dict(id='web', mapping={'u': dict(message=dict(
            author=dict(role='user'), content=dict(parts=[text])))})]), encoding='utf-8')
        local = self.root / 'local.jsonl'
        local.write_text('\n'.join(json.dumps(record) for record in [
            dict(type='session_meta', payload=dict(id='local')),
            dict(type='response_item', payload=dict(type='message', id='u', role='user',
                 content=[dict(type='input_text', text=text)]))]) + '\n', encoding='utf-8')
        for path, kind in ((web, 'web'), (local, 'local-codex')):
            receipt = import_export(self.db, 'demo', path, kind)
            digest = receipt['coverage']['original_sha256']
            options = ['--export-sha256', digest]
            expected = find(self.db, 'syntheticneedle', export_sha256=digest)
            hit = expected['matches'][0]['message_matches'][0]
            self.assert_slice(text, hit)
            self.assertEqual(hit['export_provenance'][0]['original_sha256'], digest)
            for script, args in [('recap.py', ['find']), ('conversation_search.py', [])]:
                result = subprocess.run([sys.executable, script, '--db', str(self.db),
                    *args, 'syntheticneedle', *options], capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), expected)


if __name__ == '__main__':
    unittest.main()
