"""Synthetic bridge from sampled search hits to existing raw pages and title review."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from conversation_search import find
from conversation_view import conversation
from local_parser import parse_jsonl_bytes
from session_workflow import import_export, titles
from title_proposal import apply_preview, preview
from title_suggestion import suggest


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'examples' / 'message-review-local.jsonl'
IDENTITY = 'synthetic-message-review'
TITLE = 'Compare cobalt orchard irrigation designs'
OPENING = 'Can you help with my project?'
QUERY = 'cobalt orchard'


class OmittedMessageReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='recap omitted messages ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    @staticmethod
    def evidence(db):
        with closing(sqlite3.connect(db)) as connection:
            return {table: connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                    for table in ('messages', 'artifacts', 'export_provenance', 'export_occurrences')}

    def cli(self, script, *args):
        result = subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, encoding='utf-8', timeout=30,
            env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.isascii())
        self.assertNotIn('Traceback', result.stderr)
        return json.loads(result.stdout)

    def assert_samples(self, result):
        self.assertEqual(result['total_matches'], 1)
        self.assertIsNone(result['next_cursor'])
        self.assertEqual(result['remaining_matches'], 0)
        self.assertFalse(result['truncated'])
        item, = result['matches']
        self.assertEqual(item['conversation_id'], IDENTITY)
        self.assertEqual(item['message_match_count'], 66)
        self.assertTrue(item['message_matches_truncated'])
        self.assertEqual([row['message_id'] for row in item['message_matches']],
                         ['status-00', 'status-01', 'status-02'])
        self.assertTrue(all(row['role'] == 'assistant' for row in item['message_matches']))
        self.assertTrue(item['message_term_coverage']['all_matched_terms_sampled'])
        self.assertNotIn('focus-user', [row['message_id'] for row in item['message_matches']])

    def test_fixture_has_one_later_user_after_sixty_five_assistant_hits(self):
        raw = FIXTURE.read_bytes()
        parsed = parse_jsonl_bytes(raw, FIXTURE.name, 'codex')
        self.assertEqual(parsed.observed_record_count, 68)
        self.assertEqual(len(parsed.messages), 67)
        self.assertEqual(len(parsed.sessions), 1)
        self.assertEqual(parsed.sessions[0].session_id, IDENTITY)
        self.assertEqual(parsed.messages[0].text, OPENING)
        self.assertEqual(parsed.messages[-1].message_key, 'focus-user')
        self.assertEqual(parsed.messages[-1].text, TITLE)
        self.assertEqual(sum(row.role == 'user' for row in parsed.messages), 2)
        self.assertEqual(sum(QUERY in row.text for row in parsed.messages), 66)
        self.assertEqual(FIXTURE.read_bytes(), raw)

    def test_web_and_local_pages_reach_unsampled_user_without_new_search_mode(self):
        local_raw = FIXTURE.read_bytes()
        records = [json.loads(line) for line in local_raw.splitlines()]
        mapping = {}
        parent = None
        for record in records[1:]:
            payload = record['payload']
            mapping[payload['id']] = dict(parent=parent, message=dict(author=dict(role=payload['role']),
                content=dict(content_type='text', parts=[payload['content'][0]['text']])))
            parent = payload['id']
        web = self.root / 'synthetic web.json'
        web.write_text(json.dumps([dict(id=IDENTITY, title='New chat', current_node='focus-user',
                                           mapping=mapping)]), encoding='utf-8')
        for kind, source_path in (('web', web), ('local-codex', FIXTURE)):
            with self.subTest(kind=kind):
                source_bytes = source_path.read_bytes()
                db = self.root / (kind + '.sqlite')
                imported = import_export(db, kind, source_path, kind)
                self.assertEqual(imported['inserted'], 67)
                before = db.read_bytes()
                raw_evidence = self.evidence(db)
                result = find(db, QUERY, source=kind)
                self.assert_samples(result)
                self.assert_samples(find(db, QUERY, source=kind, limit=1000))
                self.assertEqual(suggest(db, kind, IDENTITY)['title'], OPENING)
                with self.assertRaisesRegex(ValueError, 'user message'):
                    suggest(db, kind, IDENTITY, 'status-00')
                messages = []
                counts = []
                offsets = []
                offset = 0
                while offset is not None:
                    page = conversation(db, kind, IDENTITY, limit=20, offset=offset)
                    self.assertEqual(page['message_count'], 67)
                    self.assertEqual(page['selection']['mode'], 'page')
                    self.assertEqual(page['message_order'], 'archive insertion order')
                    self.assertIn('not an active-branch', page['branch_scope'])
                    messages.extend(page['messages'])
                    counts.append(len(page['messages']))
                    offset = page['selection']['next_offset']
                    offsets.append(offset)
                self.assertEqual(counts, [20, 20, 20, 7])
                self.assertEqual(offsets, [20, 40, 60, None])
                self.assertEqual([row['message_id'] for row in messages],
                    ['opening-user'] + [f'status-{i:02}' for i in range(65)] + ['focus-user'])
                self.assertEqual(messages[-1]['role'], 'user')
                self.assertEqual(messages[-1]['text'], TITLE)
                proposal = suggest(db, kind, IDENTITY, messages[-1]['message_id'])
                self.assertEqual(proposal['title'], TITLE)
                self.assertEqual(proposal['evidence_message_ids'], ['focus-user'])
                reviewed = preview(db, proposal, with_evidence=True)
                self.assertEqual(reviewed['expected_revision'], 0)
                self.assertEqual(db.read_bytes(), before)
                applied = apply_preview(db, reviewed)
                self.assertEqual(applied['display_title'], TITLE)
                self.assertGreater(applied['revision'], 0)
                self.assertEqual(find(db, QUERY, source=kind)['matches'][0]['matched_title'], True)
                self.assertEqual(self.evidence(db), raw_evidence)
                self.assertEqual(source_path.read_bytes(), source_bytes)
        self.assertEqual(FIXTURE.read_bytes(), local_raw)

    def test_exact_walkthrough_commands_require_separate_review_and_apply(self):
        document = (ROOT / 'docs' / 'OMITTED_SEARCH_MESSAGES.md').read_text(encoding='utf-8')
        commands = [shlex.split(line) for line in document.splitlines()
                    if line.startswith(('mkdir ', 'python '))]
        self.assertEqual(len(commands), 11)
        scratch = self.root / 'message review with spaces'
        db = scratch / 'archive.sqlite'
        source_bytes = FIXTURE.read_bytes()
        raw_evidence = before = None
        seen_ids = []
        page_sizes = []
        expected_offsets = [20, 40, 60, None]

        def substitute(token):
            if token.startswith('examples/'):
                return str(ROOT / token)
            prefix = '../recap-message-review-demo'
            if token == prefix or token.startswith(prefix + '/'):
                return str(scratch / token[len(prefix):].lstrip('/'))
            return token

        for number, tokens in enumerate(commands):
            if tokens[0] == 'mkdir':
                self.assertEqual(number, 0)
                Path(substitute(tokens[1])).mkdir()
                continue
            args = [substitute(token) for token in tokens[2:]]
            result = self.cli(tokens[1], *args)
            if number == 1:
                self.assertEqual(result['inserted'], 67)
                self.assertEqual(result['coverage']['original_sha256'], hashlib.sha256(source_bytes).hexdigest())
                before = db.read_bytes()
                raw_evidence = self.evidence(db)
            elif number == 2:
                self.assert_samples(result)
                self.assertFalse(result['matches'][0]['matched_title'])
            elif 3 <= number <= 6:
                self.assertEqual(result['message_count'], 67)
                page_sizes.append(len(result['messages']))
                seen_ids.extend(row['message_id'] for row in result['messages'])
                self.assertEqual(result['selection']['next_offset'], expected_offsets[number - 3])
                if number == 6:
                    self.assertEqual(result['messages'][-1]['message_id'], 'focus-user')
                    self.assertEqual(result['messages'][-1]['role'], 'user')
                    self.assertEqual(result['messages'][-1]['text'], TITLE)
            elif number in (7, 8):
                self.assertEqual(result['status'], 'SAVED')
                self.assertEqual(result['document_kind'], 'proposal' if number == 7 else 'preview')
                self.assertEqual(result['encoding'], 'UTF-8')
                self.assertTrue(result['staging_cleanup_complete'])
                raw = Path(args[args.index('--output') + 1]).read_bytes()
                self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
                self.assertEqual(result['bytes'], len(raw))
                self.assertEqual(result['sha256'], hashlib.sha256(raw).hexdigest())
                saved = json.loads(raw.decode('utf-8'))
                proposal = saved if number == 7 else saved['proposal']
                self.assertEqual(proposal['title'], TITLE)
                self.assertEqual(proposal['evidence_message_ids'], ['focus-user'])
                if number == 8:
                    self.assertEqual(saved['expected_revision'], 0)
                    self.assertEqual(saved['previous_title'], '')
                    self.assertIn('review_evidence', saved)
            elif number == 9:
                self.assertGreater(result['revision'], 0)
                self.assertEqual(result['display_title'], TITLE)
            elif number == 10:
                self.assert_samples(result)
                self.assertTrue(result['matches'][0]['matched_title'])
                self.assertEqual(result['matches'][0]['display_title'], TITLE)
            if 1 <= number <= 8:
                self.assertEqual(titles(db, 'demo', IDENTITY)['revision'], 0)
                self.assertEqual(db.read_bytes(), before)
            if number >= 1:
                self.assertEqual(self.evidence(db), raw_evidence)
            self.assertEqual(FIXTURE.read_bytes(), source_bytes)
        self.assertEqual(page_sizes, [20, 20, 20, 7])
        self.assertEqual(seen_ids, ['opening-user'] + [f'status-{i:02}' for i in range(65)] + ['focus-user'])

    def test_later_page_is_a_fresh_snapshot_not_a_cursor_content_lease(self):
        source = self.root / 'synthetic.jsonl'
        original = FIXTURE.read_bytes()
        source.write_bytes(original)
        db = self.root / 'archive.sqlite'
        import_export(db, 'demo', source, 'local-codex')
        first = conversation(db, 'demo', IDENTITY, limit=20)
        self.assertEqual(first['message_count'], 67)
        self.assertEqual(first['selection']['next_offset'], 20)
        extra = dict(type='response_item', payload=dict(type='message', id='later-import', role='assistant',
                     content=[dict(type='output_text', text='Synthetic later message')]))
        source.write_bytes(original + (json.dumps(extra) + '\n').encode('utf-8'))
        self.assertEqual(import_export(db, 'demo', source, 'local-codex')['inserted'], 1)
        later = conversation(db, 'demo', IDENTITY, limit=20, offset=60)
        self.assertEqual(later['message_count'], 68)
        self.assertEqual(len(later['messages']), 8)
        self.assertEqual(later['messages'][-1]['message_id'], 'later-import')
        self.assertIsNone(later['selection']['next_offset'])
        self.assertEqual(FIXTURE.read_bytes(), original)

    def test_guide_links_resolve_and_bridges_are_present(self):
        guide = ROOT / 'docs' / 'OMITTED_SEARCH_MESSAGES.md'
        text = guide.read_text(encoding='utf-8')
        links = re.findall(r'\]\(([^)]+)\)', text)
        self.assertTrue(links)
        for link in links:
            self.assertTrue((guide.parent / link.split('#')[0]).is_file(), link)
        for name in ('SEARCH_EXCERPTS.md', 'SEARCH_PAGINATION.md', 'TITLE_REVIEW_HINTS.md'):
            self.assertIn('(OMITTED_SEARCH_MESSAGES.md)', (ROOT / 'docs' / name).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
