"""Synthetic explicit metadata-preserving replay; never a full archive restore."""
from contextlib import closing
import copy
import hashlib
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
from recaplib import rebuild,recovery
from recaplib.session_workflow import import_export_bytes,titles
from recaplib.title_review_state import review_state
from tests.test_web_branch import fixture

class RebuildV3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.live=self.root/'live.sqlite';self.objects=self.root/'objects';self.objects.mkdir()
        self.manifest=self.root/'manifest.json';self.plan=self.root/'plan.json';self.db=self.root/'rebuilt.sqlite';self.output=self.root/'receipt.json';self.steps=[]
    def add(self,data=None,raw=None,source='demo',kind='web',conversation=None,label=None,newline='lf'):
        raw=raw if raw is not None else json.dumps(fixture() if data is None else data).encode()
        digest=hashlib.sha256(raw).hexdigest();(self.objects/digest).write_bytes(raw)
        import_export_bytes(self.live,source,raw,label,kind,conversation,newline=newline)
        self.steps.append(dict(source=source,kind=kind,object_sha256=digest,label=label,conversation=conversation,newline=newline))
        return digest
    def declare(self):
        recovery.declare_recovery(self.live,self.manifest,'2026-11-14',manifest_version=3);self.saveplan()
    def saveplan(self):self.plan.write_text(json.dumps(dict(schema=rebuild.PLAN_SCHEMA,steps=self.steps)))
    def run_rebuild(self):return rebuild.rebuild_archive(self.manifest,self.plan,self.objects,self.db,self.output)
    def test_all_seven_fields_replayed_and_full_restore_not_claimed(self):
        self.add();self.declare();before=self.live.read_bytes();r=self.run_rebuild()
        self.assertEqual(r['status'],rebuild.PASSED,r);self.assertEqual(r['schema'],'recap.rebuild-receipt.v3')
        self.assertEqual(r['manifest']['schema'],'recap.recovery-manifest.v3');self.assertFalse(r['full_archive_restored'])
        self.assertEqual(r['excluded_checks'],['title_history','title_review_history'])
        self.assertIn('original_exports',[c['check'] for c in r['checks']]);self.assertTrue(all(c['status']=='PASS' for c in r['checks']))
        with closing(sqlite3.connect(self.live)) as a,closing(sqlite3.connect(self.db)) as b:
            self.assertEqual(a.execute('SELECT * FROM original_exports').fetchall(),b.execute('SELECT * FROM original_exports').fetchall())
        self.assertEqual(self.live.read_bytes(),before);self.assertFalse(list(self.root.glob('.recap-*')))
    def test_zero_message_and_textless_topology_preserved(self):
        self.add(raw=b'[]',source='empty')
        data=fixture();data[0]['mapping']={'root':dict(parent=None,message=None)};data[0]['current_node']='root'
        self.add(data,source='textless');self.declare();r=self.run_rebuild()
        self.assertEqual(r['status'],rebuild.PASSED,r)
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM messages').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM original_exports').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM export_conversations').fetchone()[0],1)
    def test_format_and_selection_are_explicit_not_inferred(self):
        raw=Path('examples/source-attributed-session.jsonl').read_bytes()
        for kind in ('local','local-codex'):self.add(raw=raw,source='local',kind=kind,label='synthetic-local')
        self.add();self.add(conversation='synthetic');self.declare();r=self.run_rebuild()
        self.assertEqual(r['status'],rebuild.PASSED,r)
        with closing(sqlite3.connect(self.db)) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM original_exports').fetchone()[0],4)
    def test_undeclared_format_selection_source_hash_rejected_without_db(self):
        self.add();self.declare();original=copy.deepcopy(self.steps)
        for field,value in [('kind','local'),('conversation','synthetic'),('source','other'),('object_sha256','f'*64)]:
            self.steps=copy.deepcopy(original);self.steps[0][field]=value
            if field=='kind':self.steps[0]['label']='synthetic-local'
            self.saveplan();r=self.run_rebuild()
            self.assertEqual(r['status'],rebuild.FAILED);self.assertFalse(self.db.exists())
            self.assertEqual(r['failure']['phase'],'PLAN_OBJECT_DECLARATION');self.output.unlink()
    def test_declared_metadata_that_does_not_match_replay_fails(self):
        self.add();self.declare();v=json.loads(self.manifest.read_text())
        v['original_exports']['rows'][0]['original_bytes']+=1
        rows=v['original_exports']['rows'];fields=recovery.ORIGINAL_EXPORT_FIELDS
        raw=b''.join((json.dumps([r[f] for f in fields],ensure_ascii=True,separators=(',',':'))+'\n').encode('ascii') for r in rows)
        v['original_exports']['sha256']=hashlib.sha256(raw).hexdigest();self.manifest.write_text(json.dumps(v))
        r=self.run_rebuild();self.assertEqual(r['status'],rebuild.FAILED);self.assertIn('original_exports',r['failed_checks']);self.assertFalse(self.db.exists())
    def test_missing_and_empty_origin_ledger_is_not_repaired(self):
        self.add();original=self.live.read_bytes()
        for sql in ('DROP TABLE original_exports','DELETE FROM original_exports'):
            self.live.write_bytes(original)
            with closing(sqlite3.connect(self.live)) as c,c:c.execute(sql)
            self.declare();r=self.run_rebuild();self.assertEqual(r['status'],rebuild.FAILED)
            self.assertFalse(self.db.exists());self.assertFalse(list(self.root.glob('.recap-*')))
            self.manifest.unlink();self.output.unlink()
    def test_histories_excluded_not_marked_pass_and_later_full_rehearsal_fails(self):
        self.add();titles(self.live,'demo','synthetic','Synthetic chosen title',0)
        lease=review_state(self.live,'demo','synthetic')
        review_state(self.live,'demo','synthetic','skipped',lease['state_revision'],lease['expected_title_revision'],lease['expected_content_sha256'])
        self.declare();r=self.run_rebuild();self.assertEqual(r['status'],rebuild.PASSED,r)
        self.assertEqual(r['not_rebuildable_from_objects'],['title_history','title_review_history'])
        for c in r['checks']:self.assertNotIn(c['check'],r['excluded_checks'])
        expected=next(c['expected'] for c in r['checks'] if c['check']=='expected_tables')
        self.assertNotIn('title_history',expected);self.assertNotIn('title_review_history',expected)
        r=recovery.rehearse_recovery(self.manifest,self.db,self.root/'restored-check.json')
        self.assertIn('title_history',r['failed_checks']);self.assertIn('title_review_history',r['failed_checks'])
    def test_wrong_newline_and_plan_order_fail_without_reason_guess(self):
        self.add();self.add(newline='crlf');self.declare();original=copy.deepcopy(self.steps)
        for mode in ('newline','reverse'):
            self.steps=copy.deepcopy(original)
            if mode=='newline':
                for s in self.steps:s['newline']='crlf'
            else:self.steps.reverse()
            self.saveplan();r=self.run_rebuild();self.assertEqual(r['status'],rebuild.FAILED)
            self.assertFalse(self.db.exists());self.assertNotIn('PLATFORM',json.dumps(r));self.output.unlink()
    def test_missing_objects_and_changed_object_never_publish(self):
        digest=self.add();self.declare();p=self.objects/digest;raw=p.read_bytes();p.unlink()
        r=self.run_rebuild();self.assertEqual(r['status'],rebuild.FAILED);self.assertFalse(self.db.exists());self.output.unlink();p.write_bytes(raw)
        reader=rebuild._object_bytes
        def changed(path,expected):Path(path).write_bytes(b'synthetic changed');return reader(path,expected)
        with patch.object(rebuild,'_object_bytes',changed):r=self.run_rebuild()
        self.assertEqual(r['status'],rebuild.FAILED);self.assertFalse(self.db.exists());self.assertFalse(list(self.root.glob('.recap-*')))
    def test_receipt_failure_preserves_published_database(self):
        self.add();self.declare();before=self.live.read_bytes()
        with patch.object(recovery,'_publish_new_file',side_effect=OSError('synthetic')):
            with self.assertRaisesRegex(OSError,'database was preserved'):self.run_rebuild()
        self.assertTrue(self.db.exists());self.assertFalse(self.output.exists());self.assertEqual(self.live.read_bytes(),before)
    def test_database_publish_failure_keeps_failure_receipt_and_cleans_staging(self):
        self.add();self.declare();link=os.link
        def fail_db(src,dst):
            if Path(dst).resolve()==self.db.resolve():raise OSError('synthetic')
            return link(src,dst)
        with patch.object(os,'link',fail_db):r=self.run_rebuild()
        self.assertEqual(r['status'],rebuild.FAILED);self.assertFalse(self.db.exists());self.assertTrue(self.output.exists());self.assertFalse(list(self.root.glob('.recap-*')))
    def test_published_v3_rebuild_guide(self):
        out=self.root/'guide';out.mkdir();blocks=re.findall(r'```sh\n(.*?)```',Path('docs/REBUILD_V3.md').read_text(),re.S)
        self.assertEqual(len(blocks),1)
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);args[0]=sys.executable
            r=subprocess.run([p.replace('OUTPUT',str(out)) for p in args],capture_output=True)
            self.assertEqual(r.returncode,0,r.stderr);value=json.loads(r.stdout)
        self.assertEqual(value['schema'],'recap.rebuild-receipt.v3');self.assertEqual(value['status'],rebuild.PASSED)
        self.assertFalse(value['full_archive_restored'])
    def test_each_replayed_ledger_column_is_checked_before_publication(self):
        self.add();self.declare();check=recovery._archive_checks
        changes=dict(source='other',original_sha256='f'*64,original_bytes=0,format='local',selected_conversation='other',normalized_sha256='e'*64,extracted_messages=0)
        for column,value in changes.items():
            def alter(manifest,db,**kwargs):
                with closing(sqlite3.connect(db)) as c,c:c.execute('UPDATE original_exports SET '+column+'=?',(value,))
                return check(manifest,db,**kwargs)
            with self.subTest(column=column),patch.object(recovery,'_archive_checks',alter):r=self.run_rebuild()
            self.assertEqual(r['status'],rebuild.FAILED);self.assertIn('original_exports',r['failed_checks'])
            self.assertFalse(self.db.exists());self.assertFalse(list(self.root.glob('.recap-*')));self.output.unlink()
    def test_plain_normalized_v3_with_absent_origin_table_needs_no_fabrication(self):
        from recaplib.archive import ingest_bytes
        raw=Path('examples/conversations.jsonl').read_bytes();digest=hashlib.sha256(raw).hexdigest()
        (self.objects/digest).write_bytes(raw);ingest_bytes(self.live,'demo',raw)
        self.steps=[dict(source='demo',kind='normalized',object_sha256=digest,label=None,conversation=None,newline='lf')]
        self.declare();r=self.run_rebuild();self.assertEqual(r['status'],rebuild.PASSED,r)
        with closing(sqlite3.connect(self.db)) as c:
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='original_exports'").fetchone())
    def test_failure_receipt_never_echoes_private_parser_error(self):
        self.add();self.declare()
        with patch.object(rebuild,'import_export_bytes',side_effect=ValueError('PRIVATE_SYNTHETIC_BODY')):r=self.run_rebuild()
        self.assertEqual(r['status'],rebuild.FAILED);self.assertNotIn('PRIVATE_SYNTHETIC_BODY',json.dumps(r))
        self.assertNotIn(b'PRIVATE_SYNTHETIC_BODY',self.output.read_bytes());self.assertFalse(self.db.exists())
