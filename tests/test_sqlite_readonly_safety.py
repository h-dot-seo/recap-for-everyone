"""Read-back and hostile schema regressions for connection-local defenses."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes, readonly, search
from recaplib.local_parser import parse_artifact
from recaplib.recovery import declare_recovery, rehearse_recovery
from recaplib.sqlite_safety import protect_readonly, safety_status


class SQLiteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'archive.sqlite'
        row=dict(conversation_id='synthetic',message_id='m',role='user',timestamp='unknown',title='invented',text='orchard')
        ingest_bytes(self.db,'synthetic',(json.dumps(row)+'\n').encode())

    def test_actual_readback_and_no_persistent_changes(self):
        before=self.db.read_bytes()
        with closing(readonly(self.db)) as c:
            status=safety_status(c)
            self.assertEqual(status['trusted_schema'],'OFF')
            self.assertEqual(status['cell_size_check'],'ON')
            expected='ON' if hasattr(c,'getconfig') and hasattr(sqlite3,'SQLITE_DBCONFIG_DEFENSIVE') else 'UNAVAILABLE'
            self.assertEqual(status['defensive'],expected)
            self.assertEqual(c.execute('PRAGMA query_only').fetchone()[0],1)
            with self.assertRaises(sqlite3.OperationalError):c.execute('DELETE FROM messages')
        self.assertEqual(self.db.read_bytes(),before)
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute('PRAGMA trusted_schema').fetchone()[0],1)

    def test_unsafe_view_succeeds_unprotected_but_is_blocked(self):
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('CREATE VIEW hostile_view AS SELECT fts5(NULL) AS value')
            self.assertEqual(c.execute('SELECT * FROM hostile_view').fetchone(),(None,))
        with closing(readonly(self.db)) as c:
            with self.assertRaisesRegex(sqlite3.DatabaseError,'unsafe use'):
                c.execute('SELECT * FROM hostile_view').fetchall()

    def test_shipped_fts_and_write_connections_remain_working(self):
        self.assertEqual(len(search(self.db,'orchard')),1)
        row=dict(conversation_id='synthetic',message_id='second',role='user',timestamp='unknown',title='invented',text='new orchard')
        ingest_bytes(self.db,'synthetic',(json.dumps(row)+'\n').encode())
        self.assertEqual(len(search(self.db,'orchard')),2)

    def test_local_sqlite_artifact_uses_shared_protection(self):
        calls=[]
        def protect(c):
            result=protect_readonly(c);calls.append(result);return result
        with patch('recaplib.local_parser.protect_readonly',protect):
            parse_artifact(self.db,'synthetic.sqlite','sqlite')
        self.assertEqual(len(calls),1);self.assertEqual(calls[0]['trusted_schema'],'OFF')

    def test_rehearsal_records_actual_settings_inside_integrity_detail(self):
        manifest=self.root/'manifest.json';declare_recovery(self.db,manifest)
        receipt=rehearse_recovery(manifest,self.db,self.root/'receipt.json')
        detail=next(c for c in receipt['checks'] if c['check']=='integrity_check')
        self.assertEqual(detail['sqlite_protections']['trusted_schema'],'OFF')
        self.assertEqual(detail['sqlite_protections']['cell_size_check'],'ON')
        self.assertEqual(receipt['status'],'RECOVERY_REHEARSAL_PASSED')

    def test_unavailable_readback_is_not_reported_active(self):
        class Cursor:
            def fetchone(self):return None
        class Legacy:
            def execute(self,sql):return Cursor()
        self.assertEqual(protect_readonly(Legacy()),dict(trusted_schema='UNAVAILABLE',cell_size_check='UNAVAILABLE',defensive='UNAVAILABLE'))

    def test_failed_setting_closes_readonly_connection(self):
        connection=sqlite3.connect(self.db)
        with patch('recaplib.archive.sqlite3.connect',return_value=connection),patch('recaplib.archive.protect_readonly',side_effect=sqlite3.DatabaseError('synthetic failed setup')):
            with self.assertRaises(sqlite3.DatabaseError):readonly(self.db)
        with self.assertRaises(sqlite3.ProgrammingError):connection.execute('SELECT 1')
        class Cursor:
            def fetchone(self):return (1,)
        class Ignored:
            def execute(self,sql):return Cursor()
        with self.assertRaisesRegex(sqlite3.DatabaseError,'could not be enabled'):protect_readonly(Ignored())

    def test_hostile_restored_table_view_fails_rehearsal(self):
        manifest=self.root/'manifest.json';declare_recovery(self.db,manifest)
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('DROP TABLE artifacts')
            c.execute('CREATE VIEW artifacts AS SELECT fts5(NULL) AS source_id, NULL AS sha256, 0 AS bytes, 0 AS record_count')
        result=rehearse_recovery(manifest,self.db,self.root/'hostile-receipt.json')
        self.assertEqual(result['status'],'RECOVERY_REHEARSAL_FAILED')
        checks={c['check']:c for c in result['checks']}
        self.assertEqual(checks['expected_tables']['status'],'FAIL')
        self.assertEqual(checks['artifact_rows']['status'],'FAIL')
