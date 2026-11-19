"""Scoped find pages use the same body evidence as ordinary conversation search."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from recaplib import conversation_search as search
from recaplib.archive import ingest_bytes
from recaplib.errors import UnknownIdentity
from recaplib.session_workflow import import_export


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'examples' / 'message-review-local.jsonl'


class MatchingMessagePageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / 'archive.sqlite'

    def seed(self):
        # Insertion and lexicographic order differ; the same IDs occur in other scopes.
        records = [('c', 'z', 'Straße', 'user'), ('other', 'decoy', 'Straße', 'user'),
                   ('c', 'gap', 'unrelated', 'assistant'), ('c', 'a', 'prefix %_ end', 'assistant'),
                   ('c', 'm', 'x' * 300 + 'cafe\u0301', 'user')]
        rows = [dict(conversation_id=cid, message_id=mid, role=role, text=body,
                     title='titleonly', timestamp='2026-01-01T00:00:00Z') for cid, mid, body, role in records]
        raw = ''.join(json.dumps(r) + '\n' for r in rows).encode()
        for source in ('demo', 'Demo'):
            ingest_bytes(self.db, source, raw)
        return hashlib.sha256(raw).hexdigest()

    def page(self, query, **options):
        return search.find(self.db, query, source='demo', conversation='c', **options)

    def test_literal_any_term_scope_order_and_excerpt_parity(self):
        digest = self.seed()
        query = 'STRASSE %_ CAFÉ strasse'
        original = search.find(self.db, query, source='demo', canonical_unicode=True)
        item, = original['matches']
        first = self.page(query, canonical_unicode=True, limit=2)
        last = self.page(query, canonical_unicode=True, offset=first['next_offset'], limit=2)
        self.assertEqual(first['message_match_count'], 3)
        self.assertEqual(last['message_match_count'], 3)
        self.assertEqual(first['next_offset'], 2)
        self.assertIsNone(last['next_offset'])
        self.assertEqual(first['terms'], ['strasse', '%_', 'café'])
        matches = first['message_matches'] + last['message_matches']
        self.assertEqual(matches, item['message_matches'])
        self.assertEqual([m['message_id'] for m in matches], ['z', 'a', 'm'])
        self.assertEqual([m['source_line'] for m in matches], [1, 4, 5])
        self.assertTrue(all(m['source_sha256'] == digest and 'text' not in m for m in matches))
        self.assertEqual(matches[0]['first_match']['end'], 6)
        self.assertEqual(matches[-1]['first_match'], dict(term='café', start=300, end=305, fully_visible=True))
        self.assertEqual(self.page(query)['message_match_count'], 2)
        self.assertEqual(self.page('titleonly')['message_matches'], [])
        self.assertEqual(self.page('absent STRASSE')['message_match_count'], 1)
        beyond = self.page(query, canonical_unicode=True, offset=2**63-1)
        self.assertEqual(beyond['message_matches'], [])
        self.assertIsNone(beyond['next_offset'])

    def test_fixture_walkthrough_and_cli_parity(self):
        import_export(self.db, 'demo', FIXTURE, 'local-codex')
        cid = 'synthetic-message-review'
        before = self.db.read_bytes()
        args = ['cobalt orchard', '--source', 'demo', '--conversation', cid, '--limit', '20']
        expected = [f'status-{i:02d}' for i in range(65)] + ['focus-user']
        offset, ids = 0, []
        while offset is not None:
            page = search.find(self.db, args[0], 'demo', conversation=cid, limit=20, offset=offset)
            self.assertEqual(page['message_match_count'], len(expected))
            ids.extend(m['message_id'] for m in page['message_matches'])
            offset = page['next_offset']
            self.assertEqual(offset, len(ids) if len(ids) < len(expected) else None)
        self.assertEqual(ids, expected)
        args += ['--offset', '60']
        for script, verb in [('recap.py', ['find']), ('conversation_search.py', [])]:
            run = subprocess.run([sys.executable, str(ROOT / script), '--db', str(self.db), *verb, *args],
                                 capture_output=True, text=True, check=True, timeout=20)
            self.assertEqual(json.loads(run.stdout), page)
        user = search.find(self.db, args[0], 'demo', conversation=cid, text_role='user')
        self.assertEqual([m['message_id'] for m in user['message_matches']], ['focus-user'])
        self.assertEqual(self.db.read_bytes(), before)

    def test_export_role_date_filters_and_off_page_excerpt_budget(self):
        digest = 'a' * 64
        records = [('skip', 'user', '2026-01-01', digest), ('visible', 'user', '2026-01-01', digest),
                   ('later', 'user', '2026-01-01', digest), ('wrong-role', 'assistant', '2026-01-01', digest),
                   ('wrong-date', 'user', '2026-01-02', digest), ('wrong-export', 'user', '2026-01-01', 'b' * 64)]
        rows, provenance = [], []
        for mid, role, date, origin in records:
            rows.append(dict(conversation_id='c', message_id=mid, role=role, text='needle',
                             timestamp=date + 'T00:00:00Z'))
            provenance.append(dict(conversation_id='c', message_id=mid, origin_sha256=origin,
                                   origin_locator='locator-' + mid, parent_id=None))
        ingest_bytes(self.db, 'demo', ''.join(json.dumps(r) + '\n' for r in rows).encode(), provenance=provenance)
        filters = dict(text_role='user', from_date='2026-01-01', until_date='2026-01-01', export_sha256=digest)
        ordinary = search.find(self.db, 'needle', 'demo', **filters)['matches'][0]
        with patch.object(search, '_matching_excerpt', wraps=search._matching_excerpt) as excerpts, \
                patch.object(search, '_matching_export_provenance', wraps=search._matching_export_provenance) as locators:
            page = self.page('needle', limit=1, offset=1, **filters)
        excerpts.assert_called_once()
        locators.assert_called_once()
        self.assertEqual(page['message_match_count'], ordinary['message_match_count'])
        self.assertEqual(page['message_matches'], ordinary['message_matches'][1:2])
        self.assertEqual(page['message_matches'][0]['export_provenance'][0]['locator'], 'locator-visible')
        self.assertEqual(page['next_offset'], 2)
        self.assertEqual(self.page('needle', export_sha256='c' * 64)['message_match_count'], 0)

    def test_argument_bounds_and_exact_identity(self):
        for options in (dict(offset=0), dict(conversation='c'), dict(conversation='c', source=' '),
                        dict(source='demo', conversation=''), dict(conversation=2, source='demo')):
            with self.subTest(options=options), self.assertRaises(ValueError):
                search.find(self.db, 'needle', **options)
        for options in (dict(cursor=''), dict(include_title_history=True), dict(limit=0), dict(limit=1001),
                        dict(offset=-1), dict(offset=True), dict(offset=2**63)):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.page('needle', **options)
        self.assertFalse(self.db.exists())
        self.seed()
        with self.assertRaises(UnknownIdentity):
            search.find(self.db, 'Straße', 'demo', conversation='C')
        with self.assertRaises(UnknownIdentity):
            search.find(self.db, 'Straße', 'DEMO', conversation='c')

    def test_snapshot_during_scan_and_fresh_next_page(self):
        self.seed()
        with closing(sqlite3.connect(self.db)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
            readonly = search.readonly
            def open_reader(path):
                connection = readonly(path)
                def trace(sql):
                    if sql.startswith('SELECT * FROM messages'):
                        writer.execute("UPDATE messages SET text='Straße' WHERE message_id='gap'")
                        writer.commit()
                connection.set_trace_callback(trace)
                return connection
            with patch.object(search, 'readonly', open_reader):
                self.assertEqual(self.page('strasse')['message_match_count'], 1)
        later = self.page('strasse', offset=1)
        self.assertEqual(later['message_match_count'], 2)
        self.assertEqual([m['message_id'] for m in later['message_matches']], ['gap'])


if __name__ == '__main__':
    unittest.main()
