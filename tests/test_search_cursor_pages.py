"""Synthetic, read-only cursor pagination regressions. No private exports or APIs."""
import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from recaplib import conversation_search
from recaplib.conversation_search import find
from recap import ingest
from recaplib.session_workflow import titles


class SearchCursorPagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.counter = 0

    def seed(self, rows, source='synthetic', digest=None):
        self.counter += 1
        path = self.root / f'input-{self.counter}.jsonl'
        records = [dict(conversation_id=cid, message_id=f'm-{i}', role='user',
                        timestamp='synthetic', title=title, text=text)
                   for i, (cid, title, text) in enumerate(rows)]
        path.write_text(''.join(json.dumps(row, ensure_ascii=True) + '\n' for row in records), encoding='utf-8')
        provenance = None if digest is None else [dict(**row, origin_sha256=digest,
            origin_locator=f'synthetic:{i}', parent_id=None) for i, row in enumerate(records)]
        ingest(self.db, source, path, provenance=provenance)
        return path

    @staticmethod
    def decode(token):
        return json.loads(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)))

    @staticmethod
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode()).decode().rstrip('=')

    @staticmethod
    def identities(result):
        return [(item['source_id'], item['conversation_id']) for item in result['matches']]

    def page(self, **kwargs):
        return find(self.db, 'needle', **kwargs)

    def mutate(self, sql, params=()):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute(sql, params)

    def test_mixed_ranking_sources_history_and_page_counters(self):
        for source in ('z-source', 'a-source'):
            self.seed([('body', 'Other', 'needle'), ('history', 'needle old', 'Other'),
                       ('title', 'needle current', 'Other')], source)
            titles(self.db, source, 'history', 'Renamed', 0)
        expected = [('a-source', 'title'), ('z-source', 'title'),
                    ('a-source', 'history'), ('z-source', 'history'),
                    ('a-source', 'body'), ('z-source', 'body')]
        before = self.db.read_bytes()
        cursor = None
        all_hits = []
        for offset in (0, 2, 4):
            page = self.page(limit=2, include_title_history=True, cursor=cursor)
            all_hits.extend(self.identities(page))
            self.assertEqual(page['total_matches'], 6)
            self.assertEqual(page['skipped_matches'], offset)
            self.assertEqual(page['remaining_matches'], 6-offset-2)
            self.assertEqual(page['truncated'], offset < 4)
            cursor = page['next_cursor']
            if offset < 4:
                payload = self.decode(cursor)
                self.assertEqual(payload['rank'], offset // 2)
                self.assertEqual(payload['source'], 'z-source')
                self.assertEqual(payload['conversation'], expected[offset+1][1])
                self.assertEqual(len(payload['order_sha256']), 64)
        self.assertIsNone(cursor)
        self.assertEqual(all_hits, expected)
        self.assertEqual(self.db.read_bytes(), before)

    def test_beyond_thousand_and_limit_can_change(self):
        self.seed([(f'chat-{i:04}', 'Other', 'needle') for i in range(1207)])
        first = self.page(limit=1000)
        second = self.page(limit=113, cursor=first['next_cursor'])
        third = self.page(limit=1000, cursor=second['next_cursor'])
        self.assertEqual([len(p['matches']) for p in (first, second, third)], [1000, 113, 94])
        self.assertEqual([p['skipped_matches'] for p in (first, second, third)], [0, 1000, 1113])
        self.assertEqual([p['remaining_matches'] for p in (first, second, third)], [207, 94, 0])
        identities = sum((self.identities(p) for p in (first, second, third)), [])
        self.assertEqual(len(set(identities)), 1207)
        self.assertEqual(identities, sorted(identities))
        self.assertIsNone(third['next_cursor'])

    def test_unicode_quoted_control_identities_and_deterministic_token(self):
        source = '합성/"source\n'
        ids = ['a" OR 1=1 --', 'line\nbreak', 'é', '한글', '🦉']
        self.seed([(cid, 'Other', 'needle') for cid in ids], source)
        first = self.page(limit=1)
        self.assertEqual(first, self.page(limit=1))
        actual = self.identities(first)
        while first['next_cursor']:
            first = self.page(limit=1, cursor=first['next_cursor'])
            actual.extend(self.identities(first))
        self.assertEqual(actual, [(source, cid) for cid in sorted(ids)])

    def test_equivalent_query_scope_and_different_scopes_rejected_before_db(self):
        self.seed([(str(i), 'Other', 'Straße needle') for i in range(4)])
        first = find(self.db, 'STRASSE needle needle', limit=1)
        token = first['next_cursor']
        second = find(self.db, '  straße\tNEEDLE ', limit=2, cursor=token)
        self.assertEqual(second['skipped_matches'], 1)
        with patch.object(conversation_search, 'readonly', side_effect=AssertionError('DB must not open')):
            for kwargs in ({'source': 'synthetic'}, {'include_title_history': True},
                           {'export_sha256': '0'*64}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    find(self.db, 'strasse needle', cursor=token, **kwargs)
            with self.assertRaises(ValueError):
                find(self.db, 'different', cursor=token)
            with self.assertRaises(ValueError):
                find(self.db, 'needle strasse', cursor=token)

    def test_malformed_tokens_and_payloads_rejected_before_database(self):
        self.seed([('a', 'Other', 'needle'), ('b', 'Other', 'needle')])
        token = self.page(limit=1)['next_cursor']
        payload = self.decode(token)
        bad = [True, 123, [], {}, '', '!', 'not base64', 'a'*16385,
               self.encode([]), self.encode(None), self.encode({'secret': 'PRIVATE_MARKER'})]
        for key in payload:
            altered = dict(payload)
            del altered[key]
            bad.append(self.encode(altered))
        for key, value in [('rank', True), ('rank', 3), ('rank', '0'),
                           ('source', None), ('source', '\ud800'), ('conversation', []),
                           ('scope_sha256', 'A'*64), ('order_sha256', 'z'*64),
                           ('extra', 'PRIVATE_MARKER')]:
            altered = dict(payload); altered[key] = value
            bad.append(self.encode(altered))
        version_key = 'v' if 'v' in payload else 'version'
        for version in (True, 2, '1'):
            altered = dict(payload); altered[version_key] = version
            bad.append(self.encode(altered))
        raw = json.dumps(payload)
        duplicate = raw[:-1] + ',"source":"PRIVATE_MARKER"}'
        bad.append(base64.urlsafe_b64encode(duplicate.encode()).decode().rstrip('='))
        bad.append(base64.urlsafe_b64encode(b'\xff\xfe').decode().rstrip('='))
        with patch.object(conversation_search, 'readonly', side_effect=AssertionError('DB must not open')):
            for value in bad:
                with self.subTest(token_type=type(value).__name__, token_length=len(value) if isinstance(value, str) else None):
                    with self.assertRaises(ValueError) as error:
                        self.page(cursor=value)
                    self.assertNotIn('PRIVATE_MARKER', str(error.exception))
                    self.assertNotIn(token, str(error.exception))

    def test_missing_position_and_stale_membership_or_rank_require_restart(self):
        self.seed([('a', 'Other', 'needle'), ('b', 'Other', 'needle'), ('c', 'Other', 'needle')])
        token = self.page(limit=1)['next_cursor']
        payload = self.decode(token); payload['conversation'] = 'nonexistent'
        with self.assertRaises(ValueError):
            self.page(cursor=self.encode(payload))
        self.mutate("UPDATE messages SET text='unrelated' WHERE conversation_id='c'")
        with self.assertRaises(ValueError):
            self.page(cursor=token)
        token = self.page(limit=1)['next_cursor']
        self.mutate("UPDATE messages SET title='needle current' WHERE conversation_id='b'")
        with self.assertRaises(ValueError):
            self.page(cursor=token)

    def test_fresh_wording_without_membership_or_rank_change_is_allowed(self):
        self.seed([('a', 'Other', 'needle first'), ('b', 'Other', 'needle old')])
        token = self.page(limit=1)['next_cursor']
        self.mutate("UPDATE messages SET text='needle fresh evidence',title='Reworded title' WHERE conversation_id='b'")
        second = self.page(limit=1, cursor=token)
        self.assertEqual(second['matches'][0]['display_title'], 'Reworded title')
        self.assertEqual(second['matches'][0]['message_matches'][0]['snippet'], 'needle fresh evidence')
        self.assertIsNone(second['next_cursor'])

    def test_no_matches_and_exact_limit_have_no_next_cursor(self):
        self.seed([('a', 'Other', 'needle'), ('b', 'Other', 'needle')])
        for query, count in [('needle', 2), ('absent', 0)]:
            page = find(self.db, query, limit=2)
            self.assertEqual(page['total_matches'], count)
            self.assertEqual(page['skipped_matches'], 0)
            self.assertEqual(page['remaining_matches'], 0)
            self.assertFalse(page['truncated'])
            self.assertIsNone(page['next_cursor'])

    def test_large_identity_preserves_first_page_with_explicit_blocker(self):
        self.seed([('a'*20000, 'Other', 'needle'), ('z', 'Other', 'needle')])
        page = self.page(limit=1)
        self.assertEqual(len(page['matches']), 1)
        self.assertEqual(page['total_matches'], 2)
        self.assertEqual(page['remaining_matches'], 1)
        self.assertTrue(page['truncated'])
        self.assertIsNone(page['next_cursor'])
        self.assertEqual(page['pagination_blocker'], 'CURSOR_IDENTITY_TOO_LARGE')

    def test_raw_and_export_scoped_pages_preserve_provenance_and_snippets(self):
        digest = 'a'*64
        path = self.seed([(str(i), 'Other', 'x'*300+' needle evidence '+str(i)) for i in range(3)], digest=digest)
        raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        before = (self.db.read_bytes(), path.read_bytes())
        for kwargs in ({}, {'export_sha256': digest}):
            first = self.page(limit=1, **kwargs)
            page = self.page(limit=1, cursor=first['next_cursor'], **kwargs)
            match = page['matches'][0]['message_matches'][0]
            self.assertEqual(match['source_sha256'], raw_hash)
            self.assertEqual(match['source_line'], 2)
            self.assertIn('needle', match['snippet'])
            self.assertTrue(match['snippet_truncated_before'])
            if kwargs:
                self.assertEqual(match['export_provenance'][0]['original_sha256'], digest)
                self.assertEqual(match['export_provenance'][0]['locator'], 'synthetic:1')
        self.assertEqual(before, (self.db.read_bytes(), path.read_bytes()))

    def test_one_scan_no_offset_or_writes_and_wal_snapshot_binds_cursor(self):
        self.seed([(str(i), 'Other', 'needle old') for i in range(5)])
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('PRAGMA journal_mode=WAL')
        original = conversation_search.readonly
        statements = []; changed = []
        def reader(path):
            c = original(path)
            def trace(sql):
                statements.append(sql)
                if sql.startswith('SELECT * FROM messages') and not changed:
                    changed.append(True)
                    self.mutate("UPDATE messages SET text='no longer matching' WHERE conversation_id='4'")
            c.set_trace_callback(trace)
            return c
        with patch.object(conversation_search, 'readonly', reader):
            first = self.page(limit=2)
        self.assertEqual(changed, [True])
        self.assertEqual(first['total_matches'], 5)
        self.assertEqual(first['remaining_matches'], 3)
        self.assertEqual(sum(sql.startswith('SELECT * FROM messages') for sql in statements), 1)
        self.assertEqual(sum(sql.strip().upper() == 'BEGIN' for sql in statements), 1)
        self.assertFalse(any(' OFFSET ' in sql.upper() for sql in statements))
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ', 'CREATE ', 'DROP ')) for sql in statements))
        with self.assertRaises(ValueError):
            self.page(cursor=first['next_cursor'])
        self.assertEqual(self.page()['total_matches'], 4)

    def test_late_page_retention_does_not_grow_with_skipped_hits(self):
        # Large synthetic titles make retaining skipped result dictionaries visible.
        # Trace only the final read, never fixture generation or earlier pages.
        self.seed([(f'chat-{i:04}', 'needle ' + 'x'*4096, 'Other') for i in range(2200)])
        first = self.page(limit=1000)
        second = self.page(limit=1000, cursor=first['next_cursor'])
        token = second['next_cursor']
        del first, second
        tracemalloc.start()
        try:
            late = self.page(limit=1, cursor=token)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(late['skipped_matches'], 2000)
        self.assertEqual(late['matches'][0]['conversation_id'], 'chat-2000')
        self.assertLess(peak, 1024*1024,
                        'one-hit late page must not retain thousands of skipped titles/results')

    def test_both_clis_accept_cursor_and_repeat_deterministically(self):
        self.seed([('a', 'Other', 'needle'), ('한글', 'Other', 'needle'), ('🦉', 'Other', 'needle')])
        token = self.page(limit=1)['next_cursor']
        expected = self.page(limit=1, cursor=token)
        before = self.db.read_bytes()
        env = dict(os.environ, PYTHONIOENCODING='ascii')
        outputs = []
        for script, command in [('conversation_search.py', []), ('recap.py', ['find'])]:
            args = [sys.executable, script, '--db', str(self.db), *command,
                    'needle', '--limit', '1', '--cursor', token]
            for _ in range(2):
                process = subprocess.run(args, capture_output=True, env=env, timeout=20)
                self.assertEqual(process.returncode, 0, process.stderr)
                outputs.append(process.stdout)
                self.assertEqual(json.loads(process.stdout.decode('ascii')), expected)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[2], outputs[3])
        self.assertEqual(self.db.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
