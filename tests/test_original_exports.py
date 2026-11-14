"""Synthetic source metadata ledger, not retained original content or recovery proof."""
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes
from recaplib.session_workflow import import_export,import_export_bytes,normalize
from recaplib import recovery
from tests.test_web_branch import fixture


class OriginalExportsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'archive.sqlite';self.path=self.root/'input.json'
        self.data=fixture();self.write()

    def write(self):self.path.write_text(json.dumps(self.data,ensure_ascii=False),encoding='utf-8')
    def ingest(self,source='demo',**kwargs):return import_export(self.db,source,self.path,'web',**kwargs)
    def rows(self):
        with closing(sqlite3.connect(self.db)) as c:
            return c.execute('SELECT source,original_sha256,original_bytes,format,selected_conversation,normalized_sha256,extracted_messages FROM original_exports ORDER BY source,original_sha256,format,selected_conversation,normalized_sha256').fetchall()
    def view(self,**kwargs):
        from recaplib.ledger import ledger
        return ledger(self.db,**kwargs)

    def test_same_snapshot_receipt_and_deterministic_metadata_only(self):
        raw=self.path.read_bytes();expected=normalize(self.path,'web',True)[1]
        read=Path.read_bytes;calls=[]
        def counted(path):calls.append(path);return read(path)
        with patch.object(Path,'read_bytes',counted):result=self.ingest()
        self.assertEqual(calls,[self.path]);self.assertEqual(result['coverage'],expected)
        row=self.rows()[0]
        self.assertEqual(row,('demo',hashlib.sha256(raw).hexdigest(),len(raw),'web','',result['source_sha256'],3))
        self.assertNotIn('Synthetic selected orchard',repr(self.rows()));self.assertEqual(self.path.read_bytes(),raw)
        before=self.rows();self.assertEqual(self.ingest()['inserted'],0);self.assertEqual(self.rows(),before)
        self.assertEqual(self.view()['schema'],'recap.archive-ledger.v1')
        recorded=[e for e in self.view()['entries'] if e['kind']=='original_export']
        self.assertIsNone(recorded[0]['selected_conversation'])

    def test_selected_and_whole_imports_and_sources_are_distinct(self):
        self.ingest();self.ingest(conversation='synthetic');self.ingest(source='other',conversation='synthetic')
        rows=self.rows();self.assertEqual(len(rows),3)
        self.assertEqual({r[4] for r in rows},{'','synthetic'})
        self.assertTrue(all(e['source']=='other' for e in self.view(source='other')['entries']))
        self.assertEqual(self.view(source='missing')['total'],0)

    def test_zero_message_exports_keep_distinct_original_hashes(self):
        self.data[0]['mapping']={'root':dict(parent=None,message=None)};self.data[0]['current_node']='root';self.write()
        self.ingest();self.data[0]['title']='Another synthetic title';self.write();self.ingest()
        rows=self.rows();self.assertEqual(len(rows),2)
        self.assertEqual({r[6] for r in rows},{0});self.assertEqual(len({r[5] for r in rows}),1)
        self.assertEqual(len({r[1] for r in rows}),2)
        for version in (1,2):
            output=self.root/('manifest%d.json'%version);recovery.declare_recovery(self.db,output,manifest_version=version)
            value=json.loads(output.read_text());self.assertEqual(value['sources'][0]['original_hashes'],[])
            self.assertNotIn('original_exports',value)

    def test_local_profiles_same_bytes_keep_format_and_replay_identity(self):
        raw=Path('examples/source-attributed-session.jsonl').read_bytes()
        for kind in ('local','local-codex'):
            import_export_bytes(self.db,'demo',raw,'source-attributed-session.jsonl',kind,newline='lf')
        rows=self.rows();self.assertEqual({r[3] for r in rows},{'local','local-codex'})
        self.assertEqual(len(rows),2);self.assertEqual(len({r[1] for r in rows}),1)
        self.assertEqual(len({r[5] for r in rows}),1)
        import_export_bytes(self.db,'demo',raw,'source-attributed-session.jsonl','local',newline='crlf')
        self.assertEqual(len(self.rows()),3)

    def test_plain_ingest_and_readonly_legacy_do_not_create_or_infer_rows(self):
        ingest_bytes(self.db,'demo',Path('examples/conversations.jsonl').read_bytes())
        before=self.db.read_bytes();value=self.view()
        self.assertEqual(self.db.read_bytes(),before)
        self.assertFalse(any(e['kind']=='original_export' for e in value['entries']))
        self.assertTrue(all(e['origin_status']=='unledgered' for e in value['entries']))
        with closing(sqlite3.connect(self.db)) as c:
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='original_exports'").fetchone())

    def test_legacy_provenance_union_unledgered_hashes_without_inferred_metadata(self):
        self.ingest()
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('DROP TABLE original_exports');c.execute('DROP TABLE export_occurrences')
        before=self.db.read_bytes();value=self.view();self.assertEqual(self.db.read_bytes(),before)
        hashes=[e for e in value['entries'] if e['kind']=='unledgered_original_hash']
        self.assertEqual(len(hashes),1)
        for field in ('original_bytes','format','selected_conversation'):self.assertIsNone(hashes[0][field])
        self.ingest();self.assertEqual(len(self.rows()),1)

    def test_one_global_pagination_and_ascii_cli(self):
        for source in ('z','a','합성'):self.ingest(source=source)
        whole=self.view(limit=1000);pages=[];offset=0
        while True:
            page=self.view(limit=1,offset=offset);pages.extend(page['entries'])
            self.assertEqual(page['total'],whole['total'])
            if page['next_offset'] is None:break
            offset=page['next_offset']
        self.assertEqual(pages,whole['entries'])
        before=self.db.read_bytes()
        result=subprocess.run([sys.executable,'recap.py','--db',str(self.db),'ledger','--limit','1000'],capture_output=True,timeout=20,env=dict(os.environ,PYTHONIOENCODING='ascii'))
        self.assertEqual(result.returncode,0,result.stderr);result.stdout.decode('ascii')
        self.assertEqual(json.loads(result.stdout),whole);self.assertEqual(self.db.read_bytes(),before)
        for options in ({'limit':True},{'limit':0},{'limit':1001},{'offset':-1},{'offset':None}):
            with self.assertRaises(ValueError):self.view(**options)

    def test_original_export_write_failure_rolls_back_all_tables(self):
        self.ingest()
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute("CREATE TRIGGER reject_origin BEFORE INSERT ON original_exports BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        before=self.db.read_bytes()
        with self.assertRaises(sqlite3.Error):self.ingest(source='new')
        self.assertEqual(self.db.read_bytes(),before)

    def test_conflicting_existing_metadata_not_silently_ignored(self):
        self.ingest()
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('UPDATE original_exports SET original_bytes=original_bytes+1')
        before=self.db.read_bytes()
        with self.assertRaises(ValueError):self.ingest()
        self.assertEqual(self.db.read_bytes(),before)

    def test_conflicting_existing_table_is_preserved(self):
        ingest_bytes(self.db,'demo',Path('examples/conversations.jsonl').read_bytes())
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('CREATE TABLE original_exports (synthetic_existing TEXT)')
            c.execute("INSERT INTO original_exports VALUES('keep')")
        before=self.db.read_bytes()
        with self.assertRaises((sqlite3.Error,ValueError)):self.ingest()
        self.assertEqual(self.db.read_bytes(),before)

    def test_published_ledger_guide(self):
        import re,shlex
        blocks=re.findall(r'```sh\n(.*?)```',Path('docs/ARCHIVE_LEDGER.md').read_text(),re.S)
        self.assertEqual(len(blocks),1);out=self.root/'guide';out.mkdir();results=[]
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);self.assertEqual(args.pop(0),'python')
            result=subprocess.run([sys.executable,*[s.replace('OUTPUT',str(out)) for s in args]],capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);results.append(result.stdout)
        value=json.loads(results[1]);self.assertEqual(value['schema'],'recap.archive-ledger.v1')
        self.assertEqual({e['kind'] for e in value['entries']},{'artifact','original_export'})
        self.assertIn(b'Archive import ledger',results[2]);results[2].decode('ascii')

    def test_invalid_private_origin_is_rejected_before_connect(self):
        from recaplib import archive
        origin=dict(format='web',original_sha256='a'*64,original_bytes=1,selected_conversation='')
        cases=[]
        for field,value in (('format','normalized'),('original_sha256','A'*64),('original_bytes',True),
                            ('original_bytes',-1),('original_bytes',2**63),('selected_conversation',None),
                            ('selected_conversation','bad\ud800')):
            bad=dict(origin);bad[field]=value;cases.append(bad)
        cases.extend((dict(origin,extra=1),{}))
        for bad in cases:
            with patch.object(archive.sqlite3,'connect',side_effect=AssertionError('must not open DB')):
                with self.assertRaises(ValueError):archive._ingest_adapter_rows(self.db,'demo',[],origin=bad)
        self.assertFalse(self.db.exists())

    def test_output_limit_and_readonly_close(self):
        from recaplib import ledger as module
        self.ingest();opened=[];reader=module.readonly
        def record(path):
            c=reader(path);opened.append(c);return c
        before=self.db.read_bytes()
        with patch.object(module,'readonly',record),patch.object(module,'MAX_OUTPUT_BYTES',1):
            with self.assertRaises(ValueError):module.ledger(self.db)
        self.assertEqual(self.db.read_bytes(),before)
        with self.assertRaises(sqlite3.ProgrammingError):opened[0].execute('SELECT 1')

    def test_compatible_reordered_columns_are_written_by_name(self):
        ingest_bytes(self.db,'base',Path('examples/conversations.jsonl').read_bytes())
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('CREATE TABLE original_exports(source TEXT NOT NULL,format TEXT NOT NULL,original_bytes INTEGER NOT NULL,original_sha256 TEXT NOT NULL,selected_conversation TEXT NOT NULL,normalized_sha256 TEXT NOT NULL,extracted_messages INTEGER NOT NULL,PRIMARY KEY(source,original_sha256,format,selected_conversation,normalized_sha256))')
        result=self.ingest();row=self.rows()[0]
        self.assertEqual(row[1],hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(row[3],'web');self.assertEqual(row[5],result['source_sha256'])

    def test_missing_identity_constraint_rejected_without_repair(self):
        ingest_bytes(self.db,'base',Path('examples/conversations.jsonl').read_bytes())
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('CREATE TABLE original_exports(source TEXT,original_sha256 TEXT,original_bytes INTEGER,format TEXT,selected_conversation TEXT,normalized_sha256 TEXT,extracted_messages INTEGER)')
        before=self.db.read_bytes()
        with self.assertRaises(ValueError):self.ingest()
        self.assertEqual(self.db.read_bytes(),before)

    def test_extra_unique_constraint_or_ignore_trigger_cannot_hide_missing_origin(self):
        self.ingest();original=self.db.read_bytes()
        for sql in ('CREATE UNIQUE INDEX synthetic_source_only ON original_exports(source)',
                    "CREATE TRIGGER synthetic_ignore BEFORE INSERT ON original_exports BEGIN SELECT RAISE(IGNORE); END"):
            self.db.write_bytes(original)
            with closing(sqlite3.connect(self.db)) as c,c:c.execute(sql)
            before=self.db.read_bytes()
            self.path.write_text(json.dumps(self.data,indent=2),encoding='utf-8')
            with self.assertRaises(ValueError):self.ingest()
            self.assertEqual(self.db.read_bytes(),before)

    def test_generated_column_or_check_constraint_fails_without_repair(self):
        self.ingest();original=self.db.read_bytes()
        for declaration in ('extra INTEGER GENERATED ALWAYS AS (original_bytes) VIRTUAL',
                            'extra INTEGER GENERATED ALWAYS AS (original_bytes) STORED'):
            self.db.write_bytes(original)
            with closing(sqlite3.connect(self.db)) as c,c:
                schema=c.execute("SELECT sql FROM sqlite_master WHERE name='original_exports'").fetchone()[0]
                c.execute('ALTER TABLE original_exports RENAME TO old_original_exports')
                c.execute(schema.replace('PRIMARY KEY(',declaration+', PRIMARY KEY('))
            before=self.db.read_bytes()
            with self.assertRaises(ValueError):self.ingest()
            self.assertEqual(self.db.read_bytes(),before)
        self.db.write_bytes(original)
        with closing(sqlite3.connect(self.db)) as c,c:
            schema=c.execute("SELECT sql FROM sqlite_master WHERE name='original_exports'").fetchone()[0]
            c.execute('ALTER TABLE original_exports RENAME TO old_original_exports')
            c.execute(schema.replace('original_bytes INTEGER NOT NULL','original_bytes INTEGER NOT NULL CHECK(original_bytes=0)'))
        before=self.db.read_bytes()
        with self.assertRaises(ValueError):self.ingest()
        self.assertEqual(self.db.read_bytes(),before)
