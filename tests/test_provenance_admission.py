"""Synthetic API provenance admission; shape checks do not verify origin claims."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from recaplib.archive import ingest, ingest_bytes


class ProvenanceAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'synthetic.sqlite'
        self.row=dict(conversation_id='c',message_id='m',role='user',timestamp='t',text='synthetic')
        self.raw=(json.dumps(self.row)+'\n').encode()
        self.origin=dict(conversation_id='c',message_id='m',origin_sha256='a'*64,origin_locator='line:1')

    def refuse(self,provenance):
        with patch('sqlite3.connect',side_effect=AssertionError('must validate before SQLite')):
            with self.assertRaises(ValueError):ingest_bytes(self.db,'s',self.raw,provenance)
        self.assertFalse(self.db.exists())

    def test_malformed_fields_refused_before_database(self):
        for key,values in {
            'origin_sha256':[None,True,1,[],{},'', 'A'*64,'a'*63,'g'*64],
            'origin_locator':[None,True,1,[],{},''],
            'parent_id':[True,1,[],{}],
            'conversation_id':[None,True,1,[],{},'', 'other'],
            'message_id':[None,True,1,[],{},'', 'other'],
        }.items():
            for value in values:
                with self.subTest(key=key,value=value):self.refuse([dict(self.origin,**{key:value})])
        for key in ('conversation_id','message_id','origin_sha256','origin_locator'):
            item=self.origin.copy();del item[key]
            with self.subTest(missing=key):self.refuse([item])

    def test_malformed_container_and_rows(self):
        for value in (True,1,'text',b'bytes',{'unexpected':'mapping'},[None],[True],[1],[[]],['text']):
            with self.subTest(value=value):self.refuse(value)

    def test_late_invalid_row_does_not_create_database(self):
        self.refuse(iter([self.origin,dict(self.origin,origin_sha256='wrong')]))

    def test_existing_database_unchanged_after_invalid_provenance(self):
        ingest_bytes(self.db,'s',self.raw)
        before=self.db.read_bytes()
        with patch('sqlite3.connect',side_effect=AssertionError('no DB connection')):
            with self.assertRaises(ValueError):ingest_bytes(self.db,'s',self.raw,[dict(self.origin,message_id='foreign')])
        self.assertEqual(self.db.read_bytes(),before)

    def test_identity_must_be_in_current_input_not_only_archive(self):
        ingest_bytes(self.db,'s',self.raw)
        other=dict(self.row,message_id='n');raw=(json.dumps(other)+'\n').encode()
        before=self.db.read_bytes()
        with self.assertRaises(ValueError):ingest_bytes(self.db,'s',raw,[self.origin])
        self.assertEqual(self.db.read_bytes(),before)

    def test_none_and_empty_iterable_retain_distinct_ledger_behavior(self):
        for index,value in enumerate((None,[],(),iter([]))):
            db=self.root/('case%d.sqlite'%index)
            receipt=ingest_bytes(db,'s',self.raw,value)
            self.assertEqual(receipt['inserted'],1)
            with closing(sqlite3.connect(db)) as conn:
                found=conn.execute("SELECT name FROM sqlite_master WHERE name='export_occurrences'").fetchone()
                self.assertEqual(found is not None,value is not None)

    def test_iterable_order_duplicates_optional_parent_and_extra_keys(self):
        rows=[dict(self.origin,extra={'ignored':True}),dict(self.origin,origin_locator='line:2',parent_id=''),self.origin.copy()]
        yielded=[]
        def supplied():
            for row in rows:yielded.append(row);yield row
        result=ingest_bytes(self.db,'s',self.raw,supplied())
        self.assertEqual(len(yielded),3);self.assertEqual(result['inserted'],1)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute('SELECT locator,parent FROM export_provenance').fetchall(),[('line:1',None)])
            self.assertEqual(conn.execute('SELECT locator,parent FROM export_occurrences ORDER BY rowid').fetchall(),[('line:1',None),('line:2','')])
        self.assertEqual(ingest_bytes(self.db,'s',self.raw,rows)['inserted'],0)

    def test_file_provenance_fallback_one_snapshot_and_no_db_on_failure(self):
        path=self.root/'synthetic.jsonl';path.write_bytes(self.raw)
        original=Path.read_bytes;reads=[]
        def snapshot(value):reads.append(value);return original(value)
        with patch.object(Path,'read_bytes',snapshot),patch('sqlite3.connect',side_effect=AssertionError('no DB')):
            with self.assertRaises(ValueError):ingest(self.db,'s',path,[dict(self.origin,origin_locator='')])
        self.assertEqual(reads,[path]);self.assertFalse(self.db.exists())

    def test_plain_normalized_origin_members_stay_ignored(self):
        row=dict(self.row,origin_sha256='not-a-hash',origin_locator=False,parent_id=42)
        receipt=ingest_bytes(self.db,'s',(json.dumps(row)+'\n').encode())
        self.assertEqual(receipt['inserted'],1)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='export_provenance'").fetchone())

    def test_invalid_unicode_is_refused_before_database(self):
        for key in ('origin_locator','parent_id','conversation_id','message_id'):
            with self.subTest(key=key):self.refuse([dict(self.origin,**{key:'\ud800'})])

    def test_partial_provenance_and_whitespace_locator_are_preserved(self):
        other=dict(self.row,message_id='n')
        raw=self.raw+(json.dumps(other)+'\n').encode()
        receipt=ingest_bytes(self.db,'s',raw,[dict(self.origin,origin_locator=' ',parent_id=None)])
        self.assertEqual(receipt['inserted'],2)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute('SELECT message,locator,parent FROM export_occurrences').fetchall(),[('m',' ',None)])
