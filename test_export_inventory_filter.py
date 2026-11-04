"""Synthetic metadata-only pre-import discovery, with unchanged source boundaries."""
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from export_inventory import list_export
from session_workflow import import_export
from conversation_view import conversations
from conversation_search import find
from title_suggestion import suggest
from title_proposal import preview, apply_preview


class ExportInventoryFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.json'
        self.db = Path(self.tmp.name) / 'archive.sqlite'

    @staticmethod
    def web(identity, title='Other title', body='Synthetic body sentinel'):
        return dict(id=identity, title=title, mapping={'m': dict(parent=None,
            message=dict(author=dict(role='user'), content=dict(parts=[body])))})

    def web_file(self, records):
        self.path.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')

    def local_file(self):
        records = []
        for identity in ('a-session', 'z-needle-session'):
            records.extend([
                dict(type='session_meta', payload=dict(id=identity, title='Hidden metadata title',
                    cwd='/Synthetic/HiddenCwd', originator='HiddenOrigin')),
                dict(type='response_item', payload=dict(type='message', id='m', role='user',
                    content=[dict(type='input_text', text='HiddenBody synthetic planning')]))])
        self.path.write_text('\n'.join(json.dumps(x) for x in records), encoding='utf-8')

    def ids(self, **kwargs):
        return [x['conversation'] for x in list_export(self.path, 'web', **kwargs)['conversations']]

    def cli(self, script, *args, ok=True):
        result = subprocess.run([sys.executable, str(Path(__file__).parent / script),
            *map(str, args)], cwd=self.tmp.name, capture_output=True, encoding='utf-8', timeout=20,
            env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertTrue(result.stdout.isascii())
        return json.loads(result.stdout) if ok else result.stderr

    def test_late_match_beyond_maximum_page_and_global_counts(self):
        self.web_file([self.web(f'chat-{i:04}', 'Needle project review' if i == 1049 else 'Other')
                       for i in range(1050)])
        full = list_export(self.path, 'web', limit=1000)
        result = list_export(self.path, 'web', contains='Needle project')
        self.assertEqual([x['conversation'] for x in result['conversations']], ['chat-1049'])
        self.assertEqual(result['filter']['matched_conversations'], 1)
        self.assertEqual(result['filter']['matched_selectable_conversations'], 1)
        self.assertIsNone(result['next_offset'])
        for key in ('coverage', 'original_sha256', 'original_bytes', 'total_conversations',
                    'selectable_conversations', 'order', 'contains_message_text'):
            self.assertEqual(result[key], full[key], key)
        self.assertEqual(result['total_conversations'], 1050)
        self.assertNotIn('chat-1049', [x['conversation'] for x in full['conversations']])

    def test_empty_export_and_empty_original_titles(self):
        self.web_file([])
        result = list_export(self.path, 'web', contains='needle')
        self.assertEqual(result['conversations'], [])
        self.assertEqual(result['total_conversations'], 0)
        self.assertEqual(result['filter']['matched_conversations'], 0)
        self.assertIsNone(result['next_offset'])
        missing = self.web('needle-missing'); missing.pop('title')
        self.web_file([missing, self.web('needle-null', None), self.web('needle-empty', '')])
        result = list_export(self.path, 'web', contains='needle')
        self.assertEqual(len(result['conversations']), 3)
        self.assertTrue(all(x['original_titles'] == [''] for x in result['conversations']))

    def test_sparse_pagination_uses_matching_offsets_and_sorted_ids(self):
        self.web_file([self.web(f'chat-{i:03}', 'Needle' if i % 17 == 0 else 'Other')
                       for i in reversed(range(100))])
        expected = [f'chat-{i:03}' for i in range(0, 100, 17)]
        pages = [list_export(self.path, 'web', limit=2, offset=i, contains='needle')
                 for i in (0, 2, 4, 6, 999)]
        self.assertEqual([x['conversation'] for p in pages for x in p['conversations']], expected)
        self.assertEqual([p['next_offset'] for p in pages], [2, 4, None, None, None])
        for page in pages:
            self.assertEqual(page['filter']['matched_conversations'], 6)
            self.assertEqual(page['total_conversations'], 100)
        none = list_export(self.path, 'web', contains='absent')
        self.assertEqual(none['conversations'], [])
        self.assertEqual(none['filter']['matched_conversations'], 0)
        self.assertEqual(none['filter']['matched_selectable_conversations'], 0)
        self.assertIsNone(none['next_offset'])

    def test_literal_phrase_punctuation_and_meaningful_whitespace(self):
        self.web_file([self.web('a', 'alpha beta'), self.web('b', 'alpha other beta'),
                       self.web('c', 'literal %_*[x] "quote"'), self.web('d', ' alpha ')])
        self.assertEqual(self.ids(contains='alpha beta'), ['a'])
        self.assertEqual(self.ids(contains='%_*[x]'), ['c'])
        self.assertEqual(self.ids(contains='"quote"'), ['c'])
        self.assertEqual(self.ids(contains=' alpha '), ['d'])
        self.assertEqual(list_export(self.path, 'web', contains=' alpha ')['filter']['contains'], ' alpha ')
        self.assertEqual(self.ids(contains='alpha|beta'), [])

    def test_casefold_match_preserves_original_metadata_and_order(self):
        self.web_file([self.web('z', 'Straße'), self.web('Straße-ID', 'untouched'),
                       self.web('A', 'STRASSE')])
        result = list_export(self.path, 'web', contains='STRASSE')
        self.assertEqual([x['conversation'] for x in result['conversations']], ['A', 'Straße-ID', 'z'])
        self.assertEqual(result['conversations'][-1]['original_titles'], ['Straße'])
        summary = result['filter']
        self.assertEqual(summary['fields'], ['conversation', 'original_titles'])
        self.assertEqual(summary['matching'], 'literal substring within one case-folded metadata field')
        self.assertFalse(summary['canonical_unicode'])
        self.assertNotIn('normalization', summary)
        self.assertNotIn('unicode_version', summary)

    def test_canonical_opt_in_composed_decomposed_korean_and_no_compatibility_fold(self):
        self.web_file([self.web('a', 'Cafe\u0301'), self.web('b', 'Café'),
                       self.web('c', '\u1100\u1161'), self.web('d', '가'), self.web('e', 'Ａ')])
        self.assertEqual(self.ids(contains='CAFÉ'), ['b'])
        self.assertEqual(self.ids(contains='CAFÉ', canonical_unicode=True), ['a', 'b'])
        self.assertEqual(self.ids(contains='가'), ['d'])
        self.assertEqual(self.ids(contains='가', canonical_unicode=True), ['c', 'd'])
        self.assertEqual(self.ids(contains='Ａ', canonical_unicode=True), ['e'])
        self.assertNotIn('e', self.ids(contains='A', canonical_unicode=True))
        summary = list_export(self.path, 'web', contains='CAFÉ', canonical_unicode=True)['filter']
        self.assertEqual(summary['normalization'], 'NFC(NFD(text).casefold())')
        self.assertEqual(summary['unicode_version'], unicodedata.unidata_version)
        # Canonically equivalent identities are matching candidates, not one identity.
        self.web_file([self.web('Café', 'Composed title'), self.web('Cafe\u0301', 'Decomposed title')])
        result = list_export(self.path, 'web', contains='CAFÉ', canonical_unicode=True)
        self.assertEqual([x['conversation'] for x in result['conversations']], ['Cafe\u0301', 'Café'])
        self.assertEqual([x['original_titles'] for x in result['conversations']],
                         [['Decomposed title'], ['Composed title']])
        self.assertTrue(all(x['metadata_records'] == 1 and x['selection_supported']
                            for x in result['conversations']))
        self.assertEqual(result['filter']['matched_conversations'], 2)

    def test_matches_do_not_cross_metadata_fields_or_distinct_titles(self):
        self.web_file([self.web('alpha', 'beta'), self.web('duplicate', 'one'),
                       self.web('duplicate', 'two')])
        for needle in ('alpha beta', 'alphabeta', 'one two', 'onetwo'):
            self.assertEqual(self.ids(contains=needle), [])

    def test_duplicate_id_grouping_and_empty_text_blockers_survive_filter(self):
        empty = self.web('empty', 'Needle empty'); empty['mapping'] = {}
        media = self.web('media', 'Needle media')
        media['mapping']['m']['message']['content'] = dict(parts=[dict(asset='synthetic')])
        self.web_file([self.web('duplicate', 'Other'), self.web('duplicate', 'Needle duplicate'),
                       empty, media, self.web('good', 'Needle good')])
        result = list_export(self.path, 'web', contains='needle')
        items = {x['conversation']: x for x in result['conversations']}
        self.assertEqual(items['duplicate']['original_titles'], ['Other', 'Needle duplicate'])
        self.assertEqual(items['duplicate']['metadata_records'], 2)
        self.assertEqual(items['duplicate']['extracted_messages'], 2)
        self.assertEqual(items['duplicate']['selection_blocker'], 'AMBIGUOUS_WEB_ID')
        for identity in ('empty', 'media'):
            self.assertEqual(items[identity]['selection_blocker'], 'NO_EXTRACTED_TEXT')
        self.assertEqual(result['filter']['matched_conversations'], 4)
        self.assertEqual(result['filter']['matched_selectable_conversations'], 1)
        with self.assertRaises(ValueError):
            import_export(self.db, 'synthetic', self.path, 'web', 'duplicate')

    def test_web_message_bodies_are_neither_matched_nor_returned(self):
        self.web_file([self.web('a', 'Visible title', 'UNIQUE_PRIVATE_BODY')])
        self.assertEqual(self.ids(contains='UNIQUE_PRIVATE_BODY'), [])
        result = list_export(self.path, 'web', contains='visible')
        self.assertNotIn('UNIQUE_PRIVATE_BODY', json.dumps(result))
        self.assertFalse(result['contains_message_text'])

    def test_local_formats_match_only_ids_not_guessed_titles_or_metadata(self):
        self.local_file()
        for kind in ('local', 'local-codex'):
            with self.subTest(kind=kind):
                result = list_export(self.path, kind, contains='NEEDLE')
                self.assertEqual([x['conversation'] for x in result['conversations']], ['z-needle-session'])
                self.assertEqual(result['conversations'][0]['original_titles'], [])
                for needle in ('Hidden metadata title', 'HiddenCwd', 'HiddenOrigin', 'HiddenBody'):
                    self.assertEqual(list_export(self.path, kind, contains=needle)['conversations'], [])
                for private in ('Hidden metadata title', 'HiddenCwd', 'HiddenOrigin', 'HiddenBody'):
                    self.assertNotIn(private, json.dumps(result))

    def test_invalid_unmatched_web_records_fail_even_for_zero_results(self):
        for bad in (dict(id='z', title=3, mapping={}), dict(id='z', mapping=[]),
                    dict(id='z', mapping={'bad': dict(parent='missing')})):
            self.web_file([self.web('a', 'Needle'), bad])
            for needle in ('Needle', 'absent'):
                with self.subTest(bad=bad, needle=needle), self.assertRaises(ValueError):
                    list_export(self.path, 'web', limit=1, offset=999, contains=needle)

    def test_invalid_unmatched_local_metadata_still_fails(self):
        self.local_file()
        with self.path.open('a', encoding='utf-8') as output:
            output.write('\n' + json.dumps(dict(type='session_meta', payload={})))
        for kind in ('local', 'local-codex'):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                list_export(self.path, kind, contains='absent')

    def test_invalid_filter_arguments_fail_before_source_read(self):
        invalid = [dict(contains=x) for x in ('', ' ', '\t\n', 'x'*257, '\ud800', 'x\udfff',
                                             0, False, [], {}, b'needle')]
        invalid += [dict(canonical_unicode=x) for x in (0, 1, None, 'true', [], {})]
        invalid += [dict(canonical_unicode=True)]
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('must validate before read')):
            for kwargs in invalid:
                with self.subTest(kwargs=repr(kwargs)), self.assertRaises(ValueError):
                    list_export(self.path, 'web', **kwargs)

    def test_256_codepoint_limit_not_utf8_bytes_and_default_output_unchanged(self):
        self.web_file([self.web('a', '한'*256)])
        self.assertEqual(self.ids(contains='한'*256), ['a'])
        default = list_export(self.path, 'web')
        self.assertNotIn('filter', default)
        self.assertEqual(default, list_export(self.path, 'web', contains=None, canonical_unicode=False))

    def test_one_read_hash_binding_source_unchanged_and_no_database(self):
        for kind in ('web', 'local', 'local-codex'):
            if kind == 'web': self.web_file([self.web('needle')])
            else: self.local_file()
            raw = self.path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
            with patch.object(Path, 'read_bytes', return_value=raw) as reader, \
                    patch('sqlite3.connect', side_effect=AssertionError('no DB')):
                result = list_export(self.path, kind, contains='needle', expected_export_sha256=digest)
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(result['original_sha256'], digest)
            self.assertEqual(result['coverage']['expected_export_sha256'], digest)
            self.assertEqual(result['original_bytes'], len(raw))
            self.assertEqual(self.path.read_bytes(), raw)
            self.assertFalse(self.db.exists())
            with self.assertRaises(ValueError):
                list_export(self.path, kind, contains='absent', expected_export_sha256='0'*64)

    def test_both_cli_entrypoints_match_api_and_clean_errors(self):
        for kind in ('web', 'local', 'local-codex'):
            if kind == 'web': self.web_file([self.web('needle', 'Cafe\u0301')])
            else: self.local_file()
            for canonical in (False, True):
                needle = 'CAFÉ' if kind == 'web' else 'NEEDLE'
                digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
                extra = ['--contains', needle, '--limit', 1, '--offset', 0,
                         '--expected-export-sha256', digest]
                if canonical: extra += ['--canonical-unicode']
                expected = list_export(self.path, kind, limit=1, contains=needle, canonical_unicode=canonical,
                                       expected_export_sha256=digest)
                for script, prefix in (('recap.py', ['list-export']), ('export_inventory.py', [])):
                    self.assertEqual(self.cli(script, *prefix, self.path, '--format', kind, *extra), expected)
        for script, prefix in (('recap.py', ['list-export']), ('export_inventory.py', [])):
            for extra in (['--contains', ''], ['--contains', 'x'*257], ['--canonical-unicode']):
                self.cli(script, *prefix, self.path, '--format', 'local', *extra, ok=False)
        self.assertEqual({p.name for p in Path(self.tmp.name).iterdir()}, {self.path.name})

    def test_documented_filter_commands_execute_against_shipped_examples(self):
        root = Path(__file__).parent
        document = (root / 'docs' / 'EXPORT_INVENTORY.md').read_text(encoding='utf-8')
        lines = [line for line in document.splitlines()
                 if line.startswith('python ') and '--contains' in line]
        self.assertEqual(len(lines), 3)
        for line in lines:
            # Tokenize the documentation first, before inserting platform paths.
            tokens = shlex.split(line)
            script = tokens[1]
            args = [str(root / value) if value.startswith('examples/') else value
                    for value in tokens[2:]]
            with self.subTest(command=line):
                result = self.cli(script, *args)
                expected_id = 'synthetic-attributed' if '--format local-codex' in line else 'synthetic-chat'
                self.assertEqual([x['conversation'] for x in result['conversations']], [expected_id])
                self.assertEqual(result['filter']['matched_conversations'], 1)
                self.assertTrue(result['conversations'][0]['selection_supported'])
                self.assertIsNone(result['next_offset'])
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_filtered_discovery_selected_hash_bound_import_review_apply_search(self):
        for kind in ('web', 'local', 'local-codex'):
            if kind == 'web':
                self.web_file([self.web('a-unselected'), self.web('z-needle-session', 'Needle original')])
            else: self.local_file()
            raw = self.path.read_bytes()
            inventory = list_export(self.path, kind, contains='needle', limit=1)
            item, = inventory['conversations']
            self.assertTrue(item['selection_supported'])
            receipt = import_export(self.db, kind, self.path, kind, item['conversation'],
                                    expected_export_sha256=inventory['original_sha256'])
            self.assertEqual(receipt['inserted'], 1)
            archived = conversations(self.db, kind)['conversations']
            self.assertEqual([x['conversation'] for x in archived], ['z-needle-session'])
            proposal = suggest(self.db, kind, item['conversation'])
            before = self.db.read_bytes()
            reviewed = preview(self.db, proposal, 'Reviewed synthetic orchard inventory')
            self.assertEqual(self.db.read_bytes(), before)
            apply_preview(self.db, reviewed)
            results = find(self.db, 'orchard', source=kind)
            self.assertEqual(results['total_matches'], 1)
            self.assertEqual(conversations(self.db, kind)['conversations'][0]['display_title'],
                             'Reviewed synthetic orchard inventory')
            self.assertEqual(self.path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
