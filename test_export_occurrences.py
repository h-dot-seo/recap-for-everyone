import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from conversation_view import conversation
from session_workflow import import_export


class ExportOccurrenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.path = Path(self.tmp.name) / 'synthetic.jsonl'
        meta = dict(type='session_meta', payload=dict(id='synthetic'))
        message = dict(type='response_item', timestamp='synthetic', payload=dict(
            type='message', id='m', role='user', content=[dict(text='Synthetic repeated request')]))
        self.path.write_text(''.join(json.dumps(row) + '\n' for row in (meta, message, message)), encoding='utf-8')

    def locations(self, source='demo'):
        return [row['locator'] for row in conversation(self.db, source, 'synthetic')['messages'][0]['export_provenance']]

    def test_repeated_explicit_message_keeps_every_physical_occurrence(self):
        receipt = import_export(self.db, 'demo', self.path, 'local')
        self.assertEqual((receipt['records'], receipt['inserted']), (2, 1))
        self.assertEqual(self.locations(), ['line:2', 'line:3'])
        self.assertEqual(import_export(self.db, 'demo', self.path, 'local')['inserted'], 0)
        self.assertEqual(self.locations(), ['line:2', 'line:3'])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM export_provenance').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM export_occurrences').fetchone()[0], 2)

    def test_legacy_archive_is_readable_and_reimport_recovers_missing_locations(self):
        import_export(self.db, 'demo', self.path, 'local')
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('DROP TABLE export_occurrences')  # Synthetic legacy fixture.
            old = connection.execute('SELECT * FROM export_provenance').fetchall()
        self.assertEqual(self.locations(), ['line:2'])
        import_export(self.db, 'demo', self.path, 'local')
        self.assertEqual(self.locations(), ['line:2', 'line:3'])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT * FROM export_provenance').fetchall(), old)

    def test_additive_upgrade_backfills_existing_other_source(self):
        import_export(self.db, 'historical', self.path, 'local')
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('DROP TABLE export_occurrences')
        import_export(self.db, 'new', self.path, 'local')
        self.assertEqual(self.locations('historical'), ['line:2'])
        self.assertEqual(self.locations('new'), ['line:2', 'line:3'])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM export_occurrences').fetchone()[0], 3)

    def test_occurrence_failure_rolls_back_messages_and_both_ledgers(self):
        import_export(self.db, 'demo', self.path, 'local')
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("CREATE TRIGGER reject_occurrence BEFORE INSERT ON export_occurrences BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            import_export(self.db, 'failed', self.path, 'local')
        with closing(sqlite3.connect(self.db)) as connection:
            for table, column in (('messages', 'source_id'), ('artifacts', 'source_id'),
                                  ('export_provenance', 'source'), ('export_occurrences', 'source')):
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table} WHERE {column}=?', ('failed',)).fetchone()[0], 0)

    def test_failed_legacy_import_rolls_back_additive_schema_upgrade(self):
        import_export(self.db, 'demo', self.path, 'local')
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute('DROP TABLE export_occurrences')
            connection.execute("CREATE TRIGGER reject_legacy BEFORE INSERT ON export_provenance BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
        before = self.db.read_bytes()
        with self.assertRaises(sqlite3.IntegrityError):
            import_export(self.db, 'failed', self.path, 'local')
        self.assertEqual(self.db.read_bytes(), before)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='export_occurrences'").fetchone())
