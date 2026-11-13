"""Synthetic characterization of the existing normalized JSONL contract."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from recaplib.archive import ingest_bytes
from recaplib.conversation_view import conversations
from recaplib.conversation_search import find


class NormalizedContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'archive.sqlite'

    def row(self, **changes):
        row = dict(conversation_id='fictional-chat', message_id='fictional-request',
                   role='user', timestamp='fictional time', text='Synthetic orchard question')
        row.update(changes)
        return row

    def encode(self, *rows):
        return ('\n'.join(json.dumps(row) for row in rows) + '\n').encode()

    def query(self, sql):
        with closing(sqlite3.connect(self.db)) as connection:
            return connection.execute(sql).fetchall()

    def test_ignored_members_and_nonfinite_values(self):
        raw = self.encode(self.row(origin_sha256='a'*64, origin_locator='fictional:1',
                                   unused=float('nan'), source='ignored', schema='ignored'))
        receipt = ingest_bytes(self.db, 'synthetic', raw)
        self.assertEqual(receipt['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.query('SELECT source_id,source_sha256,source_line FROM messages'),
                         [('synthetic', receipt['source_sha256'], 1)])
        self.assertEqual(self.query("SELECT name FROM sqlite_master WHERE name IN ('export_provenance','export_occurrences')"), [])

    def test_whitespace_required_strings_accepted(self):
        raw = self.encode(self.row(conversation_id=' ', message_id='\t', timestamp=' ', text=' \t'))
        self.assertEqual(ingest_bytes(self.db, 'synthetic', raw)['inserted'], 1)
        self.assertEqual(self.query('SELECT conversation_id,message_id,timestamp,text FROM messages'),
                         [(' ', '\t', ' ', ' \t')])

    def test_empty_files_create_artifacts(self):
        for raw in (b'', b'\n \r\n\t\r', b'\xef\xbb\xbf\n'):
            with self.subTest(raw=raw):
                r = ingest_bytes(self.db, 'synthetic', raw)
                self.assertEqual((r['records'], r['inserted']), (0, 0))
        self.assertEqual(self.query('SELECT COUNT(*),SUM(record_count) FROM artifacts'), [(3, 0)])

    def test_bom_lines_and_hash(self):
        raw = b'\xef\xbb\xbf\r\n \r' + self.encode(self.row()).rstrip(b'\n') + b'\r\n'
        self.assertTrue(ingest_bytes(self.db, 'synthetic', raw)['utf8_bom_present'])
        self.assertEqual(self.query('SELECT source_line,source_sha256 FROM messages'),
                         [(3, hashlib.sha256(raw).hexdigest())])
        self.assertEqual(self.query('SELECT bytes FROM artifacts'), [(len(raw),)])

    def test_identical_repeats_count_without_inserting(self):
        r = ingest_bytes(self.db, 'synthetic', self.encode(self.row(), self.row()))
        self.assertEqual((r['records'], r['inserted']), (2, 1))
        self.assertEqual(self.query('SELECT record_count FROM artifacts'), [(2,)])

    def test_reimport_preserves_first_row_provenance(self):
        first = self.encode(self.row())
        second = b'\n' + self.encode(self.row(unused='Fictional metadata'))
        ingest_bytes(self.db, 'synthetic', first)
        self.assertEqual(ingest_bytes(self.db, 'synthetic', second)['inserted'], 0)
        self.assertEqual(self.query('SELECT COUNT(*) FROM artifacts'), [(2,)])
        self.assertEqual(self.query('SELECT source_sha256,source_line FROM messages'),
                         [(hashlib.sha256(first).hexdigest(), 1)])

    def test_per_line_title_and_insertion_order(self):
        ingest_bytes(self.db, 'synthetic', self.encode(
            self.row(timestamp='later', title='Fictional first'),
            self.row(message_id='fictional-second', timestamp='earlier', title='Fictional second')))
        self.assertEqual(self.query('SELECT title,timestamp FROM messages ORDER BY message_pk'),
                         [('Fictional first', 'later'), ('Fictional second', 'earlier')])
        self.assertEqual(conversations(self.db)['conversations'][0]['original_title'], 'Fictional first')

    def test_missing_title_empty_null_rejected(self):
        ingest_bytes(self.db, 'synthetic', self.encode(self.row()))
        self.assertEqual(self.query('SELECT title FROM messages'), [('',)])
        with self.assertRaisesRegex(ValueError, 'invalid title at line 1'):
            ingest_bytes(self.db, 'synthetic', self.encode(self.row(title=None)))

    def test_invalid_structure_leaves_no_database(self):
        invalid = [b'[]\n', b'{"text":\n', b'\xff', self.encode(self.row(timestamp=0)),
                   self.encode(self.row(text='')), self.encode(self.row(role='developer')),
                   self.encode(self.row(unused={'nested': '\ud800'}))]
        invalid.append(self.encode(self.row()).rstrip(b'\n')[:-1] + b',"unused":{"key":1,"key":2}}\n')
        for raw in invalid:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    ingest_bytes(self.db, 'synthetic', raw)
                self.assertFalse(self.db.exists())

    def test_conflicting_repeat_preflight(self):
        with self.assertRaisesRegex(ValueError, 'conflicting message identity at line 2'):
            ingest_bytes(self.db, 'synthetic', self.encode(self.row(), self.row(title='different')))
        self.assertFalse(self.db.exists())

    def test_existing_conflict_rolls_back_batch(self):
        ingest_bytes(self.db, 'synthetic', self.encode(self.row()))
        with self.assertRaisesRegex(ValueError, 'conflicting message identity at line 2'):
            ingest_bytes(self.db, 'synthetic', self.encode(
                self.row(message_id='fictional-new'), self.row(text='Fictional conflict')))
        self.assertEqual(self.query('SELECT COUNT(*) FROM artifacts'), [(1,)])
        self.assertEqual(self.query('SELECT COUNT(*) FROM messages'), [(1,)])

    def test_export_filter_is_not_artifact_filter(self):
        r = ingest_bytes(self.db, 'synthetic', self.encode(self.row()))
        self.assertEqual(find(self.db, 'orchard')['total_matches'], 1)
        self.assertEqual(find(self.db, 'orchard', export_sha256=r['source_sha256'])['total_matches'], 0)


if __name__ == '__main__':
    unittest.main()
