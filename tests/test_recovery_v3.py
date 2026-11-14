"""Synthetic import-metadata preservation, not original authenticity or replay."""
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib import recovery,rebuild
from recaplib.session_workflow import import_export_bytes
from tests.test_web_branch import fixture

FIELDS=('source','original_sha256','original_bytes','format','selected_conversation','normalized_sha256','extracted_messages')

class RecoveryV3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'archive.sqlite';self.serial=0
        self.raw=json.dumps(fixture()).encode()
        import_export_bytes(self.db,'demo',self.raw,None,'web',newline='lf')
    def path(self,name):
        self.serial+=1;return self.root/(str(self.serial)+'-'+name)
    def declare(self,version=3):
        path=self.path('manifest.json');result=recovery.declare_recovery(self.db,path,'2026-11-14',manifest_version=version)
        return path,json.loads(path.read_text()),result
    def rehearse(self,path,db=None,objects=None):
        out=self.path('receipt.json');result=recovery.rehearse_recovery(path,db or self.db,out,objects)
        saved=json.loads(out.read_text());self.assertEqual(saved['checks'],result['checks']);self.assertEqual(saved['schema'],result['schema'])
        return result
    def test_schema_exact_rows_and_readonly_actual_receipt(self):
        before=self.db.read_bytes();path,value,result=self.declare()
        self.assertEqual(value['schema'],'recap.recovery-manifest.v3')
        self.assertEqual(result['schema'],'recap.recovery-declaration.v3')
        ledger=value['original_exports'];self.assertEqual(set(ledger),{'count','sha256','rows'})
        self.assertEqual(ledger['count'],1);self.assertEqual(set(ledger['rows'][0]),set(FIELDS))
        self.assertEqual(ledger['rows'][0]['selected_conversation'],'')
        self.assertEqual(value['original_export_hashes'],[hashlib.sha256(self.raw).hexdigest()])
        actual=self.rehearse(path);self.assertEqual(actual['schema'],'recap.recovery-receipt.v3')
        self.assertEqual(actual['manifest']['schema'],value['schema']);self.assertEqual(actual['status'],recovery.PASSED)
        self.assertEqual(self.db.read_bytes(),before)
    def test_every_column_mutation_and_loss_is_detected(self):
        path,_,_=self.declare();original=self.db.read_bytes()
        changes=dict(source='different',original_sha256='f'*64,original_bytes=1,format='local',selected_conversation='other',normalized_sha256='e'*64,extracted_messages=0)
        for field,value in changes.items():
            with self.subTest(field=field):
                db=self.path('altered.sqlite');db.write_bytes(original)
                with closing(sqlite3.connect(db)) as c,c:c.execute('UPDATE original_exports SET '+field+'=?',(value,))
                before=db.read_bytes();r=self.rehearse(path,db)
                self.assertIn('original_exports',r['failed_checks']);self.assertEqual(db.read_bytes(),before)
        db=self.path('lost.sqlite');db.write_bytes(original)
        with closing(sqlite3.connect(db)) as c,c:c.execute('DROP TABLE original_exports')
        self.assertIn('original_exports',self.rehearse(path,db)['failed_checks'])
    def test_absent_empty_and_unexpected_table_distinct(self):
        with closing(sqlite3.connect(self.db)) as c,c:
            sql=c.execute("SELECT sql FROM sqlite_master WHERE name='original_exports'").fetchone()[0]
            c.execute('DELETE FROM original_exports')
        empty,v,_=self.declare();self.assertEqual(v['original_exports'],dict(count=0,sha256=hashlib.sha256(b'').hexdigest(),rows=[]))
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('DROP TABLE original_exports')
        absent,v,_=self.declare();self.assertIsNone(v['original_exports']);self.assertEqual(v['original_export_hashes'],[])
        self.assertIn('original_exports',self.rehearse(empty)['failed_checks'])
        self.assertEqual(self.rehearse(absent)['status'],recovery.PASSED)
        with closing(sqlite3.connect(self.db)) as c,c:c.execute(sql)
        self.assertIn('original_exports',self.rehearse(absent)['failed_checks'])
    def test_filecopy_vacuum_and_physical_row_order_do_not_change_digest(self):
        import_export_bytes(self.db,'second',self.raw,None,'web',newline='lf')
        path,value,_=self.declare();db=self.path('copy.sqlite');db.write_bytes(self.db.read_bytes())
        with closing(sqlite3.connect(db)) as c,c:
            rows=c.execute('SELECT * FROM original_exports').fetchall();c.execute('DELETE FROM original_exports')
            c.executemany('INSERT INTO original_exports VALUES(?,?,?,?,?,?,?)',list(reversed(rows)))
        with closing(sqlite3.connect(db)) as c:c.execute('VACUUM')
        self.assertEqual(self.rehearse(path,db)['status'],recovery.PASSED)
    def test_format_selection_are_distinct_and_same_hash_deduplicated(self):
        import_export_bytes(self.db,'demo',self.raw,None,'web',conversation='synthetic',newline='lf')
        raw=Path('examples/source-attributed-session.jsonl').read_bytes()
        for kind in ('local','local-codex'):import_export_bytes(self.db,'local',raw,'synthetic-local',kind,newline='lf')
        path,value,_=self.declare();rows=value['original_exports']['rows']
        self.assertEqual(len(rows),4);self.assertEqual(len(value['original_export_hashes']),2)
        self.assertEqual({r['selected_conversation'] for r in rows if r['format']=='web'},{'','synthetic'})
        self.assertEqual(self.rehearse(path)['status'],recovery.PASSED)
    def test_zero_message_hash_is_explicit_object_requirement_only_in_v3(self):
        raw=b'[]';import_export_bytes(self.db,'zero',raw,None,'web',newline='lf')
        path,value,_=self.declare();digest=hashlib.sha256(raw).hexdigest()
        self.assertIn(digest,value['original_export_hashes'])
        self.assertEqual(next(s for s in value['sources'] if s['source_id']=='zero')['original_hashes'],[])
        objects=self.root/'objects';objects.mkdir();(objects/'web.json').write_bytes(self.raw)
        (objects/'empty-normalized.jsonl').write_bytes(b'')
        first=self.rehearse(path,objects=objects)
        check=next(c for c in first['checks'] if c['check']=='declared_objects')
        self.assertEqual(next(o for o in check['objects'] if o['sha256']==digest)['status'],'MISSING')
        (objects/'zero.json').write_bytes(raw)
        self.assertEqual(self.rehearse(path,objects=objects)['status'],recovery.PASSED)
    def test_existing_versions_ignore_new_ledger_bytes_and_checks_unchanged(self):
        old=[]
        for version in (1,2):
            path,value,result=self.declare(version);old.append((version,path.read_bytes(),result,[c['check'] for c in self.rehearse(path)['checks']]))
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('DROP TABLE original_exports')
        for version,raw,result,checks in old:
            path,_,new=self.declare(version);self.assertEqual(path.read_bytes(),raw);self.assertEqual(new,result)
            self.assertEqual([c['check'] for c in self.rehearse(path)['checks']],checks)
    def test_malformed_metadata_and_hash_list_fail_closed(self):
        _,value,_=self.declare()
        variants=[]
        for field,badvalue in [('source',None),('original_sha256','A'*64),('original_bytes',True),('original_bytes',-1),('format','invented'),('selected_conversation',None),('normalized_sha256','f'*64),('extracted_messages',True)]:
            v=copy.deepcopy(value);v['original_exports']['rows'][0][field]=badvalue;variants.append(v)
        for mutate in ('extra','count','digest','hashes','duplicate','missing'):
            v=copy.deepcopy(value)
            if mutate=='extra':v['original_exports']['extra']=1
            elif mutate=='count':v['original_exports']['count']=True
            elif mutate=='digest':v['original_exports']['sha256']='A'*64
            elif mutate=='hashes':v['original_export_hashes']=['f'*64]
            elif mutate=='duplicate':v['original_exports']['rows']*=2
            else:del v['original_exports']
            variants.append(v)
        for v in variants:
            with self.subTest(value=v):
                with self.assertRaises(ValueError):recovery._validate_manifest(v)
    def test_duplicate_identity_and_conflicting_hash_counts_in_archive_rejected(self):
        original=self.db.read_bytes()
        for duplicate in (True,False):
            self.db.write_bytes(original)
            with closing(sqlite3.connect(self.db)) as c,c:
                if duplicate:
                    rows=c.execute('SELECT * FROM original_exports').fetchall();c.execute('DROP TABLE original_exports')
                    c.execute('CREATE TABLE original_exports(source,original_sha256,original_bytes,format,selected_conversation,normalized_sha256,extracted_messages)')
                    c.executemany('INSERT INTO original_exports VALUES(?,?,?,?,?,?,?)',rows*2)
                else:
                    row=list(c.execute('SELECT * FROM original_exports').fetchone());row[3]='local';row[2]+=1
                    c.execute('INSERT INTO original_exports VALUES(?,?,?,?,?,?,?)',row)
            before=self.db.read_bytes();out=self.path('invalid.json')
            with self.assertRaises(ValueError):recovery.declare_recovery(self.db,out,manifest_version=3)
            self.assertFalse(out.exists());self.assertEqual(self.db.read_bytes(),before)
    def test_v3_rebuild_rejected_before_plan_or_output(self):
        path,_,_=self.declare();out=self.path('receipt.json');db=self.path('new.sqlite')
        with patch.object(rebuild,'_read_plan',side_effect=AssertionError('must not read')):
            with self.assertRaises(ValueError):rebuild.rebuild_archive(path,self.root/'missing-plan',self.root,db,out)
        self.assertFalse(out.exists());self.assertFalse(db.exists())
    def test_cli_parity_and_executed_guide(self):
        result=[]
        for entry,command in [('recap.py','declare-recovery'),('recovery.py','declare')]:
            path=self.path('cli.json');args=[sys.executable,entry]
            args+=['--db',str(self.db),command] if entry=='recap.py' else [command,'--db',str(self.db)]
            r=subprocess.run(args+['--manifest-version','3','--declared-at','2026-11-14','--output',str(path)],capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr);result.append((r.stdout,path.read_bytes()))
        self.assertEqual(result[0],result[1])
        out=self.root/'guide';out.mkdir();blocks=re.findall(r'```sh\n(.*?)```',Path('docs/RECOVERY_V3.md').read_text(),re.S)
        self.assertEqual(len(blocks),1)
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);args[0]=sys.executable
            r=subprocess.run([s.replace('OUTPUT',str(out)) for s in args],capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr);json.loads(r.stdout)
        self.assertEqual(json.loads(r.stdout)['status'],recovery.PASSED)
    def test_failure_cleanup_close_and_existing_output(self):
        opened=[];reader=recovery.readonly
        def record(*args,**kwargs):
            c=reader(*args,**kwargs);opened.append(c);return c
        before=self.db.read_bytes();out=self.path('blocked.json')
        with patch.object(recovery,'readonly',record),patch.object(recovery.os,'link',side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):recovery.declare_recovery(self.db,out,manifest_version=3)
        self.assertFalse(out.exists());self.assertFalse(list(self.root.glob('.recap-recovery-manifest-*')))
        for c in opened:
            with self.assertRaises(sqlite3.ProgrammingError):c.execute('SELECT 1')
        out.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):recovery.declare_recovery(self.db,out,manifest_version=3)
        self.assertEqual(out.read_bytes(),b'keep');self.assertEqual(self.db.read_bytes(),before)
    def test_resigned_inconsistent_rows_rejected_and_order_is_canonical(self):
        import_export_bytes(self.db,'second',self.raw,None,'web',newline='lf')
        _,value,_=self.declare()
        for case in ('duplicate','size_conflict','artifact_count','reversed'):
            v=copy.deepcopy(value);rows=v['original_exports']['rows']
            if case=='duplicate':rows.insert(0,copy.deepcopy(rows[0]))
            elif case=='size_conflict':rows[1]['original_bytes']+=1
            elif case=='artifact_count':rows[0]['extracted_messages']+=1
            else:rows.reverse()
            v['original_exports']['count']=len(rows)
            raw=b''.join((json.dumps([r[f] for f in FIELDS],ensure_ascii=True,separators=(',',':'))+'\n').encode('ascii') for r in rows)
            v['original_exports']['sha256']=hashlib.sha256(raw).hexdigest()
            with self.subTest(case=case):
                with self.assertRaises(ValueError):recovery._validate_manifest(v)
    def test_invalid_versions_bounds_and_corrupt_copy_never_mark_unrun_pass(self):
        for version in (True,False,0,4,'3',None):
            out=self.path('invalid.json')
            with self.assertRaises(ValueError):recovery.declare_recovery(self.db,out,manifest_version=version)
            self.assertFalse(out.exists())
        out=self.path('too-large.json')
        with patch.object(recovery,'MAX_MANIFEST_BYTES',1):
            with self.assertRaises(ValueError):recovery.declare_recovery(self.db,out,manifest_version=3)
        self.assertFalse(out.exists())
        path,_,_=self.declare();broken=self.path('broken.sqlite');broken.write_bytes(b'synthetic invalid SQLite')
        r=self.rehearse(path,broken);self.assertEqual(r['status'],recovery.FAILED)
        self.assertEqual([c['check'] for c in r['checks']],list(recovery.CHECKS_V3))
        self.assertTrue(all(c['status']=='FAIL' for c in r['checks']))
    def test_rehearsal_close_receipt_failure_and_retained_publication(self):
        path,_,_=self.declare();opened=[];reader=recovery.readonly;before=self.db.read_bytes()
        def record(*args,**kwargs):
            c=reader(*args,**kwargs);opened.append(c);return c
        out=self.path('failed-receipt.json')
        with patch.object(recovery,'readonly',record),patch.object(recovery.os,'link',side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):recovery.rehearse_recovery(path,self.db,out)
        self.assertFalse(out.exists());self.assertFalse(list(self.root.glob('.recap-recovery-receipt-*')))
        for c in opened:
            with self.assertRaises(sqlite3.ProgrammingError):c.execute('SELECT 1')
        unlink=Path.unlink;out=self.path('retained.json')
        def fail_staging(p,*args,**kwargs):
            if p.name.startswith('.recap-recovery-manifest-'):raise OSError('synthetic cleanup')
            return unlink(p,*args,**kwargs)
        with patch.object(Path,'unlink',fail_staging):r=recovery.declare_recovery(self.db,out,manifest_version=3)
        self.assertFalse(r['staging_cleanup_complete']);self.assertTrue(out.exists());self.assertEqual(self.db.read_bytes(),before)
