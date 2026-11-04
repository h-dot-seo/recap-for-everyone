"""Synthetic canonical Unicode search and source-offset regressions; no network."""
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import tracemalloc
import unicodedata as ud
import unittest
from pathlib import Path
from unittest.mock import patch

from conversation_search import find
from recap import ingest
from session_workflow import titles, import_export
from conversation_view import conversation
from title_proposal import snapshot, preview, apply_preview
from unicode_search import canonical_fold, canonical_span, _canonical_items


def reference(text):
    return ud.normalize('NFC', ud.normalize('NFD', text).casefold())


class CanonicalMappingTests(unittest.TestCase):
    def check_mapping(self, text):
        items = list(_canonical_items(text))
        self.assertEqual(''.join(item[0] for item in items), reference(text), repr(text))
        self.assertEqual(canonical_fold(text), reference(text))
        for character, start, end in items:
            self.assertEqual(len(character), 1)
            self.assertTrue(0 <= start < end <= len(text), (repr(text), character, start, end))
        if items:
            self.assertEqual(canonical_span(text, 0, len(items)),
                             (min(item[1] for item in items), max(item[2] for item in items)))
        return items

    def test_standard_transform_and_reordering_before_casefold(self):
        for text in ('', '기전', ud.normalize('NFD', '기전'), 'café', 'cafe\u0301',
                     '\u0345\u0300', 'α\u0345\u0300', 'α\u0300\u0345',
                     'a\u0315\u0300', '\u0315\u0300', 'Straße', 'İ',
                     'ﬃ Ａ Ⓐ', '\u1100\u1161\u11a8', '각', '\u212b', '🌱𐐀'):
            with self.subTest(text=repr(text)):
                self.check_mapping(text)
        self.assertEqual(canonical_fold('α\u0345\u0300'), canonical_fold('α\u0300\u0345'))

    def test_known_exact_source_spans_and_reordered_cover(self):
        for text, folded, spans in [
            ('e\u0301', 'é', [(0, 2)]),
            ('\u1100\u1161\u11a8', '각', [(0, 3)]),
            ('ß', 'ss', [(0, 1), (0, 1)]),
            ('a\u0315\u0300', 'à\u0315', [(0, 3), (1, 2)]),
            ('\u0315\u0300', '\u0300\u0315', [(1, 2), (0, 1)]),
        ]:
            with self.subTest(text=repr(text)):
                self.assertEqual(canonical_fold(text), folded)
                self.assertEqual([(a, b) for _, a, b in self.check_mapping(text)], spans)
                for index, span in enumerate(spans):
                    self.assertEqual(canonical_span(text, index, index + 1), span)

    def test_late_span_does_not_allocate_a_full_character_map(self):
        # Construct the source before tracing. A retained per-character mapping
        # of 100,000 items costs several MiB; the streaming implementation only
        # needs a short pending normalization sequence and generator state.
        text = '기' * 100000 + 'e\u0301'
        tracemalloc.start()
        try:
            result = canonical_span(text, 100000, 100001)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(result, (100000, 100002))
        self.assertLess(peak, 512 * 1024)

    def test_invalid_or_out_of_range_spans(self):
        for start, end in [(-1, 1), (0, 0), (1, 0), (True, 2), (0, False), (0, 9), (5, 6)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                canonical_span('e\u0301', start, end)

    def test_seeded_random_transform_and_span_equivalence(self):
        rng = random.Random(470018)
        alphabet = list('abcABCßİéÅﬃ가각힣🌱') + [chr(x) for x in range(0x300, 0x370)] + [
            chr(x) for x in range(0x1100, 0x1113)] + ['\u1161', '\u1162', '\u11a8', '\u1f88', '\u1fbc']
        for _ in range(1000):
            text = ''.join(rng.choice(alphabet) for _ in range(rng.randrange(1, 25)))
            items = self.check_mapping(text)
            start = rng.randrange(len(items)); end = rng.randrange(start + 1, len(items) + 1)
            self.assertEqual(canonical_span(text, start, end),
                (min(item[1] for item in items[start:end]), max(item[2] for item in items[start:end])))


class CanonicalSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root / 'archive.sqlite'; self.serial = 0

    def seed(self, cid, text, title='Synthetic title', digest=None, source='demo'):
        self.serial += 1
        path = self.root / f'input-{self.serial}.jsonl'
        row = dict(conversation_id=cid, message_id=f'u-{self.serial}', role='user',
                   timestamp='synthetic', title=title, text=text)
        path.write_text(json.dumps(row) + '\n', encoding='utf-8')
        provenance = None if digest is None else [dict(**row, origin_sha256=digest,
            origin_locator=f'synthetic:{self.serial}', parent_id=None)]
        ingest(self.db, source, path, provenance=provenance)

    def test_both_directions_default_unchanged_and_source_offsets(self):
        for index, phrase in enumerate(('기전', 'café')):
            nfd = ud.normalize('NFD', phrase)
            for label, text, query in [('nfd', nfd, phrase), ('nfc', phrase, nfd)]:
                source = f'{index}-{label}'; original = '🌱' * 300 + ' ' + text + ' tail'
                self.seed(source, original, source=source)
                self.assertEqual(find(self.db, query, source=source)['total_matches'], 0)
                before = self.db.read_bytes()
                result = find(self.db, query, source=source, canonical_unicode=True)
                self.assertEqual(result['total_matches'], 1)
                hit = result['matches'][0]['message_matches'][0]
                self.assertEqual(hit['snippet'], original[hit['snippet_start']:hit['snippet_end']])
                self.assertLessEqual(len(hit['snippet']), 240)
                self.assertEqual(hit['first_match']['start'], 301)
                self.assertEqual(hit['first_match']['end'], 301 + len(text))
                self.assertTrue(hit['first_match']['fully_visible'])
                self.assertEqual(before, self.db.read_bytes())

    def test_reordered_composition_cover_can_exceed_excerpt(self):
        text = 'a' + '\u0315' * 300 + '\u0300'
        self.seed('long-cover', text)
        hit = find(self.db, 'à', canonical_unicode=True)['matches'][0]['message_matches'][0]
        self.assertEqual(hit['first_match']['start'], 0)
        self.assertEqual(hit['first_match']['end'], len(text))
        self.assertFalse(hit['first_match']['fully_visible'])
        self.assertEqual(hit['snippet'], text[:240])

    def test_no_accent_stripping_or_compatibility_normalization(self):
        self.seed('accent', 'café Ｚ Ⓩ ﬃ Straße')
        for query in ('cafe', 'z'):
            self.assertEqual(find(self.db, query, canonical_unicode=True)['total_matches'], 0)
        for query in ('ffi', 'STRASSE', 'cafe\u0301'):
            self.assertEqual(find(self.db, query, canonical_unicode=True)['total_matches'], 1)

    def test_title_history_body_source_and_export_filter(self):
        word = ud.normalize('NFD', '기전')
        self.seed('current', 'Other', title=word, digest='a' * 64)
        self.seed('history', 'Other', title=word, digest='a' * 64)
        titles(self.db, 'demo', 'history', 'Renamed', 0)
        self.seed('body', word, digest='b' * 64)
        self.seed('outside', word, source='other', digest='a' * 64)
        result = find(self.db, '기전', source='demo', include_title_history=True, canonical_unicode=True)
        self.assertEqual([x['conversation_id'] for x in result['matches']], ['current', 'history', 'body'])
        self.assertEqual(result['matches'][1]['historical_title_matches'][0]['title'], word)
        filtered = find(self.db, '기전', source='demo', include_title_history=True,
                        export_sha256='a' * 64, canonical_unicode=True)
        self.assertEqual([x['conversation_id'] for x in filtered['matches']], ['current', 'history'])
        self.assertEqual(find(self.db, '기전', source='demo', canonical_unicode=True)['total_matches'], 2)

    def test_cursor_equivalent_query_and_mode_binding(self):
        for index in range(3): self.seed(str(index), 'café')
        first = find(self.db, 'café', limit=1, canonical_unicode=True)
        token = first['next_cursor']; self.assertIsNotNone(token)
        second = find(self.db, 'cafe\u0301', limit=1, cursor=token, canonical_unicode=True)
        self.assertEqual(second['skipped_matches'], 1)
        with patch('conversation_search.readonly', side_effect=AssertionError('database opened')):
            with self.assertRaises(ValueError): find(self.db, 'café', cursor=token)
        with patch('conversation_search.unicodedata.unidata_version', 'synthetic-future'):
            with self.assertRaises(ValueError):
                find(self.db, 'café', cursor=token, canonical_unicode=True)
        default = find(self.db, 'café', limit=1)
        with self.assertRaises(ValueError):
            find(self.db, 'café', cursor=default['next_cursor'], canonical_unicode=True)

    def test_invalid_boolean_before_database_open(self):
        with patch('conversation_search.readonly', side_effect=AssertionError('database opened')):
            for invalid in (1, 0, None, 'true', [], {}):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    find(self.db, 'query', canonical_unicode=invalid)

    def test_import_find_show_review_apply_and_historical_lookup(self):
        text = '🌱' * 280 + ' ' + ud.normalize('NFD', '기전 café')
        for kind in ('web', 'local-codex'):
            with self.subTest(kind=kind):
                cid = 'synthetic-' + kind
                path = self.root / (kind + '.json')
                if kind == 'web':
                    value = [dict(id=cid, title='Synthetic original', mapping={
                        'u': dict(parent=None, message=dict(author=dict(role='user'),
                            content=dict(parts=[text])))})]
                    path.write_text(json.dumps(value), encoding='utf-8')
                else:
                    value = [dict(type='session_meta', payload=dict(id=cid)),
                        dict(type='response_item', payload=dict(type='message', id='u',
                            role='user', content=[dict(type='input_text', text=text)]))]
                    path.write_text(''.join(json.dumps(v) + '\n' for v in value), encoding='utf-8')
                original = path.read_bytes(); digest = hashlib.sha256(original).hexdigest()
                import_export(self.db, kind, path, kind)
                before = self.db.read_bytes()
                result = find(self.db, '기전 café', source=kind,
                              export_sha256=digest, canonical_unicode=True)
                hit = result['matches'][0]['message_matches'][0]
                shown = conversation(self.db, kind, cid, message_id=hit['message_id'])['messages'][0]
                self.assertEqual(shown['text'], text)
                self.assertEqual(hit['snippet'], shown['text'][hit['snippet_start']:hit['snippet_end']])
                self.assertEqual(text[hit['first_match']['start']:hit['first_match']['end']],
                                 ud.normalize('NFD', '기전'))
                self.assertEqual(shown['export_provenance'][0]['original_sha256'], digest)
                self.assertEqual(hit['export_provenance'][0]['original_sha256'], digest)
                self.assertEqual(self.db.read_bytes(), before)
                _, fingerprint = snapshot(self.db, kind, cid)
                proposal = dict(source=kind, conversation=cid, content_sha256=fingerprint,
                    title=ud.normalize('NFD', '검토 계획'), provider='operator', evidence_message_ids=['u'])
                reviewed = preview(self.db, proposal)
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(apply_preview(self.db, reviewed)['display_title'], proposal['title'])
                self.assertEqual(find(self.db, '검토', source=kind, canonical_unicode=True)['total_matches'], 1)
                replacement = dict(proposal, title='Final synthetic title')
                apply_preview(self.db, preview(self.db, replacement))
                self.assertEqual(find(self.db, '검토', source=kind, canonical_unicode=True)['total_matches'], 0)
                history = find(self.db, '검토', source=kind, include_title_history=True,
                               export_sha256=digest, canonical_unicode=True)
                self.assertTrue(history['matches'][0]['matched_historical_title'])
                self.assertEqual(path.read_bytes(), original)
                final = conversation(self.db, kind, cid, message_id='u')['messages'][0]
                self.assertEqual(final, shown)

    def test_both_clis_ascii_stdout(self):
        self.seed('korean', ud.normalize('NFD', '기전'))
        expected = find(self.db, '기전', canonical_unicode=True)
        for script, arguments in [('recap.py', ['find']), ('conversation_search.py', [])]:
            result = subprocess.run([sys.executable, script, '--db', str(self.db),
                *arguments, '기전', '--canonical-unicode'], capture_output=True, text=True,
                encoding='ascii', env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)


if __name__ == '__main__':
    unittest.main()
