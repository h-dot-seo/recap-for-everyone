"""Synthetic explicit v2 ledger preservation, never source authenticity."""
from contextlib import closing
import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from recaplib import recovery
from recaplib.session_workflow import import_export, titles
from recaplib.title_review_state import review_state
from tests.test_web_branch import fixture


class RecoveryV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'archive.sqlite'
        self.source=self.root/'synthetic.json';self.source.write_text(json.dumps(fixture()))
        import_export(self.db,'demo',self.source,'web')
        titles(self.db,'demo','synthetic','First synthetic title',0)
        titles(self.db,'demo','synthetic','Second synthetic title',1)
        for state in ('skipped','deferred'):
            lease=review_state(self.db,'demo','synthetic')
            review_state(self.db,'demo','synthetic',state,lease['state_revision'],lease['expected_title_revision'],lease['expected_content_sha256'])
        self.serial=0

    def path(self,name):
        self.serial+=1;return self.root/(str(self.serial)+'-'+name)

    def declare(self,version=2):
        path=self.path('manifest.json')
        result=recovery.declare_recovery(self.db,path,'2026-11-14',manifest_version=version)
        return path,json.loads(path.read_text()),result

    def rehearse(self,manifest,db=None):
        path=self.path('receipt.json')
        result=recovery.rehearse_recovery(manifest,db or self.db,path)
        return result,json.loads(path.read_text())

    def test_v2_all_declared_ledgers_and_actual_schema(self):
        before=self.db.read_bytes();path,value,result=self.declare()
        self.assertEqual(value['schema'],'recap.recovery-manifest.v2')
        self.assertEqual(result['manifest_schema'],value['schema'])
        self.assertEqual(result['schema'],'recap.recovery-declaration.v2')
        for name in ('title_history','title_review_history','export_provenance','export_nodes','export_conversations'):
            self.assertEqual(set(value[name]),{'count','sha256'});self.assertGreater(value[name]['count'],0)
        actual,saved=self.rehearse(path)
        self.assertEqual(actual['schema'],'recap.recovery-receipt.v2')
        self.assertEqual(actual['manifest']['schema'],value['schema'])
        self.assertEqual(actual['status'],recovery.PASSED)
        self.assertTrue(all(c['status']=='PASS' for c in actual['checks']))
        self.assertEqual(saved['checks'],actual['checks']);self.assertEqual(self.db.read_bytes(),before)

    def test_each_optional_ledger_loss_and_field_mutation_fails(self):
        path,_,_=self.declare();original=self.db.read_bytes()
        mutations={'title_history':"UPDATE title_history SET title='Changed' WHERE id=1",
                   'title_review_history':"UPDATE title_review_history SET state='pending' WHERE id=1",
                   'export_provenance':"UPDATE export_provenance SET locator='changed' WHERE message='active'",
                   'export_nodes':"UPDATE export_nodes SET ordinal=99 WHERE node='active'",
                   'export_conversations':"UPDATE export_conversations SET current_node='old'"}
        for table,change in mutations.items():
            for sql in ('DROP TABLE '+table,change):
                with self.subTest(table=table,sql=sql):
                    db=self.path('restored.sqlite');db.write_bytes(original)
                    with closing(sqlite3.connect(db)) as c,c:c.execute(sql)
                    before=db.read_bytes();actual,_=self.rehearse(path,db)
                    self.assertEqual(actual['status'],recovery.FAILED)
                    self.assertIn(table,actual['failed_checks']);self.assertEqual(db.read_bytes(),before)

    def test_swapping_history_ids_changes_v2_not_v1_title_digest(self):
        v1,_,_=self.declare(1);v2,_,_=self.declare()
        original=self.db.read_bytes()
        for table in ('title_history','title_review_history'):
            db=self.path('swapped.sqlite');db.write_bytes(original)
            with closing(sqlite3.connect(db)) as c,c:
                c.execute('UPDATE '+table+' SET id=-id')
                c.execute('UPDATE '+table+' SET id=CASE id WHEN -1 THEN 2 WHEN -2 THEN 1 END')
            actual,_=self.rehearse(v2,db);self.assertIn(table,actual['failed_checks'])
            legacy,_=self.rehearse(v1,db);self.assertEqual(legacy['status'],recovery.PASSED)

    def test_topology_text_marker_and_pointer_state_are_bound(self):
        path,_,_=self.declare();original=self.db.read_bytes()
        for sql,check in (("UPDATE export_nodes SET has_text=0 WHERE node='active'",'export_nodes'),
                          ("UPDATE export_conversations SET current_node_state='invalid'",'export_conversations')):
            db=self.path('altered.sqlite');db.write_bytes(original)
            with closing(sqlite3.connect(db)) as c,c:c.execute(sql)
            actual,_=self.rehearse(path,db);self.assertIn(check,actual['failed_checks'])

    def test_vacuum_and_file_copy_preserve_logical_digests(self):
        path,_,_=self.declare();db=self.path('copy.sqlite');db.write_bytes(self.db.read_bytes())
        with closing(sqlite3.connect(db)) as c:c.execute('VACUUM')
        actual,_=self.rehearse(path,db);self.assertEqual(actual['status'],recovery.PASSED)

    def test_null_absent_and_empty_table_are_distinct(self):
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('DELETE FROM title_review_history')
        empty,value,_=self.declare();self.assertEqual(value['title_review_history']['count'],0)
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('DROP TABLE title_review_history')
        absent,value,_=self.declare();self.assertIsNone(value['title_review_history'])
        actual,_=self.rehearse(empty);self.assertIn('title_review_history',actual['failed_checks'])
        self.assertEqual(self.rehearse(absent)[0]['status'],recovery.PASSED)

    def test_default_and_explicit_v1_manifest_and_declaration_bytes_identical(self):
        one=self.path('default.json');two=self.path('explicit.json')
        default=recovery.declare_recovery(self.db,one,'2026-11-14')
        explicit=recovery.declare_recovery(self.db,two,'2026-11-14',manifest_version=1)
        self.assertEqual(one.read_bytes(),two.read_bytes());self.assertEqual(default,explicit)
        value=json.loads(one.read_text());self.assertEqual(set(value),set(recovery.MANIFEST_FIELDS))
        result,_=self.rehearse(one)
        self.assertEqual([c['check'] for c in result['checks']],list(recovery.CHECKS))

    def test_bad_versions_and_exact_v2_fields_rejected(self):
        for version in (True,False,0,3,'2',None):
            output=self.path('bad.json');before=self.db.read_bytes()
            with self.assertRaises(ValueError):recovery.declare_recovery(self.db,output,manifest_version=version)
            self.assertFalse(output.exists());self.assertEqual(self.db.read_bytes(),before)
        _,value,_=self.declare()
        for mutation in ('missing','extra','bool_count','uppercase_digest'):
            bad=copy.deepcopy(value)
            if mutation=='missing':del bad['export_nodes']
            elif mutation=='extra':bad['unexpected']=1
            elif mutation=='bool_count':bad['export_nodes']['count']=True
            else:bad['export_nodes']['sha256']='A'*64
            with self.assertRaises(ValueError):recovery._validate_manifest(bad)

    def test_cli_declare_and_rehearse_v2_equivalence(self):
        outputs=[]
        for entry,command in (('recap.py','declare-recovery'),('recovery.py','declare')):
            output=self.path('cli-manifest.json')
            args=[sys.executable,entry]
            if entry=='recap.py':args+=['--db',str(self.db),command]
            else:args+=[command,'--db',str(self.db)]
            args+=['--manifest-version','2','--declared-at','2026-11-14','--output',str(output)]
            result=subprocess.run(args,capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0],outputs[1])

    def test_v2_rebuild_rejected_before_plan_read_or_output_creation(self):
        from unittest.mock import patch
        from recaplib import rebuild
        path,_,_=self.declare();target=self.path('rebuilt.sqlite');output=self.path('rebuild.json')
        before=self.db.read_bytes()
        with patch.object(rebuild,'_read_plan',side_effect=AssertionError('plan must not be read')):
            with self.assertRaises(ValueError):
                rebuild.rebuild_archive(path,self.root/'no-plan.json',self.root,target,output)
        self.assertFalse(target.exists());self.assertFalse(output.exists());self.assertEqual(self.db.read_bytes(),before)

    def test_published_self_check_guide(self):
        import re,shlex
        block=re.findall(r'```sh\n(.*?)```',Path('docs/RECOVERY_V2.md').read_text(),re.S)
        self.assertEqual(len(block),1);out=self.root/'guide';out.mkdir();results=[]
        for line in block[0].strip().splitlines():
            args=shlex.split(line);self.assertEqual(args.pop(0),'python')
            result=subprocess.run([sys.executable,*[s.replace('OUTPUT',str(out)) for s in args]],capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);results.append(json.loads(result.stdout))
        self.assertEqual(results[-1]['schema'],'recap.recovery-receipt.v2')
        self.assertEqual(results[-1]['status'],recovery.PASSED)

    def test_occurrence_digest_detects_every_column_with_same_row_count(self):
        path,value,_=self.declare();original=self.db.read_bytes()
        self.assertRegex(value['export_occurrences_sha256'],r'^[0-9a-f]{64}$')
        changes={'source':'other','conversation':'other','message':'other',
                 'original_hash':'f'*64,'locator':'mapping:changed','parent':'old'}
        for column,value in changes.items():
            with self.subTest(column=column):
                db=self.path('occurrence.sqlite');db.write_bytes(original)
                with closing(sqlite3.connect(db)) as c,c:
                    c.execute('UPDATE export_occurrences SET '+column+'=? WHERE message=?',(value,'active'))
                actual,_=self.rehearse(path,db);self.assertIn('export_occurrences',actual['failed_checks'])

    def test_occurrence_null_empty_and_row_order_contract(self):
        path,value,_=self.declare()
        with closing(sqlite3.connect(self.db)) as c,c:
            sql=c.execute("SELECT sql FROM sqlite_master WHERE name='export_occurrences'").fetchone()[0]
            rows=c.execute('SELECT * FROM export_occurrences').fetchall()
            c.execute('DROP TABLE export_occurrences');c.execute(sql)
            c.executemany('INSERT INTO export_occurrences VALUES(?,?,?,?,?,?)',list(reversed(rows)))
        self.assertEqual(self.rehearse(path)[0]['status'],recovery.PASSED)
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('DELETE FROM export_occurrences')
        _,empty,_=self.declare();self.assertEqual(empty['export_occurrences'],0)
        self.assertEqual(empty['export_occurrences_sha256'],__import__('hashlib').sha256(b'').hexdigest())
        with closing(sqlite3.connect(self.db)) as c,c:c.execute('DROP TABLE export_occurrences')
        _,absent,_=self.declare();self.assertIsNone(absent['export_occurrences']);self.assertIsNone(absent['export_occurrences_sha256'])

    def test_v2_publication_failure_cleanup_and_existing_output_are_non_destructive(self):
        from unittest.mock import patch
        before=self.db.read_bytes();output=self.path('blocked.json')
        with patch.object(recovery.os,'link',side_effect=OSError('synthetic link failure')):
            with self.assertRaises(OSError):recovery.declare_recovery(self.db,output,manifest_version=2)
        self.assertFalse(output.exists());self.assertFalse(list(self.root.glob('.recap-recovery-manifest-*')))
        output.write_bytes(b'synthetic keep')
        with self.assertRaises(FileExistsError):recovery.declare_recovery(self.db,output,manifest_version=2)
        self.assertEqual(output.read_bytes(),b'synthetic keep');self.assertEqual(self.db.read_bytes(),before)
        output=self.path('retained.json');unlink=Path.unlink
        def fail_staging(path,*args,**kwargs):
            if path.name.startswith('.recap-recovery-manifest-'):raise OSError('synthetic cleanup failure')
            return unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail_staging):
            result=recovery.declare_recovery(self.db,output,manifest_version=2)
        self.assertFalse(result['staging_cleanup_complete']);self.assertTrue(output.exists())
        self.assertTrue((self.root/result['remaining_staging_file']).exists())
        self.assertEqual(json.loads(output.read_text())['schema'],'recap.recovery-manifest.v2')
        self.assertEqual(self.db.read_bytes(),before)

    def test_v2_connections_close_on_success_and_digest_error(self):
        from unittest.mock import patch
        original=recovery.readonly;connections=[]
        def opened(path):
            c=original(path);connections.append(c);return c
        with patch.object(recovery,'readonly',opened):
            path,_,_=self.declare();self.rehearse(path)
            with patch.object(recovery,'_v2_ledger',side_effect=ValueError('synthetic digest failure')):
                with self.assertRaises(ValueError):self.declare()
                failed,_=self.rehearse(path);self.assertEqual(failed['status'],recovery.FAILED)
        self.assertEqual(len(connections),4)
        for c in connections:
            with self.assertRaises(sqlite3.ProgrammingError):c.execute('SELECT 1')
