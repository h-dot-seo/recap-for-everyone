"""Synthetic regression checks for bounded Python result buffering."""
import json
import sqlite3
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch
from conversation_search import find
from conversation_view import conversations, conversation
from recap import ingest, readonly
from session_workflow import titles


class ArchiveScalingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'synthetic.sqlite'

    def load(self, count=10, messages=2, padding=''):
        path = self.root / 'synthetic.jsonl'
        with path.open('w', encoding='utf-8') as f:
            for number in range(count):
                for index in range(messages):
                    row = dict(conversation_id=f'c{number:05}', message_id=str(index), role='user',
                               timestamp='synthetic', title='Original',
                               text=('apple' if index % 2 == 0 else 'pear') + padding)
                    f.write(json.dumps(row) + '\n')
        ingest(self.db, 'synthetic', path)

    def test_search_keeps_ranking_counts_and_cross_message_and(self):
        self.load()
        titles(self.db, 'synthetic', 'c00009', 'Apple plan', 0)
        result = find(self.db, 'APPLE pear', limit=2)
        self.assertEqual(result['total_matches'], 10)
        self.assertTrue(result['truncated'])
        self.assertEqual([r['conversation_id'] for r in result['matches']], ['c00009', 'c00000'])
        self.assertEqual(result['matches'][0]['message_count'], 2)
        self.assertEqual(len(result['matches'][0]['message_matches']), 2)
        self.assertEqual(find(self.db, 'not-present')['total_matches'], 0)

    def test_search_python_buffer_does_not_hold_the_archive(self):
        self.load(count=300, messages=8, padding=' synthetic' * 400)
        tracemalloc.start()
        try:
            result = find(self.db, 'apple pear', limit=2)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(result['total_matches'], 300)
        self.assertEqual(len(result['matches']), 2)
        self.assertTrue(all(len(row['message_matches']) == 3 for row in result['matches']))
        # The fixture contains >8 MB of text. This measures Python allocations,
        # not SQLite's native page cache or an overall process memory guarantee.
        self.assertLess(peak, 2_000_000)

    def test_listing_only_fetches_titles_for_the_page(self):
        self.load(count=120)
        titles(self.db, 'synthetic', 'c00080', 'Selected title', 0)
        queries = []

        def traced(db):
            connection = readonly(db)
            connection.set_trace_callback(queries.append)
            return connection

        with patch('conversation_view.readonly', traced):
            result = conversations(self.db, limit=3, offset=79)
        self.assertEqual(result['total'], 120)
        self.assertEqual(len(result['conversations']), 3)
        self.assertEqual(result['conversations'][1]['display_title'], 'Selected title')
        self.assertEqual(sum(q.startswith('SELECT title FROM messages') for q in queries), 3)
        queries.clear()
        with patch('conversation_view.readonly', traced):
            detail = conversation(self.db, 'synthetic', 'c00080')
        self.assertEqual(detail['display_title'], 'Selected title')
        self.assertEqual(sum(q.startswith('SELECT title FROM messages') for q in queries), 1)

    def test_empty_archive_and_noninteger_limits(self):
        self.load(count=0)
        self.assertEqual(find(self.db, 'apple')['total_matches'], 0)
        self.assertEqual(conversations(self.db)['total'], 0)
        for limit in (True, 1.5, '1'):
            with self.assertRaises(ValueError):
                find(self.db, 'apple', limit=limit)

    def test_latest_title_cursor_is_single_pass_and_source_scoped(self):
        self.load(count=30)
        for number in range(30):
            first = titles(self.db, 'synthetic', f'c{number:05}', 'Old label', 0)
            titles(self.db, 'synthetic', f'c{number:05}', 'Reviewed label', first['revision'])
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO title_history(source,conversation,title) VALUES('aaa','orphan','Ignored')")
            c.execute("INSERT INTO title_history(source,conversation,title) VALUES('synthetic','c00000-extra','Ignored')")
        queries = []

        def traced(db):
            connection = readonly(db)
            connection.set_trace_callback(queries.append)
            return connection

        with patch('conversation_search.readonly', traced):
            result = find(self.db, 'reviewed pear', source='synthetic', limit=3)
        self.assertEqual(result['total_matches'], 30)
        self.assertEqual(find(self.db, 'old')['total_matches'], 0)
        self.assertEqual(find(self.db, 'ignored')['total_matches'], 0)
        self.assertEqual(find(self.db, 'reviewed', source='aaa')['total_matches'], 0)
        self.assertEqual(sum('FROM title_history' in q for q in queries), 1)
