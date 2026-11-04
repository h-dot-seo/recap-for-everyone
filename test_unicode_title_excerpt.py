"""Synthetic NFC greeting keys and join-control retention, not grapheme handling."""
import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from contextlib import closing
from pathlib import Path

from attributed_title import suggest_attributed
from branch_title import suggest_branch
from conversation_search import find
from recap import ingest
from replay_title import suggest_replay
from session_workflow import import_export, titles
from title_adapter import generate, prepare_request
from title_batch import review_queue
from title_excerpt import GREETINGS, excerpt
from title_proposal import apply_preview, content_fingerprint, preview, snapshot
from title_suggestion import suggest


KOREAN_GREETINGS = ('안녕', '안녕하세요', '반가워요', '감사합니다', '고마워요')


def nfd(text):
    return unicodedata.normalize('NFD', text)


def rows_for(*texts):
    return [dict(role='user', text=text, message_id=f'u-{index}')
            for index, text in enumerate(texts)]


class UnicodeExcerptUnitTests(unittest.TestCase):
    def test_all_korean_greetings_nfd_skip_to_nfc_or_nfd_request(self):
        self.assertEqual(set(KOREAN_GREETINGS), {g for g in GREETINGS if not g.isascii()})
        for greeting in KOREAN_GREETINGS:
            for request in ('합성 연구 계획', nfd('합성 연구 계획')):
                with self.subTest(greeting=greeting, request=request):
                    rows = rows_for(nfd(greeting) + '！？', request)
                    original = copy.deepcopy(rows)
                    result = excerpt(rows)
                    self.assertEqual(result['title'], request)
                    self.assertEqual(result['evidence_message_ids'], ['u-1'])
                    self.assertEqual(result['selection_method'], 'first_non_greeting_user_excerpt')
                    self.assertEqual(rows, original)

    def test_decomposed_greeting_fallback_preserves_label_and_first_identity(self):
        for greeting in KOREAN_GREETINGS:
            with self.subTest(greeting=greeting):
                text = nfd(greeting) + '!'
                result = excerpt(rows_for('👩\u200d🔬', '\t' + text + '\n', 'Hello!'))
                self.assertEqual(result['title'], text)
                self.assertEqual(result['evidence_message_ids'], ['u-1'])
                self.assertEqual(result['selection_method'], 'first_user_greeting_fallback')

    def test_no_compatibility_folding_lookalike_matching_or_new_punctuation(self):
        # Fullwidth Hello and mathematical bold hi fold under NFKC, not NFC.
        for text in ('Ｈｅｌｌｏ!', '𝐡𝐢', 'hеllo', '안녕하세요:', '안녕하세요…', '안녕하세요 부탁해요'):
            with self.subTest(text=text):
                result = excerpt(rows_for(text, 'Synthetic later request'))
                self.assertEqual(result['title'], text)
                self.assertEqual(result['evidence_message_ids'], ['u-0'])
                self.assertEqual(result['selection_method'], 'first_non_greeting_user_excerpt')
        self.assertEqual(excerpt(rows_for(' HeLLo！？ ', 'Synthetic next'))['title'], 'Synthetic next')

    def test_join_controls_preserved_other_controls_still_space_separated(self):
        text = '\x00Synthetic\u200b👩\u200d🔬\u202eمی\u200cروم\ufefffield\tstudy\n'
        self.assertEqual(excerpt(rows_for(text))['title'], 'Synthetic 👩\u200d🔬 می\u200cروم field study')
        for text in ('Synthetic 👩\u200d🔬 field study', 'Synthetic می\u200cروم study'):
            self.assertEqual(excerpt(rows_for(text))['title'], text)

    def test_emoji_or_join_controls_without_alphanumeric_evidence_still_rejected(self):
        for text in ('👩\u200d🔬', '\u200c\u200d', '!? 👩\u200d🔬', '\u0301'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'no usable user text'):
                excerpt(rows_for(text))

    def test_eighty_code_point_boundary_can_split_joined_or_combining_sequences(self):
        # These expectations intentionally document code-point, not cluster, slicing.
        for text in ('x' * 78 + '👩\u200d🔬', 'x' * 79 + 'e\u0301',
                     'x' * 79 + '\u200c' + 'z', 'x' * 79 + nfd('가')):
            with self.subTest(text=text):
                result = excerpt(rows_for(text))
                self.assertEqual(result['title'], text[:80])
                self.assertEqual(len(result['title']), 80)
                self.assertTrue(result['truncated'])
        text = 'x' * 79 + '\u200d'
        self.assertEqual(excerpt(rows_for(text))['title'], text)
        self.assertFalse(excerpt(rows_for(text))['truncated'])

    def test_non_alphanumeric_capped_labels_are_rejected_despite_later_letters(self):
        # Retained code points fill the cap; later letters do not rescue the label.
        for prefix in ('\u200d' * 80, '\u200c' * 80, '!' * 80,
                       '\u0301' * 80, '👩' * 80, ('👩\u200d🔬' * 27)):
            with self.subTest(prefix=prefix):
                text = prefix + 'Synthetic request'
                with self.assertRaisesRegex(ValueError, 'no usable user text'):
                    excerpt(rows_for(text))
                result = excerpt(rows_for(text, 'Synthetic later request'))
                self.assertEqual(result['title'], 'Synthetic later request')
                self.assertEqual(result['evidence_message_ids'], ['u-1'])
                self.assertFalse(result['truncated'])

    def test_last_included_code_point_can_qualify_but_first_excluded_cannot(self):
        for prefix_character in ('\u200d', '\u200c', '!', '\u0301', '👩'):
            with self.subTest(prefix_character=prefix_character):
                included = prefix_character * 79 + 'a'
                result = excerpt(rows_for(included))
                self.assertEqual(result['title'], included)
                self.assertEqual(result['evidence_message_ids'], ['u-0'])
                self.assertFalse(result['truncated'])
                with self.assertRaisesRegex(ValueError, 'no usable user text'):
                    excerpt(rows_for(prefix_character * 80 + 'a'))

    def test_cleaned_away_controls_do_not_consume_excerpt_capacity(self):
        for control in ('\x00', '\t', '\u200b', '\u202e', '\ufeff'):
            with self.subTest(control=control):
                result = excerpt(rows_for(control * 80 + 'Synthetic request'))
                self.assertEqual(result['title'], 'Synthetic request')
                self.assertEqual(result['evidence_message_ids'], ['u-0'])
                self.assertFalse(result['truncated'])

    def test_emoji_tag_format_characters_remain_outside_join_control_exception(self):
        text = 'Synthetic 🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f study'
        self.assertEqual(excerpt(rows_for(text))['title'], 'Synthetic 🏴 study')


class UnicodeExcerptWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'synthetic.sqlite'
        self.path = self.root / 'synthetic.jsonl'
        self.text = nfd('합성 연구') + ' 👩\u200d🔬 می\u200cروم'
        self.greeting = nfd('안녕하세요!')

    def seed_raw(self):
        records = [dict(row, conversation_id='synthetic', timestamp='synthetic', title='Original')
                   for row in rows_for(self.greeting, self.text)]
        self.path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
        ingest(self.db, 'demo', self.path)

    def assert_parity(self, extra_proposals=()):
        before = self.db.read_bytes(), self.path.read_bytes()
        rows, digest = snapshot(self.db, 'demo', 'synthetic')
        self.assertEqual([r['text'] for r in rows], [self.greeting, self.text])
        self.assertEqual(digest, content_fingerprint(rows))
        proposal = suggest(self.db, 'demo', 'synthetic')
        proposals = [proposal, review_queue(self.db, 'demo')['items'][0]['proposal'],
                     generate(prepare_request(self.db, 'demo', 'synthetic')), *extra_proposals]
        for candidate in proposals:
            self.assertEqual(candidate['title'], self.text)
            self.assertEqual(candidate['content_sha256'], digest)
            self.assertEqual(candidate['evidence_message_ids'], ['u-1'])
            reviewed = preview(self.db, candidate)
            self.assertIn('FORMAT_CHARACTERS_PRESENT', reviewed['title_advisory']['privacy_flags'])
            self.assertEqual(reviewed['semantic_validation'], 'NOT_PERFORMED')
        self.assertEqual(titles(self.db, 'demo', 'synthetic')['suggested_title'], self.text)
        self.assertEqual(snapshot(self.db, 'demo', 'synthetic'), (rows, digest))
        self.assertEqual(before, (self.db.read_bytes(), self.path.read_bytes()))
        return proposal

    def test_raw_queue_adapter_preview_and_storage_are_consistent_and_readonly(self):
        self.seed_raw()
        self.assert_parity()

    def test_explicit_review_apply_and_search_preserve_unicode_evidence(self):
        self.seed_raw()
        proposal = self.assert_parity()
        source_bytes = self.path.read_bytes()
        raw_snapshot = snapshot(self.db, 'demo', 'synthetic')
        reviewed = preview(self.db, proposal, with_evidence=True)
        self.assertEqual(reviewed['review_evidence']['messages'][0]['text_excerpt'], self.text)
        self.assertEqual(titles(self.db, 'demo', 'synthetic')['revision'], 0)
        result = apply_preview(self.db, reviewed)
        self.assertEqual(result['display_title'], self.text)
        self.assertGreater(result['revision'], 0)
        for query, canonical in [('👩\u200d🔬', False), ('합성 연구', True)]:
            match = find(self.db, query, 'demo', canonical_unicode=canonical)['matches'][0]
            self.assertEqual(match['display_title'], self.text)
            self.assertTrue(match['matched_title'])
        self.assertEqual(snapshot(self.db, 'demo', 'synthetic'), raw_snapshot)
        self.assertEqual(self.path.read_bytes(), source_bytes)
        with self.assertRaisesRegex(ValueError, 'stale title preview'):
            apply_preview(self.db, reviewed)

    def test_original_decomposed_content_fingerprint_still_detects_canonical_change(self):
        self.seed_raw()
        proposal = self.assert_parity()
        reviewed = preview(self.db, proposal)
        original = self.path.read_bytes()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('UPDATE messages SET text=? WHERE message_id=?',
                               (unicodedata.normalize('NFC', self.text), 'u-1'))
        self.assertNotEqual(snapshot(self.db, 'demo', 'synthetic')[1], proposal['content_sha256'])
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            preview(self.db, proposal)
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            apply_preview(self.db, reviewed)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(titles(self.db, 'demo', 'synthetic')['revision'], 0)

    def test_web_import_branch_preserves_original_bytes_and_identity(self):
        mapping = {f'u-{index}': dict(parent=None if index == 0 else 'u-0',
                   message=dict(author=dict(role='user'), content=dict(parts=[text])))
                   for index, text in enumerate((self.greeting, self.text))}
        self.path.write_text(json.dumps([dict(id='synthetic', title='Original', current_node='u-1',
                                             mapping=mapping)], ensure_ascii=False), encoding='utf-8')
        original = self.path.read_bytes()
        import_export(self.db, 'demo', self.path, 'web')
        branch = suggest_branch(self.db, 'demo', 'synthetic', self.path)
        self.assert_parity([branch])
        self.assertEqual(branch['branch_context']['original_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.path.read_bytes(), original)

    def seed_local(self, attributed=False):
        records = [dict(type='session_meta', payload=dict(id='synthetic'))]
        for index, text in enumerate((self.greeting, self.text)):
            records.extend([
                dict(type='event_msg', payload=dict(type='task_started', turn_id=f't-{index}')),
                dict(type='event_msg', payload=dict(type='user_message', message=text)),
                dict(type='response_item', payload=dict(type='message', role='user', id=f'u-{index}',
                     content=[dict(type='input_text', text=text)],
                     internal_chat_message_metadata_passthrough=dict(content_item_metadata=[
                         dict(provenance=dict(type='user'))]))),
                dict(type='event_msg', payload=dict(type='task_complete', turn_id=f't-{index}'))])
        # Retained-turn replay deliberately does not support attribution metadata.
        if not attributed:
            for record in records:
                if record['type'] == 'response_item':
                    record['payload'].pop('internal_chat_message_metadata_passthrough')
        self.path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
        import_export(self.db, 'demo', self.path, 'local-codex')

    def test_local_import_replay_shares_unicode_contract(self):
        self.seed_local()
        original = self.path.read_bytes()
        proposal = suggest_replay(self.db, 'demo', 'synthetic', self.path)
        self.assert_parity([proposal])
        self.assertEqual(proposal['projection_context']['original_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.path.read_bytes(), original)

    def test_local_import_attribution_shares_unicode_contract(self):
        self.seed_local(attributed=True)
        original = self.path.read_bytes()
        proposal = suggest_attributed(self.db, 'demo', 'synthetic', self.path)
        self.assert_parity([proposal])
        self.assertEqual(proposal['attribution_context']['original_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.path.read_bytes(), original)

    def test_ascii_cli_title_suggestion_and_queue_parity_without_mutation(self):
        self.seed_raw()
        before = self.db.read_bytes(), self.path.read_bytes()
        identity = ['--source', 'demo', '--conversation', 'synthetic']
        commands = [('recap.py', ['title', *identity], 'suggested_title'),
                    ('session_workflow.py', ['title', *identity], 'suggested_title'),
                    ('recap.py', ['suggest-title', *identity], 'title'),
                    ('title_suggestion.py', identity, 'title'),
                    ('recap.py', ['review-titles', '--source', 'demo'], None)]
        for script, args, key in commands:
            with self.subTest(script=script, command=args[0]):
                result = subprocess.run([sys.executable, script, '--db', str(self.db), *args],
                                        capture_output=True, timeout=20,
                                        env=dict(os.environ, PYTHONIOENCODING='ascii'))
                self.assertEqual(result.returncode, 0, result.stderr)
                document = json.loads(result.stdout.decode('ascii'))
                value = document[key] if key else document['items'][0]['proposal']['title']
                self.assertEqual(value, self.text)
        self.assertEqual(before, (self.db.read_bytes(), self.path.read_bytes()))


if __name__ == '__main__':
    unittest.main()
