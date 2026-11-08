"""Synthetic regressions for read-only, bounded conversation evidence selection."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from recaplib.conversation_view import conversation
from recaplib.conversation_search import find
from recap import ingest, readonly
from recaplib.session_workflow import titles


class ConversationSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.export = self.root / 'synthetic.jsonl'
        self.ids = ['z-last-lexically', 'a-first-lexically', "quote'--", 'middle', 'final']
        records = [dict(conversation_id='chat', message_id=mid, role='user',
                        timestamp=str(100 - i), title='Original title',
                        text=f'Private synthetic evidence {i}') for i, mid in enumerate(self.ids)]
        self.export.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
        ingest(self.db, 'primary', self.export)
        ingest(self.db, 'other', self.export)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            for table in ('export_provenance', 'export_occurrences'):
                connection.execute(f'CREATE TABLE {table} (source TEXT, conversation TEXT, '
                                   'message TEXT, original_hash TEXT, locator TEXT, parent TEXT)')
                for source in ('primary', 'other'):
                    connection.executemany(f'INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?)', [
                        (source, 'chat', mid, 'a' * 64 if source == 'primary' else 'b' * 64,
                         f'{source}:node:{i}', self.ids[i - 1] if i else None)
                        for i, mid in enumerate(self.ids)])
            # A second occurrence must survive the legacy/occurrence union.
            connection.execute('INSERT INTO export_occurrences VALUES (?, ?, ?, ?, ?, ?)',
                               ('primary', 'chat', self.ids[1], 'c' * 64, 'extra:node', self.ids[0]))
        self.revision = titles(self.db, 'primary', 'chat', 'Reviewed title', 0)['revision']

    def show(self, **kwargs):
        return conversation(self.db, 'primary', 'chat', **kwargs)

    def test_default_full_view_is_unchanged_and_read_only(self):
        before = self.db.read_bytes(), self.export.read_bytes()
        result = self.show()
        self.assertNotIn('selection', result)
        self.assertEqual([m['message_id'] for m in result['messages']], self.ids)
        self.assertEqual(result['message_count'], 5)
        self.assertEqual(result['original_title'], 'Original title')
        self.assertEqual(result['display_title'], 'Reviewed title')
        self.assertEqual(result['revision'], self.revision)
        self.assertEqual(len(result['messages'][1]['export_provenance']), 2)
        self.assertEqual(result, self.show(offset=0))
        self.assertEqual(before, (self.db.read_bytes(), self.export.read_bytes()))

    def test_pages_preserve_archive_order_summary_and_evidence(self):
        full = self.show()
        for offset, expected_next in ((0, 2), (2, 4), (4, None)):
            with self.subTest(offset=offset):
                result = self.show(limit=2, offset=offset)
                self.assertEqual(result['messages'], full['messages'][offset:offset + 2])
                self.assertEqual(result['selection'], dict(mode='page', limit=2, offset=offset,
                                  returned_messages=len(result['messages']), next_offset=expected_next))
                self.assertEqual({k: v for k, v in result.items() if k not in ('messages', 'selection')},
                                 {k: v for k, v in full.items() if k != 'messages'})
        self.assertEqual(self.show(limit=5)['selection']['next_offset'], None)
        self.assertEqual(self.show(limit=1000)['messages'], full['messages'])

    def test_page_past_end_keeps_summary_and_is_empty(self):
        for offset in (5, 500, 2**63 - 1):
            with self.subTest(offset=offset):
                result = self.show(limit=2, offset=offset)
                self.assertEqual(result['messages'], [])
                self.assertEqual(result['message_count'], 5)
                self.assertEqual(result['display_title'], 'Reviewed title')
                self.assertEqual(result['selection'], dict(mode='page', limit=2, offset=offset,
                                                          returned_messages=0, next_offset=None))

    def test_exact_message_handles_quoted_ids_and_unknown_ids(self):
        full = self.show()
        for index in (1, 2):
            result = self.show(message_id=self.ids[index])
            self.assertEqual(result['messages'], [full['messages'][index]])
            self.assertEqual(result['message_count'], 5)
            self.assertEqual(result['selection'], dict(mode='message', message_id=self.ids[index],
                                                       returned_messages=1))
        for mid in ('missing', "' OR 1=1 --"):
            with self.subTest(message_id=mid), self.assertRaises(ValueError):
                self.show(message_id=mid)
        with self.assertRaises(ValueError):
            conversation(self.db, 'primary', 'missing', limit=1)

    def test_search_hit_opens_exact_archived_evidence(self):
        before = self.db.read_bytes()
        hit = find(self.db, '3', source='primary')['matches'][0]
        sample = hit['message_matches'][0]
        selected = conversation(self.db, hit['source_id'], hit['conversation_id'],
                                message_id=sample['message_id'])
        message = selected['messages'][0]
        self.assertEqual(message['text'][sample['snippet_start']:sample['snippet_end']], sample['snippet'])
        self.assertEqual(message['source_sha256'], sample['source_sha256'])
        self.assertEqual(message['source_line'], sample['source_line'])
        self.assertEqual(message['message_id'], self.ids[3])
        self.assertEqual(selected['selection']['returned_messages'], 1)
        self.assertEqual(self.db.read_bytes(), before)

    def test_limit_and_offset_validation_precedes_database_access(self):
        invalid = ([dict(limit=x) for x in (0, -1, 1001, True, False, 1.5, '2', [])] +
                   [dict(limit=1, offset=x) for x in (-1, 2**63, True, False, 0.5, '0', None)] +
                   [dict(offset=1)])
        with patch('recaplib.conversation_view.readonly', side_effect=AssertionError('validation must happen first')):
            for options in invalid:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    self.show(**options)

    def test_exact_selector_validation_and_conflicts_precede_database_access(self):
        invalid = ([dict(message_id=x) for x in ('', 1, True, [], {})] +
                   [dict(message_id=self.ids[0], limit=1), dict(message_id=self.ids[0], offset=1)])
        with patch('recaplib.conversation_view.readonly', side_effect=AssertionError('validation must happen first')):
            for options in invalid:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    self.show(**options)
        self.assertEqual(len(self.show(message_id=self.ids[0], offset=0)['messages']), 1)

    def test_source_and_conversation_isolation(self):
        result = conversation(self.db, 'other', 'chat', message_id=self.ids[1])
        self.assertEqual(result['display_title'], 'Original title')
        self.assertEqual(result['revision'], 0)
        self.assertEqual(result['messages'][0]['export_provenance'], [dict(
            original_sha256='b' * 64, locator='other:node:1', parent_id=self.ids[0])])
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("INSERT INTO export_occurrences VALUES ('primary', 'different', ?, ?, ?, NULL)",
                               (self.ids[1], 'd' * 64, 'unrelated-private-locator'))
        result = self.show(message_id=self.ids[1])
        self.assertEqual(len(result['messages'][0]['export_provenance']), 2)
        self.assertNotIn('unrelated-private-locator', json.dumps(result))
        with self.assertRaises(ValueError):
            conversation(self.db, "' OR 1=1 --", 'chat', limit=1)

    def test_legacy_and_absent_provenance_tables(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('DROP TABLE export_occurrences')
        result = self.show(limit=1, offset=1)
        self.assertEqual(len(result['messages'][0]['export_provenance']), 1)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('DROP TABLE export_provenance')
            connection.execute('DROP TABLE title_history')
        for options in (dict(limit=1), dict(message_id=self.ids[1])):
            result = self.show(**options)
            self.assertEqual(result['messages'][0]['export_provenance'], [])
            self.assertEqual(result['display_title'], 'Original title')
            self.assertEqual(result['revision'], 0)

    def test_unified_and_standalone_cli_match_api_without_mutation(self):
        before = self.db.read_bytes(), self.export.read_bytes()
        for args, options in (([], {}), (['--limit', '2', '--offset', '1'], dict(limit=2, offset=1)),
                              (['--message', self.ids[2]], dict(message_id=self.ids[2]))):
            expected = self.show(**options)
            for script in ('recap.py', 'conversation_view.py'):
                with self.subTest(script=script, args=args):
                    result = subprocess.run([sys.executable, script, '--db', str(self.db), 'show',
                                             '--source', 'primary', '--conversation', 'chat', *args],
                                            capture_output=True, text=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), expected)
        self.assertEqual(before, (self.db.read_bytes(), self.export.read_bytes()))

    def test_ascii_stdout_preserves_unicode_in_page_and_exact_cli_views(self):
        path = self.root / 'unicode.jsonl'
        record = dict(conversation_id='unicode-chat', message_id='unicode-message', role='user',
                      timestamp='synthetic', title='원래 제목 🌳', text='한글 근거와 이모지 😀')
        path.write_text(json.dumps(record, ensure_ascii=False) + '\n', encoding='utf-8')
        ingest(self.db, 'unicode', path)
        titles(self.db, 'unicode', 'unicode-chat', '검토한 제목 📝', 0)
        before = self.db.read_bytes(), path.read_bytes()
        environment = dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0')
        for args, options in ((['--limit', '1'], dict(limit=1)),
                              (['--message', 'unicode-message'], dict(message_id='unicode-message'))):
            expected = conversation(self.db, 'unicode', 'unicode-chat', **options)
            for script in ('recap.py', 'conversation_view.py'):
                with self.subTest(script=script, args=args):
                    result = subprocess.run([sys.executable, script, '--db', str(self.db), 'show',
                                             '--source', 'unicode', '--conversation', 'unicode-chat', *args],
                                            capture_output=True, env=environment, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr.decode('ascii'))
                    actual = json.loads(result.stdout.decode('ascii'))
                    self.assertEqual(actual, expected)
                    self.assertEqual(actual['original_title'], record['title'])
                    self.assertEqual(actual['display_title'], '검토한 제목 📝')
                    self.assertEqual(actual['messages'][0]['text'], record['text'])
        self.assertEqual(before, (self.db.read_bytes(), path.read_bytes()))

    def test_cli_rejects_invalid_selection_cleanly(self):
        before = self.db.read_bytes()
        for script in ('recap.py', 'conversation_view.py'):
            for args in (['--limit', '0'], ['--offset', '1'], ['--message', 'missing'],
                         ['--limit', '1', '--offset', str(2**63)], ['--message', self.ids[0], '--limit', '1']):
                with self.subTest(script=script, args=args):
                    result = subprocess.run([sys.executable, script, '--db', str(self.db), 'show',
                                             '--source', 'primary', '--conversation', 'chat', *args],
                                            capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, '')
                    self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(before, self.db.read_bytes())

    def test_only_selected_message_bodies_and_provenance_are_fetched(self):
        # Observe rows materialized by sqlite, not merely the final filtered JSON.
        for options, wanted in ((dict(limit=1, offset=1), self.ids[1]),
                                (dict(message_id=self.ids[2]), self.ids[2])):
            fetched, queries, opened = [], [], []
            def traced(db):
                connection = readonly(db)
                opened.append(connection)
                def record(cursor, values):
                    row = sqlite3.Row(cursor, values)
                    fetched.append(dict(row))
                    return row
                connection.row_factory = record
                connection.set_trace_callback(queries.append)
                return connection
            with self.subTest(options=options), patch('recaplib.conversation_view.readonly', traced):
                result = self.show(**options)
            self.assertEqual(len(result['messages']), 1)
            self.assertEqual(len(opened), 1)
            bodies = [row for row in fetched if 'text' in row]
            evidence = [row for row in fetched if 'original_hash' in row]
            self.assertEqual([r['message_id'] for r in bodies], [wanted])
            self.assertTrue(evidence)
            self.assertTrue(all(r['message'] == wanted for r in evidence))
            self.assertEqual(sum(q.strip().upper() == 'BEGIN' for q in queries), 1)

    def test_selection_summary_and_provenance_share_read_snapshot(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        expected = self.show(limit=1, offset=1)
        changed = []
        def traced(db):
            connection = readonly(db)
            def trace(sql):
                if sql.lstrip().upper().startswith('SELECT') and 'original_hash' in sql and not changed:
                    changed.append(True)
                    with closing(sqlite3.connect(self.db)) as writer, writer:
                        writer.execute("UPDATE messages SET text='Changed after snapshot' WHERE source_id='primary'")
                        writer.execute("UPDATE title_history SET title='Changed title' WHERE source='primary'")
                        for table in ('export_provenance', 'export_occurrences'):
                            writer.execute(f"DELETE FROM {table} WHERE source='primary'")
            connection.set_trace_callback(trace)
            return connection
        with patch('recaplib.conversation_view.readonly', traced):
            actual = self.show(limit=1, offset=1)
        self.assertTrue(changed)
        self.assertEqual(actual, expected)
        later = self.show(limit=1, offset=1)
        self.assertEqual(later['display_title'], 'Changed title')
        self.assertEqual(later['messages'][0]['text'], 'Changed after snapshot')
        self.assertEqual(later['messages'][0]['export_provenance'], [])


if __name__ == '__main__':
    unittest.main()
