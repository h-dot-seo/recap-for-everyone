"""Synthetic concurrent-writer and WAL snapshot regression tests."""
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from conversation_search import find
from conversation_view import conversations
from recap import readonly
from session_workflow import import_export, titles


class ConcurrentTitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'synthetic.sqlite'
        import_export(self.db, 'demo', 'examples/web-export.json', 'web')

    def test_two_checked_writers_cannot_both_replace_one_revision(self):
        gate = threading.Barrier(2)

        def change(title):
            gate.wait(timeout=10)
            try:
                return titles(self.db, 'demo', 'synthetic-chat', title, 0)
            except ValueError as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(change, title) for title in ('Synthetic title A', 'Synthetic title B')]
            outcomes = [future.result(timeout=15) for future in futures]
        winners = [value for value in outcomes if isinstance(value, dict)]
        losers = [value for value in outcomes if isinstance(value, str)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), 1)
        self.assertIn('stale title preview', losers[0])
        self.assertEqual(titles(self.db, 'demo', 'synthetic-chat')['display_title'], winners[0]['display_title'])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM title_history').fetchone()[0], 1)

    def _snapshot_check(self, module, trigger, read):
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        old = titles(self.db, 'demo', 'synthetic-chat', 'Old synthetic label', 0)
        changed = []

        def traced(db):
            connection = readonly(db)

            def on_statement(sql):
                if not changed and sql.startswith(trigger):
                    changed.append(True)
                    titles(self.db, 'demo', 'synthetic-chat', 'New synthetic label', old['revision'])

            connection.set_trace_callback(on_statement)
            return connection

        with patch(module + '.readonly', traced):
            during = read()
        self.assertEqual(changed, [True])
        self.assertEqual(during['display_title'], 'Old synthetic label')
        self.assertEqual(read()['display_title'], 'New synthetic label')

    def test_inventory_remains_consistent_during_a_committed_title_change(self):
        self._snapshot_check('conversation_view', 'SELECT title FROM messages',
                             lambda: conversations(self.db)['conversations'][0])

    def test_search_remains_consistent_during_a_committed_title_change(self):
        self._snapshot_check('conversation_search', 'SELECT h.source,h.conversation',
                             lambda: find(self.db, 'synthetic')['matches'][0])
