"""Synthetic, metadata-only title history and checked reversal regressions."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from recap import ingest, readonly
from session_workflow import import_export, titles
from title_history import history


class TitleHistoryViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'synthetic.sqlite'
        self.seed()

    def seed(self, source='demo', conversation='chat', title='Synthetic original', message='m1'):
        path = self.root / 'synthetic.jsonl'
        path.write_text(json.dumps(dict(conversation_id=conversation, message_id=message,
            role='user', text='SYNTHETIC_PRIVATE_BODY_SENTINEL', title=title,
            timestamp='synthetic')) + '\n', encoding='utf-8')
        ingest(self.db, source, path)

    def rename(self, title, source='demo', conversation='chat'):
        revision = titles(self.db, source, conversation)['revision']
        return titles(self.db, source, conversation, title, revision)['revision']

    def read(self, **kwargs):
        return history(self.db, 'demo', 'chat', **kwargs)

    def test_missing_history_is_readonly_original_revision_zero(self):
        before = self.db.read_bytes()
        result = self.read()
        self.assertEqual(result['source'], 'demo')
        self.assertEqual(result['conversation'], 'chat')
        self.assertEqual(result['original_title'], 'Synthetic original')
        self.assertEqual(result['display_title'], 'Synthetic original')
        self.assertEqual(result['revision'], 0)
        self.assertEqual(result['changes'], [])
        self.assertEqual(result['total_changes'], 0)
        self.assertEqual(result['returned_changes'], 0)
        self.assertEqual(result['remaining_changes'], 0)
        self.assertEqual((result['limit'], result['offset']), (20, 0))
        self.assertIsNone(result['next_offset'])
        self.assertFalse(result['truncated'])
        self.assertEqual(result['scope'], 'local display title history only')
        self.assertIs(result['contains_message_text'], False)
        self.assertTrue(result['warning'])
        self.assertEqual(self.db.read_bytes(), before)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='title_history'").fetchone())

    def test_missing_database_is_not_created(self):
        missing = self.root / 'missing.sqlite'
        with self.assertRaises(sqlite3.Error):
            history(missing, 'demo', 'chat')
        self.assertFalse(missing.exists())

    def test_revision_zero_guard_and_empty_history_for_other_identity(self):
        self.assertEqual(self.read(expected_revision=0)['revision'], 0)
        self.seed(conversation='other')
        self.rename('Only other identity changed', conversation='other')
        result = self.read(expected_revision=0)
        self.assertEqual(result['changes'], [])
        self.assertEqual(result['total_changes'], 0)
        self.assertEqual(result['display_title'], 'Synthetic original')
        self.rename('First local change')
        with self.assertRaisesRegex(ValueError, 'stale title history'):
            self.read(expected_revision=0)

    def test_sparse_revisions_pages_repeated_and_reversed_labels(self):
        self.seed(conversation='other')
        first = self.rename('Chosen title')
        self.rename('Other label', conversation='other')
        second = self.rename('Chosen title')
        self.rename('Other label again', conversation='other')
        third = self.rename('Synthetic original')
        self.assertEqual([first, second, third], [1, 3, 5])
        before = self.db.read_bytes()
        page = self.read(limit=2)
        self.assertEqual(page['revision'], third)
        self.assertEqual(page['display_title'], 'Synthetic original')
        self.assertEqual(page['total_changes'], 3)
        self.assertEqual(page['returned_changes'], 2)
        self.assertEqual(page['remaining_changes'], 1)
        self.assertEqual(page['next_offset'], 2)
        self.assertTrue(page['truncated'])
        self.assertEqual([row['revision'] for row in page['changes']], [third, second])
        self.assertEqual([row['is_current'] for row in page['changes']], [True, False])
        self.assertEqual([row['previous_title'] for row in page['changes']], ['Chosen title', 'Chosen title'])
        self.assertEqual([row['title'] for row in page['changes']], ['Synthetic original', 'Chosen title'])
        self.assertTrue(all(isinstance(row['changed_at'], str) and row['changed_at'] for row in page['changes']))
        last = self.read(limit=2, offset=2, expected_revision=third)
        self.assertEqual(last['changes'][0]['revision'], first)
        self.assertEqual(last['changes'][0]['previous_title'], 'Synthetic original')
        self.assertFalse(last['changes'][0]['is_current'])
        self.assertEqual(last['remaining_changes'], 0)
        self.assertIsNone(last['next_offset'])
        self.assertFalse(last['truncated'])
        self.assertEqual(self.db.read_bytes(), before)

    def test_empty_tail_preserves_current_metadata(self):
        revision = self.rename('Current title')
        for offset in (1, 100, 2**63 - 1):
            with self.subTest(offset=offset):
                result = self.read(offset=offset)
                self.assertEqual(result['revision'], revision)
                self.assertEqual(result['display_title'], 'Current title')
                self.assertEqual(result['total_changes'], 1)
                self.assertEqual(result['changes'], [])
                self.assertEqual(result['returned_changes'], 0)
                self.assertEqual(result['remaining_changes'], 0)
                self.assertIsNone(result['next_offset'])
                self.assertFalse(result['truncated'])

    def test_source_and_conversation_scope_are_exact(self):
        self.seed(source='other')
        self.seed(conversation='other')
        self.rename('Wrong source', source='other')
        self.rename('Wrong conversation', conversation='other')
        revision = self.rename('Right title')
        result = self.read()
        self.assertEqual(result['revision'], revision)
        self.assertEqual([row['title'] for row in result['changes']], ['Right title'])
        self.assertEqual(result['total_changes'], 1)

    def test_literal_unicode_quoted_and_whitespace_identities(self):
        for source, cid in [('합성', '대화'), (' source ', ' '), ('quoted"source', "quoted'chat"), ('1', '01')]:
            with self.subTest(source=source, cid=cid):
                self.seed(source=source, conversation=cid)
                result = history(self.db, source, cid)
                self.assertEqual((result['source'], result['conversation']), (source, cid))
                self.assertEqual(result['revision'], 0)

    def test_original_uses_first_message_and_preserves_legacy_values(self):
        for index, original in enumerate(['', ' ', 'Synthetic\noriginal', 'x' * 201]):
            cid = 'legacy-' + str(index)
            self.seed(conversation=cid, title=original)
            self.seed(conversation=cid, title='Later imported title', message='m2')
            with self.subTest(original=original):
                self.assertEqual(history(self.db, 'demo', cid)['original_title'], original)
                revision = self.rename('Valid override', conversation=cid)
                result = history(self.db, 'demo', cid)
                self.assertEqual(result['original_title'], original)
                self.assertEqual(result['changes'][0]['previous_title'], original)
                self.assertEqual(result['revision'], revision)

    def test_legacy_history_values_are_not_validated_as_new_titles(self):
        self.rename('Valid title')
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute('INSERT INTO title_history(source,conversation,previous,title,changed_at) VALUES(?,?,?,?,?)',
                    ('demo', 'chat', 'Valid title', 'Legacy\nmultiline', '2000-01-01 00:00:00'))
        before = self.db.read_bytes()
        result = self.read()
        self.assertEqual(result['display_title'], 'Legacy\nmultiline')
        self.assertEqual(result['changes'][0]['changed_at'], '2000-01-01 00:00:00')
        self.assertEqual(self.db.read_bytes(), before)

    def test_unknown_conversation_and_orphan_history_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unknown conversation'):
            history(self.db, 'demo', 'missing')
        self.rename('Valid title')
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute('INSERT INTO title_history(source,conversation,previous,title) VALUES(?,?,?,?)',
                    ('demo', 'missing', '', 'Orphan label'))
        before = self.db.read_bytes()
        with self.assertRaisesRegex(ValueError, 'unknown conversation'):
            history(self.db, 'demo', 'missing')
        self.assertEqual(self.db.read_bytes(), before)

    def test_invalid_arguments_fail_before_database_access(self):
        cases = []
        for value in (None, '', ' ', 1, True, [], {}):
            cases.append((value, 'chat', {}))
        for value in (None, '', 1, True, [], {}):
            cases.append(('demo', value, {}))
        for field, values in [('limit', [None, True, False, 0, -1, 1001, 1.0, '1']),
                              ('offset', [None, True, False, -1, 2**63, 0.0, '0']),
                              ('expected_revision', [True, False, -1, 0.0, '0', [], {}])]:
            cases.extend(('demo', 'chat', {field: value}) for value in values)
        for source, cid, kwargs in cases:
            with self.subTest(source=source, cid=cid, kwargs=kwargs), patch('title_history.readonly') as read:
                with self.assertRaises(ValueError):
                    history(self.root / 'missing.sqlite', source, cid, **kwargs)
                read.assert_not_called()
        self.assertFalse((self.root / 'missing.sqlite').exists())

    def test_stale_page_guard_including_noop_changes(self):
        self.rename('First')
        self.rename('Second')
        page = self.read(limit=1)
        self.rename('Second')
        before = self.db.read_bytes()
        with self.assertRaisesRegex(ValueError, 'stale title history'):
            self.read(limit=1, offset=page['next_offset'], expected_revision=page['revision'])
        with self.assertRaisesRegex(ValueError, 'stale title history'):
            self.read(expected_revision=2**100)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(self.read()['revision'], 3)

    def test_guard_is_not_invalidated_by_other_titles_or_imports(self):
        revision = self.rename('Current')
        self.seed(conversation='other')
        self.rename('Other', conversation='other')
        self.seed(message='m2', title='Second imported title')
        self.assertEqual(self.read(expected_revision=revision)['revision'], revision)
        self.assertEqual(self.read(expected_revision=revision)['total_changes'], 1)

    def test_metadata_only_sql_never_reads_message_body(self):
        self.rename('Chosen metadata title')
        def guarded(db):
            connection = readonly(db)
            def authorize(action, table, column, database, trigger):
                if action == sqlite3.SQLITE_READ and (table == 'messages_fts' or (table == 'messages' and column in ('text', 'role'))):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            connection.set_authorizer(authorize)
            return connection
        with patch('title_history.readonly', guarded):
            result = self.read()
        self.assertNotIn('SYNTHETIC_PRIVATE_BODY_SENTINEL', json.dumps(result))
        self.assertNotIn('suggested_title', result)
        self.assertFalse(result['contains_message_text'])

    def test_page_materialization_is_bounded(self):
        self.rename('Initial')
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.executemany('INSERT INTO title_history(source,conversation,previous,title) VALUES(?,?,?,?)',
                    [('demo', 'chat', 'Synthetic previous', 'Synthetic title ' + str(i)) for i in range(2000)])
        produced = []
        def guarded(db):
            connection = readonly(db)
            factory = connection.row_factory
            def counted(cursor, row):
                produced.append(1)
                if len(produced) > 20:
                    raise AssertionError('History page materialized unbounded rows')
                return factory(cursor, row)
            connection.row_factory = counted
            return connection
        with patch('title_history.readonly', guarded):
            result = self.read(limit=3, offset=100)
        self.assertEqual(result['total_changes'], 2001)
        self.assertEqual(len(result['changes']), 3)
        self.assertLessEqual(len(produced), 20)

    def test_wal_snapshot_keeps_title_count_and_page_coherent(self):
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        old_revision = self.rename('Old label')
        changed = []
        def traced(db):
            connection = readonly(db)
            def on_sql(sql):
                if not changed and sql.lstrip().upper().startswith('SELECT') and 'FROM title_history' in sql:
                    changed.append(True)
                    titles(self.db, 'demo', 'chat', 'Concurrent label', old_revision)
            connection.set_trace_callback(on_sql)
            return connection
        with patch('title_history.readonly', traced):
            result = self.read()
        self.assertEqual(changed, [True])
        self.assertEqual(result['display_title'], 'Old label')
        self.assertEqual(result['revision'], old_revision)
        self.assertEqual(result['total_changes'], 1)
        self.assertEqual([row['title'] for row in result['changes']], ['Old label'])
        self.assertEqual(self.read()['display_title'], 'Concurrent label')

    def test_history_selected_reversal_uses_current_lease_and_preserves_events(self):
        first = self.rename('Chosen first')
        self.rename('Mistaken second')
        result = self.read()
        target = next(row for row in result['changes'] if row['revision'] == first)
        restored = titles(self.db, 'demo', 'chat', target['title'], result['revision'])
        self.assertEqual(restored['display_title'], 'Chosen first')
        self.assertEqual(self.read()['total_changes'], 3)
        with self.assertRaisesRegex(ValueError, 'stale title preview'):
            titles(self.db, 'demo', 'chat', 'Mistaken second', result['revision'])
        self.assertEqual(self.read()['total_changes'], 3)

    def test_both_clis_ascii_and_web_local_workflow(self):
        for kind, fixture, cid in [('web', 'examples/web-export.json', 'synthetic-chat'),
                                   ('local', 'examples/local-session.jsonl', 'synthetic-local')]:
            import_export(self.db, kind, fixture, kind)
            revision = self.rename('합성 과수원 🌳', source=kind, conversation=cid)
            before = self.db.read_bytes()
            outputs = []
            for script, command in [('recap.py', ['title-history']), ('title_history.py', [])]:
                args = [sys.executable, script, '--db', str(self.db), *command, '--source', kind,
                        '--conversation', cid, '--limit', '1', '--offset', '0', '--expected-revision', str(revision)]
                result = subprocess.run(args, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.isascii())
                output = json.loads(result.stdout)
                self.assertEqual(output['display_title'], '합성 과수원 🌳')
                outputs.append(output)
                result = subprocess.run(args[:-1] + ['0'], capture_output=True, timeout=20)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'stale title history', result.stderr)
                self.assertNotIn(b'Traceback', result.stderr)
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(self.db.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
