"""Synthetic pre-open observations, never SQLite copy-safety determinations."""
from contextlib import closing
import io
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes
from recaplib import archive_schema

class StorageObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'synthetic.sqlite'
        ingest_bytes(self.db,'synthetic',Path('examples/conversations.jsonl').read_bytes())
    def observe(self,db=None):return archive_schema.describe_schema(db or self.db,observe_storage=True)
    def cli(self,db=None):
        return subprocess.run([sys.executable,'recap.py','--db',str(db or self.db),'describe-schema','--observe-storage'],capture_output=True,timeout=20)
    def test_default_inventory_preserved_optin_is_separate(self):
        before=self.db.read_bytes();old=archive_schema.describe_schema(self.db);r=self.observe()
        self.assertEqual(r['schema'],'recap.archive-storage-observation.v1');self.assertEqual(r['status'],'OBSERVED')
        self.assertEqual(r['inventory'],old);self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(r['pre_open']['main']['bytes'],len(before))
        h=r['pre_open']['main']['header'];self.assertEqual(h['bytes_read'],100);self.assertTrue(h['sqlite_signature'])
        self.assertEqual(h['user_version'],0);self.assertEqual(h['read_version'],1);self.assertEqual(h['write_version'],1)
        self.assertEqual(set(r['pre_open']['sidecars']),{'wal','shm','journal'})
        for name in ('snapshot_consistency','copy_safety','backup_completeness'):self.assertEqual(r[name],'NOT_ESTABLISHED')
        self.assertNotIn(str(self.db),json.dumps(r));self.assertIsNone(r['error'])
        c=self.cli();self.assertEqual(c.returncode,0,c.stderr);self.assertEqual(json.loads(c.stdout),r)
    def test_preopen_snapshot_precedes_readonly_wal_sidecar_creation(self):
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute('PRAGMA journal_mode=WAL').fetchone()[0],'wal')
        self.assertFalse(Path(str(self.db)+'-wal').exists());self.assertFalse(Path(str(self.db)+'-shm').exists())
        original=archive_schema.readonly;during=[]
        class TracedConnection:
            def __init__(self,c,db):self.c=c;self.db=db
            def __getattr__(self,name):return getattr(self.c,name)
            def execute(self,sql,*args):
                result=self.c.execute(sql,*args)
                if 'sqlite_master' in sql:during.append({s:Path(str(self.db)+'-'+s).exists() for s in ('wal','shm')})
                return result
        def opened(db):return TracedConnection(original(db),db)
        before=self.db.read_bytes()
        with patch.object(archive_schema,'readonly',opened):r=self.observe()
        self.assertEqual(r['status'],'OBSERVED');self.assertEqual(r['pre_open']['main']['header']['read_version'],2)
        self.assertEqual(r['pre_open']['main']['header']['write_version'],2)
        for name in ('wal','shm'):self.assertEqual(r['pre_open']['sidecars'][name]['bytes'],None)
        self.assertTrue(during);self.assertTrue(during[0]['wal']);self.assertTrue(during[0]['shm'])
        self.assertEqual(self.db.read_bytes(),before)
    def test_existing_wal_observed_before_inventory_without_checkpoint(self):
        c=sqlite3.connect(self.db)
        try:
            c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA wal_autocheckpoint=0')
            c.execute('CREATE TABLE synthetic_extra(value TEXT)');c.commit()
            before={s:Path(str(self.db)+s).read_bytes() for s in ('','-wal')}
            sizes={s:Path(str(self.db)+'-'+s).stat().st_size for s in ('wal','shm')}
            r=self.observe();self.assertEqual(r['status'],'OBSERVED')
            for s in ('wal','shm'):self.assertEqual(r['pre_open']['sidecars'][s]['bytes'],sizes[s])
            for s,raw in before.items():self.assertEqual(Path(str(self.db)+s).read_bytes(),raw)
        finally:c.close()
    def make_hot_journal(self):
        with closing(sqlite3.connect(self.db)) as c,c:
            c.execute('CREATE TABLE synthetic_padding(id INTEGER PRIMARY KEY,value TEXT)')
            c.executemany('INSERT INTO synthetic_padding(value) VALUES(?)',[('a'*8000,)]*200)
        code="import sqlite3,sys,os;c=sqlite3.connect(sys.argv[1]);c.execute('PRAGMA cache_size=5');c.execute('PRAGMA cache_spill=ON');c.execute('BEGIN IMMEDIATE');c.execute('UPDATE synthetic_padding SET value=?',('b'*8000,));os._exit(0)"
        r=subprocess.run([sys.executable,'-c',code,str(self.db)],capture_output=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr);journal=Path(str(self.db)+'-journal')
        self.assertTrue(journal.exists());self.assertGreater(journal.stat().st_size,512)
        return journal
    def test_real_hot_journal_open_error_keeps_observation_and_no_repair(self):
        journal=self.make_hot_journal();before=self.db.read_bytes();jraw=journal.read_bytes()
        r=self.observe();self.assertNotEqual(r['status'],'OBSERVED');self.assertIsNone(r['inventory'])
        self.assertEqual(r['pre_open']['sidecars']['journal']['bytes'],len(jraw))
        self.assertEqual(r['error']['exception_type'],'OperationalError')
        self.assertEqual(self.db.read_bytes(),before);self.assertEqual(journal.read_bytes(),jraw)
        c=self.cli();self.assertEqual(c.returncode,1);self.assertEqual(c.stderr,b'')
        self.assertEqual(json.loads(c.stdout)['pre_open'],r['pre_open']);self.assertNotIn(str(self.db),c.stdout.decode())
    def test_main_nonregular_and_missing_inputs_never_reach_sqlite(self):
        cases=[self.root/'missing',self.root]
        if hasattr(os,'mkfifo'):
            fifo=self.root/'fifo';os.mkfifo(fifo);cases.append(fifo)
        for path in cases:
            with patch.object(archive_schema,'readonly',side_effect=AssertionError('must not open SQLite')):r=self.observe(path)
            self.assertEqual(r['status'],'OBSERVATION_ERROR');self.assertIsNone(r['inventory'])
            self.assertNotIn(str(path),json.dumps(r))
            c=self.cli(path);self.assertEqual(c.returncode,1);self.assertEqual(c.stderr,b'')
    def test_sidecar_nonregular_never_reaches_sqlite(self):
        p=Path(str(self.db)+'-journal');p.mkdir()
        with patch.object(archive_schema,'readonly',side_effect=AssertionError('must not open SQLite')):r=self.observe()
        self.assertEqual(r['status'],'OBSERVATION_ERROR');p.rmdir()
        if hasattr(os,'mkfifo'):
            os.mkfifo(p)
            with patch.object(archive_schema,'readonly',side_effect=AssertionError('must not open SQLite')):r=self.observe()
            self.assertEqual(r['status'],'OBSERVATION_ERROR');self.assertEqual(self.cli().returncode,1)
    def test_symlink_main_and_sidecar_not_followed(self):
        link=self.root/'link.sqlite'
        try:link.symlink_to(self.db)
        except (OSError,NotImplementedError):self.skipTest('symlink unavailable')
        with patch.object(archive_schema,'readonly',side_effect=AssertionError('must not open SQLite')):r=self.observe(link)
        self.assertEqual(r['status'],'OBSERVATION_ERROR')
        side=Path(str(self.db)+'-wal');side.symlink_to(self.db)
        with patch.object(archive_schema,'readonly',side_effect=AssertionError('must not open SQLite')):r=self.observe()
        self.assertEqual(r['status'],'OBSERVATION_ERROR')
    def test_header_read_bounded_and_invalid_header_never_echoed(self):
        p=self.root/'invalid.sqlite';p.write_bytes(b'PRIVATE_SYNTHETIC_HEADER'*20)
        original=Path.open;reads=[]
        class Traced:
            def __init__(self,stream):self.stream=stream
            def __enter__(self):self.stream.__enter__();return self
            def __exit__(self,*args):return self.stream.__exit__(*args)
            def read(self,n=-1):reads.append(n);return self.stream.read(n)
        def traced(path,*args,**kwargs):return Traced(original(path,*args,**kwargs))
        with patch.object(Path,'open',traced):r=self.observe(p)
        self.assertEqual(reads,[100]);self.assertNotIn('PRIVATE_SYNTHETIC_HEADER',json.dumps(r))
        self.assertFalse(r['pre_open']['main']['header']['sqlite_signature'])
        for f in ('read_version','write_version','user_version'):self.assertIsNone(r['pre_open']['main']['header'][f])
    def test_user_version_observed_without_stamp(self):
        with closing(sqlite3.connect(self.db)) as c:c.execute('PRAGMA user_version=42')
        before=self.db.read_bytes();r=self.observe();self.assertEqual(r['pre_open']['main']['header']['user_version'],42)
        self.assertEqual(r['inventory']['user_version'],42);self.assertEqual(self.db.read_bytes(),before)
    def test_injected_sqlite_error_is_redacted_and_opened_connection_closed(self):
        with patch.object(archive_schema,'readonly',side_effect=sqlite3.OperationalError('PRIVATE_SYNTHETIC_PATH')):r=self.observe()
        self.assertNotEqual(r['status'],'OBSERVED');self.assertNotIn('PRIVATE_SYNTHETIC_PATH',json.dumps(r));self.assertIsNone(r['inventory'])
        opened=[];reader=archive_schema.readonly
        def capture(db):c=reader(db);opened.append(c);return c
        with patch.object(archive_schema,'readonly',capture):self.observe()
        with self.assertRaises(sqlite3.ProgrammingError):opened[0].execute('SELECT 1')
    def test_published_storage_guide(self):
        out=self.root/'guide';out.mkdir();blocks=re.findall(r'```sh\n(.*?)```',Path('docs/STORAGE_OBSERVATION.md').read_text(),re.S)
        self.assertEqual(len(blocks),1)
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);args[0]=sys.executable
            r=subprocess.run([p.replace('OUTPUT',str(out)) for p in args],capture_output=True,timeout=20)
            self.assertEqual(r.returncode,0,r.stderr);value=json.loads(r.stdout)
        self.assertEqual(value['schema'],'recap.archive-storage-observation.v1');self.assertEqual(value['status'],'OBSERVED')
    def test_total_envelope_limit_preserves_preopen_and_drops_large_inventory(self):
        limit=archive_schema.MAX_OUTPUT_BYTES
        inventory={'synthetic':'x'*(limit-40)}
        self.assertLess(len(json.dumps(inventory,ensure_ascii=True,indent=2).encode('ascii'))+1,limit)
        with patch.object(archive_schema,'_inventory',return_value=inventory):r=self.observe()
        self.assertEqual(r['status'],'INVENTORY_ERROR');self.assertEqual(r['error']['reason'],'OUTPUT_LIMIT')
        self.assertIsNone(r['inventory']);self.assertEqual(r['pre_open']['main']['header']['bytes_read'],100)
        self.assertLess(len(json.dumps(r,ensure_ascii=True,indent=2).encode('ascii'))+1,limit)
    def test_open_vs_inventory_failure_are_distinct_and_connections_closed(self):
        with patch.object(archive_schema,'readonly',side_effect=sqlite3.OperationalError('PRIVATE_OPEN')):opened=self.observe()
        self.assertEqual(opened['status'],'OPEN_ERROR');self.assertEqual(opened['error']['reason'],'READONLY_OPEN_FAILED')
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('DROP TABLE artifacts')
        connections=[];reader=archive_schema.readonly
        def record(db):c=reader(db);connections.append(c);return c
        with patch.object(archive_schema,'readonly',record):r=self.observe()
        self.assertEqual(r['status'],'INVENTORY_ERROR');self.assertEqual(r['error']['reason'],'METADATA_INVENTORY_FAILED')
        self.assertIsNone(r['inventory']);self.assertEqual(r['pre_open']['main']['header']['bytes_read'],100)
        with self.assertRaises(sqlite3.ProgrammingError):connections[0].execute('SELECT 1')
    def test_stat_header_failure_redacted_preflight_complete_and_no_sqlite(self):
        original=Path.lstat
        def blocked(path,*args,**kwargs):
            if str(path).endswith('-shm'):raise PermissionError('PRIVATE_STAT_PATH')
            return original(path,*args,**kwargs)
        with patch.object(Path,'lstat',blocked),patch.object(archive_schema,'readonly',side_effect=AssertionError('must not open')):r=self.observe()
        self.assertEqual(r['status'],'OBSERVATION_ERROR');self.assertNotIn('PRIVATE_STAT_PATH',json.dumps(r))
        self.assertEqual(set(r['pre_open']['sidecars']),{'wal','shm','journal'})
        with patch.object(Path,'open',side_effect=PermissionError('PRIVATE_HEADER_PATH')),patch.object(archive_schema,'readonly',side_effect=AssertionError('must not open')):r=self.observe()
        self.assertEqual(r['error']['reason'],'HEADER_READ_FAILED');self.assertIsNone(r['pre_open']['main']['header'])
        self.assertNotIn('PRIVATE_HEADER_PATH',json.dumps(r));self.assertEqual(set(r['pre_open']['sidecars']),{'wal','shm','journal'})
