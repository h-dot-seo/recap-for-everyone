"""Synthetic anchored archive-context regressions; no private sources or network."""
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

import conversation_view
from conversation_view import conversation
from conversation_search import find
from recap import ingest, readonly
from session_workflow import import_export, titles


class ConversationContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.path = self.root / 'synthetic.jsonl'
        self.ids = ['z-last', 'a-first', "quote'--", '한글 😀', 'middle', 'end', 'tail']
        rows = []
        for index, mid in enumerate(self.ids):
            rows.extend([
                dict(conversation_id='chat', message_id=mid, role='user', timestamp=str(100-index),
                     title='원래 제목', text=f'Synthetic private evidence marker{index}'),
                dict(conversation_id='unrelated', message_id=mid, role='assistant', timestamp=str(index),
                     title='Unrelated', text='DO NOT INCLUDE OTHER CONVERSATION')])
        self.path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        provenance = [dict(**r, origin_sha256='a'*64, origin_locator=f'node:{i}', parent_id=None)
                      for i, r in enumerate(rows)]
        ingest(self.db, 'primary', self.path, provenance=provenance)
        ingest(self.db, 'other', self.path, provenance=provenance)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('INSERT INTO export_occurrences VALUES (?, ?, ?, ?, ?, ?)',
                               ('primary', 'chat', self.ids[3], 'b'*64, 'second:occurrence', self.ids[2]))
        self.revision = titles(self.db, 'primary', 'chat', '검토 제목 📝', 0)['revision']

    def show(self, **options):
        return conversation(self.db, 'primary', 'chat', **options)

    def assert_window(self, anchor, before, after, options=None):
        full = self.show()
        result = self.show(around_message_id=self.ids[anchor], **(
            dict(before=before, after=after) if options is None else options))
        start, stop = max(0, anchor-before), min(len(self.ids), anchor+after+1)
        self.assertEqual(result['messages'], full['messages'][start:stop])
        self.assertEqual({k:v for k,v in result.items() if k not in ('messages', 'selection')},
                         {k:v for k,v in full.items() if k != 'messages'})
        selection = result['selection']
        for key, value in dict(mode='context', anchor_message_id=self.ids[anchor],
                               anchor_index=anchor-start, anchor_offset=anchor,
                               before=before, after=after, returned_before=anchor-start,
                               returned_after=stop-anchor-1, returned_messages=stop-start,
                               offset=start, omitted_before=start, omitted_after=len(self.ids)-stop,
                               next_offset=stop if stop < len(self.ids) else None).items():
            self.assertEqual(selection[key], value, key)
        self.assertTrue(selection['context_scope'])
        self.assertTrue(selection['warning'])
        return result

    def test_default_and_explicit_windows_preserve_insertion_order_and_summary(self):
        before = self.db.read_bytes(), self.path.read_bytes()
        self.assert_window(3, 2, 2, {})
        for anchor in (0, 1, 3, 6):
            for preceding, following in ((0, 0), (0, 2), (2, 0), (1, 3), (50, 50)):
                with self.subTest(anchor=anchor, before=preceding, after=following):
                    self.assert_window(anchor, preceding, following)
        self.assertEqual(before, (self.db.read_bytes(), self.path.read_bytes()))

    def test_independent_defaults_and_existing_modes(self):
        self.assert_window(3, 0, 2, dict(before=0))
        self.assert_window(3, 2, 0, dict(after=0))
        self.assertNotIn('selection', self.show())
        self.assertEqual(self.show(message_id=self.ids[3])['selection']['mode'], 'message')
        self.assertEqual(self.show(limit=2)['selection']['mode'], 'page')
        self.assertEqual(self.show(around_message_id=self.ids[3], before=0, after=0)['messages'],
                         self.show(message_id=self.ids[3])['messages'])

    def test_maximum_window_is_101_messages(self):
        records = [dict(conversation_id='large', message_id=f'm{i}', role='user', timestamp='t',
                        text=f'Synthetic {i}') for i in range(111)]
        path = self.root / 'large.jsonl'
        path.write_text(''.join(json.dumps(r)+'\n' for r in records), encoding='utf-8')
        ingest(self.db, 'primary', path)
        result = conversation(self.db, 'primary', 'large', around_message_id='m55', before=50, after=50)
        self.assertEqual([m['message_id'] for m in result['messages']], [f'm{i}' for i in range(5, 106)])
        self.assertEqual(result['selection']['omitted_before'], 5)
        self.assertEqual(result['selection']['omitted_after'], 5)
        self.assertEqual(result['selection']['next_offset'], 106)

    def test_invalid_context_arguments_fail_before_database_access(self):
        invalid = [dict(around_message_id=v) for v in ('', True, 1, [], {})]
        invalid += [dict(around_message_id=self.ids[3], **{key:v})
                    for key in ('before', 'after') for v in (-1, 51, True, False, 1.5, '2', [], {})]
        invalid += [dict(before=0), dict(after=0), dict(before=2, after=2),
                    dict(around_message_id=self.ids[3], message_id=self.ids[3]),
                    dict(around_message_id=self.ids[3], limit=1),
                    dict(around_message_id=self.ids[3], limit=1, offset=1),
                    dict(around_message_id=self.ids[3], offset=1)]
        with patch('conversation_view.readonly', side_effect=AssertionError('validation must precede open')):
            for options in invalid:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    self.show(**options)
            for source, cid in [(v, 'chat') for v in (None, '', '  ', 1, True, [], {})] + [
                    ('primary', v) for v in (None, '', 1, True, [], {})]:
                with self.subTest(source=source, cid=cid), self.assertRaises(ValueError):
                    conversation(self.db, source, cid, around_message_id=self.ids[3])

    def test_unknown_anchor_and_scope_are_clean_failures(self):
        for source, cid, anchor in [('primary', 'chat', 'missing'), ('primary', 'missing', self.ids[0]),
                                    ('missing', 'chat', self.ids[0]), ('primary', 'chat', "' OR 1=1 --")]:
            with self.subTest(source=source, cid=cid, anchor=anchor), self.assertRaises(ValueError):
                conversation(self.db, source, cid, around_message_id=anchor)
        other = conversation(self.db, 'other', 'chat', around_message_id=self.ids[3], before=0, after=0)
        self.assertEqual(other['revision'], 0)
        self.assertEqual(len(other['messages'][0]['export_provenance']), 1)
        self.assertEqual(len(self.show(around_message_id=self.ids[3], before=0, after=0)
                             ['messages'][0]['export_provenance']), 2)

    def test_accepted_identity_strings_are_not_trimmed(self):
        path = self.root / 'spaces.jsonl'
        record = dict(conversation_id=' chat ', message_id=' anchor ', role='user', timestamp='t', text='spaces')
        path.write_text(json.dumps(record)+'\n', encoding='utf-8')
        ingest(self.db, ' primary ', path)
        result = conversation(self.db, ' primary ', ' chat ', around_message_id=' anchor ')
        self.assertEqual(result['source'], ' primary ')
        self.assertEqual(result['conversation'], ' chat ')
        self.assertEqual(result['selection']['anchor_message_id'], ' anchor ')
        with self.assertRaises(ValueError):
            conversation(self.db, ' primary ', ' chat ', around_message_id='anchor')

    def test_only_window_bodies_and_provenance_materialize(self):
        fetched, queries = [], []
        def traced(db):
            connection = readonly(db)
            def factory(cursor, values):
                row = sqlite3.Row(cursor, values)
                fetched.append(dict(row))
                return row
            connection.row_factory = factory
            connection.set_trace_callback(queries.append)
            return connection
        with patch('conversation_view.readonly', traced):
            result = self.show(around_message_id=self.ids[3], before=1, after=1)
        wanted = self.ids[2:5]
        self.assertEqual([r['message_id'] for r in fetched if 'text' in r], wanted)
        evidence = [r for r in fetched if 'original_hash' in r]
        self.assertTrue(evidence)
        self.assertTrue(all(r['message'] in wanted for r in evidence))
        self.assertEqual(sum(q.strip().upper() == 'BEGIN' for q in queries), 1)
        self.assertNotIn('DO NOT INCLUDE', json.dumps(result))

    def test_legacy_and_absent_provenance_tables(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('DROP TABLE export_occurrences')
        result = self.show(around_message_id=self.ids[3])
        self.assertTrue(all(len(m['export_provenance']) == 1 for m in result['messages']))
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('DROP TABLE export_provenance')
            connection.execute('DROP TABLE title_history')
        result = self.show(around_message_id=self.ids[3])
        self.assertTrue(all(m['export_provenance'] == [] for m in result['messages']))
        self.assertEqual(result['revision'], 0)

    def test_snapshot_survives_concurrent_changes_after_window_selection(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        expected = self.show(around_message_id=self.ids[3], before=1, after=1)
        original = conversation_view._context_window
        changed = []
        def concurrent(*args, **kwargs):
            window = original(*args, **kwargs)
            with closing(sqlite3.connect(self.db)) as writer, writer:
                writer.execute("UPDATE messages SET text='Later changed text' WHERE source_id='primary'")
                writer.execute("UPDATE title_history SET title='Later title' WHERE source='primary'")
                writer.execute("DELETE FROM export_occurrences WHERE source='primary'")
                writer.execute("DELETE FROM export_provenance WHERE source='primary'")
            changed.append(True)
            return window
        with patch('conversation_view._context_window', concurrent):
            actual = self.show(around_message_id=self.ids[3], before=1, after=1)
        self.assertEqual(changed, [True])
        self.assertEqual(actual, expected)
        later = self.show(around_message_id=self.ids[3], before=1, after=1)
        self.assertEqual(later['display_title'], 'Later title')
        self.assertTrue(all(m['text'] == 'Later changed text' and not m['export_provenance'] for m in later['messages']))

    def test_both_cli_routes_match_api_on_ascii_stdout(self):
        environment = dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0')
        before = self.db.read_bytes(), self.path.read_bytes()
        for args, options in [([], {}), (['--before', '0', '--after', '1'], dict(before=0, after=1))]:
            expected = self.show(around_message_id=self.ids[3], **options)
            for script in ('recap.py', 'conversation_view.py'):
                result = subprocess.run([sys.executable, script, '--db', str(self.db), 'show', '--source',
                                         'primary', '--conversation', 'chat', '--around-message', self.ids[3], *args],
                                        capture_output=True, env=environment, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr.decode('ascii'))
                self.assertEqual(json.loads(result.stdout.decode('ascii')), expected)
        self.assertEqual(before, (self.db.read_bytes(), self.path.read_bytes()))

    def test_cli_invalid_context_does_not_create_missing_database(self):
        missing = self.root / 'missing.sqlite'
        for script in ('recap.py', 'conversation_view.py'):
            for args in (['--before', '0'], ['--around-message', 'x', '--after', '51'],
                         ['--around-message', 'x', '--message', 'x'],
                         ['--around-message', 'x', '--limit', '1']):
                with self.subTest(script=script, args=args):
                    result = subprocess.run([sys.executable, script, '--db', str(missing), 'show',
                                             '--source', 'primary', '--conversation', 'chat', *args],
                                            capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, '')
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertFalse(missing.exists())

    def test_export_filtered_search_does_not_filter_context_neighbors(self):
        hit = find(self.db, 'marker3', source='primary', export_sha256='b'*64)['matches'][0]
        sample = hit['message_matches'][0]
        result = conversation(self.db, hit['source_id'], hit['conversation_id'],
                              around_message_id=sample['message_id'], before=1, after=1)
        self.assertEqual([m['message_id'] for m in result['messages']], self.ids[2:5])
        self.assertEqual({p['original_sha256'] for p in result['messages'][0]['export_provenance']}, {'a'*64})
        self.assertEqual({p['original_sha256'] for p in result['messages'][1]['export_provenance']},
                         {'a'*64, 'b'*64})
        self.assertIn('no branch, replay or original-export filter', result['selection']['context_scope'])
        self.assertIn('alternate branches', result['selection']['warning'])

    def test_synthetic_web_and_local_find_context_explicit_title_review(self):
        for source, path, fmt, query in [('web', 'examples/web-export.json', 'web', 'orchard'),
                                         ('local', 'examples/local-session.jsonl', 'local', 'orchard')]:
            with self.subTest(source=source):
                source_bytes = Path(path).read_bytes()
                import_export(self.db, source, path, fmt)
                hits = find(self.db, query, source=source)['matches']
                self.assertTrue(hits)
                hit = hits[0]
                sample = hit['message_matches'][0]
                before = conversation(self.db, source, hit['conversation_id'], around_message_id=sample['message_id'])
                anchor = before['messages'][before['selection']['anchor_index']]
                self.assertEqual(anchor['message_id'], sample['message_id'])
                self.assertEqual(anchor['source_sha256'], sample['source_sha256'])
                self.assertEqual(anchor['source_line'], sample['source_line'])
                revision = titles(self.db, source, hit['conversation_id'], 'Explicitly reviewed orchard context',
                                  before['revision'])['revision']
                after = conversation(self.db, source, hit['conversation_id'], around_message_id=sample['message_id'])
                self.assertEqual(after['revision'], revision)
                self.assertEqual(after['messages'], before['messages'])
                self.assertEqual(after['selection'], before['selection'])
                self.assertEqual(Path(path).read_bytes(), source_bytes)


if __name__ == '__main__':
    unittest.main()
