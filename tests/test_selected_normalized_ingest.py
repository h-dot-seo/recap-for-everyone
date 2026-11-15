"""Explicit normalized selection retains the complete immutable artifact identity."""
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from recaplib import archive as a,rebuild,recovery
from recaplib.session_workflow import inspect_normalized
from recaplib.import_check import check_import
from recaplib.export_inventory import list_export
from tests import test_streamed_ingest as prior


def fixture():
    return [dict(conversation_id=c,message_id=str(i),role='user' if i==0 else 'assistant',timestamp='synthetic',title='title-'+c,text=c+str(i)) for c in ('a','b') for i in range(2)]

def encoded(rows):return ('\n'.join(json.dumps(row,ensure_ascii=True) for row in rows)+'\n').encode()

class SelectedNormalizedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.path=self.root/'synthetic.jsonl';self.raw=b'\n'+encoded(fixture());self.path.write_bytes(self.raw)
        self.db=self.root/'archive.sqlite';self.digest=hashlib.sha256(self.raw).hexdigest()

    def test_selected_file_bytes_receipt_full_artifact_and_physical_lines(self):
        r=a.ingest(self.db,'synthetic',self.path,conversation='b',expected_sha256=self.digest)
        other=self.root/'bytes.sqlite';expected=a.ingest_bytes(other,'synthetic',self.raw,conversation='b',expected_sha256=self.digest)
        self.assertEqual(r,expected);self.assertEqual(prior.tables(self.db),prior.tables(other))
        self.assertEqual((r['source_sha256'],r['records'],r['inserted']),(self.digest,4,2))
        self.assertEqual(r['selection']['conversation'],'b');self.assertEqual(r['selection']['selected_messages'],2)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute('SELECT sha256,bytes,record_count FROM artifacts').fetchall(),[(self.digest,len(self.raw),4)])
            self.assertEqual(conn.execute('SELECT conversation_id,source_line FROM messages ORDER BY message_pk').fetchall(),[('b',4),('b',5)])
            self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='original_exports'").fetchone())
        self.assertEqual(self.path.read_bytes(),self.raw)

    def test_repeated_disjoint_then_full_ingest_is_idempotent(self):
        results=[a.ingest(self.db,'synthetic',self.path,conversation=c) for c in ('a','a','b')]
        results.append(a.ingest(self.db,'synthetic',self.path))
        self.assertEqual([x['inserted'] for x in results],[2,0,2,0]);self.assertTrue(all(x['records']==4 for x in results))
        self.assertNotIn('selection',results[-1])
        with closing(sqlite3.connect(self.db)) as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0],1)

    def test_missing_invalid_and_provenance_combination_before_database(self):
        for selected in ('missing','',True,42):
            with self.subTest(selected=selected),patch.object(sqlite3,'connect',side_effect=AssertionError('no database')):
                with self.assertRaises(ValueError):a.ingest(self.db,'synthetic',self.path,conversation=selected)
        for provenance in ([],[{}]):
            with patch.object(sqlite3,'connect',side_effect=AssertionError('no database')):
                with self.assertRaises(ValueError):a.ingest_bytes(self.db,'synthetic',self.raw,provenance,conversation='a')
                with self.assertRaises(ValueError):a.ingest(self.db,'synthetic',self.path,provenance,conversation='a')
        self.assertFalse(self.db.exists())

    def test_all_syntax_but_only_selected_identity_conflicts(self):
        rows=fixture();rows.append(dict(rows[-1],text='conflicting excluded body'))
        raw=encoded(rows)
        r=a.ingest_bytes(self.db,'synthetic',raw,conversation='a');self.assertEqual((r['records'],r['inserted']),(5,2))
        before=self.db.read_bytes()
        with self.assertRaises(ValueError):a.ingest_bytes(self.db,'synthetic',raw,conversation='b')
        self.assertEqual(self.db.read_bytes(),before)
        for invalid in (raw+b'not JSON',raw+b'\xff'):
            with patch.object(sqlite3,'connect',side_effect=AssertionError('no database')):
                with self.assertRaises((ValueError,UnicodeError)):a.ingest_bytes(self.db,'synthetic',invalid,conversation='a')

    def test_selected_inspection_check_and_inventory_agree(self):
        a.ingest_bytes(self.db,'synthetic',b'')
        rows,report=inspect_normalized(self.path,'a',self.digest)
        self.assertEqual({x['conversation_id'] for x in rows},{'a'});self.assertEqual(report['records'],4)
        checked=check_import(self.db,'synthetic',self.path,'normalized',conversation='a',expected_export_sha256=self.digest)
        inventory=list_export(self.path,'normalized')
        self.assertEqual(report['selection']['selected_messages'],2)
        self.assertTrue(all(x['selection_supported'] for x in inventory['conversations']))
        self.assertEqual(checked['coverage']['selection']['conversation'],'a')

    def test_second_pass_mutation_rolls_back_and_closes(self):
        a.ingest_bytes(self.db,'old',encoded(fixture()));before=prior.tables(self.db);real=sqlite3.connect;connections=[]
        def connect(*args,**kwargs):
            self.path.write_bytes(self.raw+b'\n');conn=real(*args,**kwargs);connections.append(conn);return conn
        with patch.object(sqlite3,'connect',side_effect=connect):
            with self.assertRaises(ValueError):a.ingest(self.db,'synthetic',self.path,conversation='a')
        self.assertEqual(prior.tables(self.db),before)
        for conn in connections:
            with self.assertRaises(sqlite3.ProgrammingError):conn.execute('SELECT 1')

    def test_new_empty_schema_can_remain_after_second_pass_failure(self):
        real=sqlite3.connect
        def connect(*args,**kwargs):self.path.write_bytes(self.raw+b'\n');return real(*args,**kwargs)
        with patch.object(sqlite3,'connect',side_effect=connect):
            with self.assertRaises(ValueError):a.ingest(self.db,'synthetic',self.path,conversation='a')
        self.assertTrue(self.db.exists())
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],0)

    def test_ignored_file_origin_claims_do_not_gain_provenance(self):
        rows=fixture()
        for row in rows:row.update(origin_sha256='unverified',origin_locator='not authority',parent_id=True)
        a.ingest_bytes(self.db,'synthetic',encoded(rows),conversation='a')
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name IN ('export_provenance','export_occurrences','original_exports')").fetchone())
