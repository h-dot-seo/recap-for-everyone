"""Synthetic evidence for bounded, coverage-aware message samples."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import conversation_search
from conversation_search import find
from recap import ingest
from session_workflow import import_export, titles


class SearchSampleCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'synthetic.sqlite'
        self.sequence = 0

    def load(self, bodies, conversation='synthetic', source='demo', title='Synthetic title'):
        self.sequence += 1
        path = self.root / ('messages-%s.jsonl' % self.sequence)
        records = [dict(conversation_id=conversation, message_id='m%s' % i,
                        role='user', timestamp='synthetic', title=title, text=body)
                   for i, body in enumerate(bodies)]
        path.write_text(''.join(json.dumps(record) + '\n' for record in records), encoding='utf-8')
        ingest(self.db, source, path)

    def hit(self, query, **options):
        result = find(self.db, query, **options)
        self.assertEqual(result['total_matches'], 1)
        return result['matches'][0]

    def assert_sample(self, hit, ids, count, matched, sampled=None, unsampled=None):
        sampled = matched if sampled is None else sampled
        unsampled = [] if unsampled is None else unsampled
        self.assertEqual([row['message_id'] for row in hit['message_matches']], ids)
        self.assertEqual(hit['message_match_count'], count)
        self.assertIs(hit['message_matches_truncated'], count > len(ids))
        self.assertEqual(hit['message_term_coverage'], dict(
            matched_terms=matched, sampled_terms=sampled, unsampled_terms=unsampled,
            all_matched_terms_sampled=not unsampled))
        self.assertLessEqual(len(ids), 3)

    def test_late_rare_term_replaces_redundant_sample_and_counts_all_bodies(self):
        self.load(['alpha', 'alpha', 'alpha', 'beta', 'unrelated', 'alpha'])
        hit = self.hit('alpha beta')
        self.assert_sample(hit, ['m0', 'm1', 'm3'], 5, ['alpha', 'beta'])
        self.assertEqual(hit['message_count'], 6)

    def test_equal_union_prefers_larger_summed_message_coverage(self):
        self.load(['alpha', 'beta', 'gamma', 'alpha beta'])
        self.assert_sample(self.hit('alpha beta gamma'), ['m0', 'm2', 'm3'], 4,
                           ['alpha', 'beta', 'gamma'])

    def test_equal_scores_keep_earliest_in_archive_order_not_message_id_order(self):
        self.load(['alpha beta'] * 12)
        self.assert_sample(self.hit('beta alpha'), ['m0', 'm1', 'm2'], 12,
                           ['beta', 'alpha'])

    def test_later_multi_term_body_improves_union_without_exceeding_three(self):
        self.load(['alpha', 'alpha', 'beta', 'gamma delta'])
        self.assert_sample(self.hit('delta beta alpha gamma'), ['m0', 'm2', 'm3'], 4,
                           ['delta', 'beta', 'alpha', 'gamma'])

    def test_four_distinct_bodies_explicitly_report_uncovered_terms(self):
        self.load(['alpha', 'beta', 'gamma', 'delta', 'epsilon'])
        self.assert_sample(self.hit('epsilon delta gamma beta alpha'),
                           ['m0', 'm1', 'm2'], 5,
                           ['epsilon', 'delta', 'gamma', 'beta', 'alpha'],
                           sampled=['gamma', 'beta', 'alpha'], unsampled=['epsilon', 'delta'])

    def test_casefolded_duplicate_terms_count_once_for_sampling(self):
        self.load(['alpha', 'beta', 'gamma', 'Straße', 'beta gamma'])
        hit = self.hit('ALPHA alpha beta gamma STRASSE Straße')
        # Duplicate alpha/strasse terms must not skew the summed-coverage tie break.
        self.assert_sample(hit, ['m0', 'm1', 'm4'], 5,
                           ['alpha', 'beta', 'gamma', 'strasse'],
                           sampled=['alpha', 'beta', 'gamma'], unsampled=['strasse'])

    def test_twenty_input_terms_allowed_but_twenty_one_duplicates_rejected_before_read(self):
        self.load(['alpha'])
        self.assert_sample(self.hit(' '.join(['ALPHA'] * 20)), ['m0'], 1, ['alpha'])
        with patch.object(conversation_search, 'readonly', side_effect=AssertionError('must validate first')):
            with self.assertRaises(ValueError):
                find(self.db, ' '.join(['alpha'] * 21))

    def test_full_selected_body_coverage_does_not_claim_all_terms_visible_in_excerpt(self):
        self.load(['alpha ' + 'padding ' * 100 + 'beta'])
        result = find(self.db, 'alpha beta')
        hit = result['matches'][0]
        self.assert_sample(hit, ['m0'], 1, ['alpha', 'beta'])
        self.assertNotIn('beta', hit['message_matches'][0]['snippet'])
        self.assertLessEqual(len(hit['message_matches'][0]['snippet']), 240)
        semantics = result['message_sample_semantics'].casefold()
        for word in ('streaming', 'literal', 'semantic', '240'):
            self.assertIn(word, semantics)

    def test_title_only_and_history_only_have_empty_body_coverage(self):
        self.load(['unrelated'], title='Alpha')
        self.assert_sample(self.hit('alpha'), [], 0, [])
        changed = titles(self.db, 'demo', 'synthetic', 'Beta', 0)
        self.assert_sample(self.hit('beta'), [], 0, [])
        titles(self.db, 'demo', 'synthetic', 'Current', changed['revision'])
        self.assertEqual(find(self.db, 'beta')['total_matches'], 0)
        historical = self.hit('beta', include_title_history=True)
        self.assertTrue(historical['matched_historical_title'])
        self.assert_sample(historical, [], 0, [])

    def test_title_terms_do_not_leak_into_body_coverage_and_and_matching_remains(self):
        self.load(['beta', 'unrelated'], title='Alpha')
        self.assert_sample(self.hit('alpha beta'), ['m0'], 1, ['beta'])
        self.assertEqual(find(self.db, 'alpha beta gamma')['total_matches'], 0)

    def test_title_first_ranking_and_limit_remain_unchanged(self):
        self.load(['alpha'], conversation='a-body')
        self.load(['unrelated'], conversation='z-title', title='Alpha')
        result = find(self.db, 'alpha', limit=1)
        self.assertEqual(result['total_matches'], 2)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['matches'][0]['conversation_id'], 'z-title')
        self.assert_sample(result['matches'][0], [], 0, [])

    def test_sources_do_not_share_counts_or_coverage(self):
        self.load(['alpha', 'alpha', 'alpha', 'beta'], source='first')
        self.load(['alpha', 'gamma'], source='second')
        self.assert_sample(self.hit('alpha beta', source='first'), ['m0', 'm1', 'm3'], 4,
                           ['alpha', 'beta'])
        self.assertEqual(find(self.db, 'alpha beta', source='second')['total_matches'], 0)
        self.assertEqual(find(self.db, 'beta gamma')['total_matches'], 0)
        self.assert_sample(self.hit('alpha', source='second'), ['m0'], 1, ['alpha'])

    def test_export_scope_counts_only_linked_bodies_and_keeps_selected_provenance(self):
        def load_export(name, bodies):
            path = self.root / (name + '.json')
            mapping = {name + str(i): dict(parent=None, message=dict(
                author=dict(role='user'), content=dict(parts=[body])))
                for i, body in enumerate(bodies)}
            path.write_text(json.dumps([dict(id='split', title='Synthetic', mapping=mapping)]))
            return import_export(self.db, 'demo', path, 'web')['coverage']['original_sha256']
        first = load_export('first', ['alpha', 'alpha', 'alpha', 'beta'])
        second = load_export('second', ['gamma', 'unrelated'])
        hit = self.hit('alpha beta', export_sha256=first)
        self.assertEqual(hit['message_count'], 4)
        self.assertEqual(hit['message_match_count'], 4)
        self.assertTrue(hit['message_matches_truncated'])
        self.assertEqual(hit['message_term_coverage']['matched_terms'], ['alpha', 'beta'])
        self.assertEqual(hit['message_term_coverage']['unsampled_terms'], [])
        self.assertEqual(len(hit['message_matches']), 3)
        self.assertTrue(any('beta' in row['snippet'] for row in hit['message_matches']))
        for row in hit['message_matches']:
            self.assertTrue(row['export_provenance'])
            self.assertTrue(all(p['original_sha256'] == first for p in row['export_provenance']))
        self.assertEqual(find(self.db, 'alpha gamma', export_sha256=first)['total_matches'], 0)
        self.assertEqual(find(self.db, 'alpha', export_sha256=second)['total_matches'], 0)
        other = self.hit('gamma', export_sha256=second)
        self.assertEqual(other['message_match_count'], 1)
        self.assertFalse(other['message_matches_truncated'])
        self.assertEqual(other['message_term_coverage']['matched_terms'], ['gamma'])

    def test_streaming_materializes_only_entering_candidates_not_all_matching_bodies(self):
        path = self.root / 'many.json'
        mapping = {'node%s' % i: dict(parent=None, message=dict(
            author=dict(role='user'), content=dict(parts=[body])))
            for i, body in enumerate(['alpha'] * 50 + ['beta'])}
        path.write_text(json.dumps([dict(id='many', title='Synthetic', mapping=mapping)]))
        digest = import_export(self.db, 'demo', path, 'web')['coverage']['original_sha256']
        with patch.object(conversation_search, '_matching_export_provenance',
                          wraps=conversation_search._matching_export_provenance) as provenance, \
                patch.object(conversation_search, '_matching_excerpt',
                             wraps=conversation_search._matching_excerpt) as excerpt:
            hit = self.hit('alpha beta', export_sha256=digest)
        # Three initial entrants and one later replacement are materialized.
        self.assertEqual(provenance.call_count, 4)
        self.assertEqual(excerpt.call_count, 4)
        self.assertEqual(hit['message_count'], 51)
        self.assert_sample(hit, ['node0', 'node1', 'node50'], 51, ['alpha', 'beta'])

    def test_both_clis_equal_api_and_do_not_write_any_archive_files(self):
        self.load(['alpha', 'alpha', 'alpha', '기전', 'unrelated'])
        before = {path.name: path.read_bytes() for path in self.root.iterdir()}
        expected = find(self.db, 'ALPHA 기전', source='demo')
        for script, command in [('conversation_search.py', []), ('recap.py', ['find'])]:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).parent / script), '--db', str(self.db),
                 *command, 'ALPHA 기전', '--source', 'demo'], capture_output=True,
                text=True, encoding='ascii', env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=20)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout), expected)
        after = {path.name: path.read_bytes() for path in self.root.iterdir()}
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()
