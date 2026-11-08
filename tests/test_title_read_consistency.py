"""Synthetic regression coverage for shared title excerpts and read snapshots."""
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

from recap import ingest
from recaplib.session_workflow import titles
from recaplib.title_suggestion import suggest


class TitleReadConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.export = self.root / 'synthetic.jsonl'

    def seed(self, texts, source='synthetic', conversation='chat'):
        records = [dict(conversation_id=conversation, message_id=f'm-{i}',
                        role=role, text=text, title='Synthetic original', timestamp='synthetic')
                   for i, (role, text) in enumerate(texts)]
        self.export.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
        ingest(self.db, source, self.export)

    def read(self, source='synthetic'):
        return titles(self.db, source, 'chat')

    def proposal(self, source='synthetic'):
        return suggest(self.db, source, 'chat')

    def test_greeting_skipped_and_non_user_message_indexes_preserved(self):
        self.seed([('system', 'Synthetic system'), ('user', 'Hello!'),
                   ('assistant', 'Synthetic reply'), ('user', 'Plan a synthetic orchard experiment')])
        result = self.proposal()
        self.assertEqual(result['title'], 'Plan a synthetic orchard experiment')
        self.assertEqual(result['evidence_message_ids'], ['m-3'])
        self.assertEqual(result['selection_method'], 'first_non_greeting_user_excerpt')
        self.assertEqual(self.read()['suggested_title'], result['title'])

    def test_korean_greeting_and_controls_cleaned_only_in_label(self):
        text = '\x00합성\u200b 실험\n  결과\t정리\x1b'
        self.seed([('user', '안녕하세요!'), ('user', text)])
        before = self.db.read_bytes(), self.export.read_bytes()
        self.assertEqual(self.read()['suggested_title'], '합성 실험 결과 정리')
        self.assertEqual(self.read()['suggested_title'], self.proposal()['title'])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT text FROM messages WHERE message_id='m-1'").fetchone()[0], text)
        self.assertEqual(before, (self.db.read_bytes(), self.export.read_bytes()))

    def test_long_excerpt_truncation_and_trailing_space_match(self):
        text = 'x' * 79 + ' ' + 'synthetic continuation'
        self.seed([('user', text)])
        self.assertEqual(self.read()['suggested_title'], 'x' * 79)
        self.assertEqual(self.read()['suggested_title'], self.proposal()['title'])
        self.assertTrue(self.proposal()['truncated'])

    def test_greeting_only_uses_first_usable_greeting(self):
        self.seed([('user', '\x00 !!!'), ('user', ' Hello! '), ('user', '안녕하세요!')])
        self.assertEqual(self.read()['suggested_title'], 'Hello!')
        proposal = self.proposal()
        self.assertEqual(proposal['title'], 'Hello!')
        self.assertEqual(proposal['evidence_message_ids'], ['m-1'])
        self.assertEqual(proposal['selection_method'], 'first_user_greeting_fallback')

    def test_no_usable_user_text_is_informational_fallback_not_proposal(self):
        for rows in ([('assistant', 'Synthetic answer')],
                     [('user', '\x00\u200b \n'), ('user', '...!?')]):
            with self.subTest(rows=rows):
                self.seed(rows, conversation='unusable-' + str(len(rows)))
                cid = 'unusable-' + str(len(rows))
                before = self.db.read_bytes()
                result = titles(self.db, 'synthetic', cid)
                self.assertEqual(result['suggested_title'], 'Untitled conversation')
                self.assertEqual(result['display_title'], 'Synthetic original')
                self.assertEqual(result['revision'], 0)
                self.assertEqual(result['prior_titles'], [])
                with self.assertRaisesRegex(ValueError, 'no usable user text'):
                    suggest(self.db, 'synthetic', cid)
                self.assertEqual(before, self.db.read_bytes())

    def test_read_and_write_receipts_preserve_original_history_and_sources(self):
        self.seed([('user', 'Hello!'), ('user', 'Synthetic meaningful request')])
        self.seed([('user', 'Separate synthetic source')], source='other')
        expected = self.proposal()['title']
        first = titles(self.db, 'synthetic', 'chat', 'Reviewed one', 0)
        second = titles(self.db, 'synthetic', 'chat', 'Reviewed two', first['revision'])
        read = self.read()
        for receipt in (first, second, read):
            self.assertEqual(receipt['suggested_title'], expected)
            self.assertEqual(receipt['original_title'], 'Synthetic original')
            self.assertEqual(receipt['scope'], 'local display only')
        self.assertEqual(first['prior_titles'], [])
        self.assertEqual(second['prior_titles'], ['Reviewed one'])
        self.assertEqual(read['prior_titles'], ['Reviewed one', 'Reviewed two'])
        self.assertEqual(read['display_title'], 'Reviewed two')
        self.assertEqual(read['revision'], second['revision'])
        self.assertEqual(self.read('other')['suggested_title'], 'Separate synthetic source')
        self.assertEqual(self.read('other')['revision'], 0)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT DISTINCT title FROM messages').fetchall(), [('Synthetic original',)])

    def test_source_name_does_not_filter_raw_user_excerpt(self):
        for source in ('web', 'local-codex', 'mixed-synthetic'):
            self.seed([('user', 'Hello!'), ('user', 'Raw synthetic user request')], source=source)
            self.assertEqual(self.read(source)['suggested_title'], self.proposal(source)['title'])
            self.assertEqual(self.read(source)['suggested_title'], 'Raw synthetic user request')

    def test_ascii_cli_parity_and_no_read_mutation(self):
        self.seed([('user', '안녕하세요!'), ('user', '합성\u200b 실험 검토')])
        before = self.db.read_bytes(), self.export.read_bytes()
        env = dict(os.environ, PYTHONIOENCODING='ascii')
        outputs = []
        for script, command in (('recap.py', ['title']), ('session_workflow.py', ['title']),
                                ('recap.py', ['suggest-title']), ('title_suggestion.py', [])):
            args = [sys.executable, script, '--db', str(self.db), *command,
                    '--source', 'synthetic', '--conversation', 'chat']
            result = subprocess.run(args, capture_output=True, env=env, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(json.loads(result.stdout.decode('ascii')))
        expected = '합성 실험 검토'
        self.assertEqual([item.get('suggested_title', item.get('title')) for item in outputs], [expected] * 4)
        self.assertEqual(before, (self.db.read_bytes(), self.export.read_bytes()))

    def test_missing_database_not_created_and_unknown_conversation_read_only(self):
        missing = self.root / 'missing.sqlite'
        for operation in (titles, suggest):
            with self.assertRaises(sqlite3.Error):
                operation(missing, 'synthetic', 'chat')
            self.assertFalse(missing.exists())
        self.seed([('user', 'Synthetic request')])
        before = self.db.read_bytes()
        with self.assertRaisesRegex(ValueError, 'unknown conversation'):
            titles(self.db, 'synthetic', 'missing')
        self.assertEqual(before, self.db.read_bytes())

    def test_wal_concurrent_content_title_revision_history_use_one_snapshot(self):
        from recaplib import session_workflow
        self.seed([('user', 'Hello!'), ('user', 'Old synthetic request')])
        first = titles(self.db, 'synthetic', 'chat', 'Old reviewed title', 0)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        real_readonly = session_workflow.readonly
        changed = []

        def mutate():
            with closing(sqlite3.connect(self.db)) as connection, connection:
                connection.execute("UPDATE messages SET text='New synthetic request' WHERE message_id='m-1'")
                connection.execute("UPDATE messages SET title='New synthetic original'")
                changed.append(connection.execute(
                    'INSERT INTO title_history(source,conversation,previous,title) VALUES(?,?,?,?)',
                    ('synthetic', 'chat', 'Old reviewed title', 'New reviewed title')).lastrowid)

        class CursorProxy:
            def __init__(self, cursor):
                self.cursor = cursor
            def fetchall(self):
                rows = self.cursor.fetchall()
                mutate()
                return rows

        class ConnectionProxy:
            def __init__(self, connection):
                self.connection = connection
            def execute(self, sql, *args):
                cursor = self.connection.execute(sql, *args)
                if sql.startswith('SELECT role,text,title'):
                    return CursorProxy(cursor)
                return cursor
            def close(self):
                self.connection.close()

        with patch.object(session_workflow, 'readonly', lambda db: ConnectionProxy(real_readonly(db))):
            old = self.read()
        self.assertEqual(len(changed), 1, 'concurrent write hook must execute')
        self.assertEqual(old['suggested_title'], 'Old synthetic request')
        self.assertEqual(old['original_title'], 'Synthetic original')
        self.assertEqual(old['display_title'], 'Old reviewed title')
        self.assertEqual(old['revision'], first['revision'])
        self.assertEqual(old['prior_titles'], ['Old reviewed title'])
        new = self.read()
        self.assertEqual(new['suggested_title'], 'New synthetic request')
        self.assertEqual(new['original_title'], 'New synthetic original')
        self.assertEqual(new['display_title'], 'New reviewed title')
        self.assertEqual(new['revision'], changed[0])
        self.assertEqual(new['prior_titles'], ['Old reviewed title', 'New reviewed title'])
