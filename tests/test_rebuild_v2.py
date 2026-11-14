"""Synthetic v2 object replay excludes decisions, never full restoration."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from recaplib import rebuild,recovery
from recaplib.session_workflow import import_export_bytes,titles
from recaplib.title_review_state import review_state
from tests.test_web_branch import fixture


class RebuildV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.live=self.root/'live.sqlite'
        self.objects=self.root/'objects';self.objects.mkdir()
        self.manifest=self.root/'manifest.json';self.plan=self.root/'plan.json'
        self.db=self.root/'rebuilt.sqlite';self.output=self.root/'receipt.json'
        self.steps=[]

    def add(self,data=None):
        raw=json.dumps(fixture() if data is None else data).encode()
        digest=hashlib.sha256(raw).hexdigest();(self.objects/digest).write_bytes(raw)
        import_export_bytes(self.live,'demo',raw,None,'web',newline='lf')
        self.steps.append(dict(source='demo',kind='web',object_sha256=digest,label=None,conversation=None,newline='lf'))

    def declare(self):
        recovery.declare_recovery(self.live,self.manifest,'2026-11-14',manifest_version=2)
        self.plan.write_text(json.dumps(dict(schema=rebuild.PLAN_SCHEMA,steps=self.steps)))

    def run_rebuild(self):
        return rebuild.rebuild_archive(self.manifest,self.plan,self.objects,self.db,self.output)

    def histories(self):
        titles(self.live,'demo','synthetic','Synthetic choice',0)
        lease=review_state(self.live,'demo','synthetic')
        review_state(self.live,'demo','synthetic','skipped',lease['state_revision'],lease['expected_title_revision'],lease['expected_content_sha256'])

    def test_declared_histories_excluded_never_passed_or_restored(self):
        self.add();self.histories();self.declare();before=self.live.read_bytes()
        result=self.run_rebuild();self.assertEqual(result['status'],rebuild.PASSED,result)
        self.assertEqual(result['schema'],'recap.rebuild-receipt.v2')
        self.assertEqual(result['manifest']['schema'],'recap.recovery-manifest.v2')
        self.assertFalse(result['full_archive_restored'])
        self.assertEqual(result['not_rebuildable_from_objects'],['title_history','title_review_history'])
        self.assertEqual(result['excluded_checks'],['title_history','title_review_history'])
        self.assertEqual(result['review_state'],'NOT_REBUILDABLE_FROM_OBJECTS')
        names=[c['check'] for c in result['checks']]
        self.assertNotIn('title_history',names);self.assertNotIn('title_review_history',names)
        expected=next(c for c in result['checks'] if c['check']=='expected_tables')['expected']
        self.assertNotIn('title_history',expected);self.assertNotIn('title_review_history',expected)
        self.assertEqual(result['checks_run'],12)
        with closing(sqlite3.connect(self.db)) as c:
            names={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn('title_history',names);self.assertNotIn('title_review_history',names)
        self.assertEqual(self.live.read_bytes(),before);self.assertFalse(list(self.root.glob('.recap-*')))
        result=recovery.rehearse_recovery(self.manifest,self.db,self.root/'restore-check.json')
        self.assertEqual(result['status'],recovery.FAILED)
        self.assertIn('title_history',result['failed_checks']);self.assertIn('title_review_history',result['failed_checks'])

    def test_absent_histories_are_not_claimed_as_rebuildable(self):
        self.add();self.declare();result=self.run_rebuild()
        self.assertEqual(result['status'],rebuild.PASSED,result)
        self.assertEqual(result['not_rebuildable_from_objects'],[])
        self.assertEqual(result['review_state'],'NOT_DECLARED')
        self.assertFalse(result['full_archive_restored'])

    def test_every_replay_ledger_digest_mismatch_prevents_publication(self):
        self.add();self.declare();original=self.manifest.read_bytes()
        for name in ('export_provenance','export_nodes','export_conversations','export_occurrences'):
            with self.subTest(name=name):
                value=json.loads(original)
                if name=='export_occurrences':value['export_occurrences_sha256']='0'*64
                else:value[name]['sha256']='0'*64
                self.manifest.write_text(json.dumps(value));result=self.run_rebuild()
                self.assertEqual(result['status'],rebuild.FAILED)
                self.assertIn(name,result['failed_checks']);self.assertFalse(self.db.exists())
                self.assertFalse(list(self.root.glob('.recap-*')));self.output.unlink()

    def test_unexpected_replayed_ledger_is_not_dropped_to_force_match(self):
        self.add()
        with closing(sqlite3.connect(self.live)) as c,c:
            c.execute('DROP TABLE export_nodes');c.execute('DROP TABLE export_conversations')
        self.declare();result=self.run_rebuild()
        self.assertEqual(result['status'],rebuild.FAILED)
        self.assertIn('export_nodes',result['failed_checks']);self.assertIn('export_conversations',result['failed_checks'])
        self.assertFalse(self.db.exists())

    def test_legacy_only_object_coverage_is_not_inferred_or_expanded(self):
        self.add()
        with closing(sqlite3.connect(self.live)) as c,c:c.execute('DROP TABLE export_occurrences')
        self.declare();result=self.run_rebuild()
        self.assertEqual(result['status'],rebuild.FAILED);self.assertFalse(self.db.exists())
        self.assertEqual(result['failure']['phase'],'PLAN_OBJECT_DECLARATION')

    def test_zero_message_export_hash_is_not_guessed_from_topology(self):
        data=fixture();data[0]['mapping']={'root':dict(parent=None,message=None)};data[0]['current_node']='root'
        self.add(data);self.declare();result=self.run_rebuild()
        self.assertEqual(result['status'],rebuild.FAILED);self.assertFalse(self.db.exists())
        self.assertEqual(result['failure']['phase'],'PLAN_OBJECT_DECLARATION')

    def test_textless_conversation_in_declared_export_is_replayed(self):
        data=fixture();data.append(dict(id='empty-synthetic',mapping={'root':dict(parent=None,message=None)},current_node='root'))
        self.add(data);self.declare();result=self.run_rebuild()
        self.assertEqual(result['status'],rebuild.PASSED,result)
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute("SELECT mapping_nodes FROM export_conversations WHERE conversation='empty-synthetic'").fetchone()[0],1)

    def test_receipt_failure_after_database_publication_preserves_database(self):
        self.add();self.declare();before=self.live.read_bytes()
        with patch.object(recovery,'_publish_new_file',side_effect=OSError('synthetic failure')):
            with self.assertRaisesRegex(OSError,'database was preserved'):self.run_rebuild()
        self.assertTrue(self.db.is_file());self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.recap-*')));self.assertEqual(self.live.read_bytes(),before)

    def test_database_link_failure_no_partial_database_or_staging(self):
        self.add();self.declare();link=os.link;injected=[]
        def fail_db(source,destination):
            if Path(destination).resolve()==self.db.resolve():
                injected.append(destination);raise OSError('synthetic db publish failure')
            return link(source,destination)
        with patch.object(os,'link',fail_db):result=self.run_rebuild()
        self.assertEqual(len(injected),1);self.assertEqual(result['status'],rebuild.FAILED)
        self.assertFalse(self.db.exists());self.assertFalse(list(self.root.glob('.recap-*')))
        self.assertEqual(json.loads(self.output.read_text())['status'],rebuild.FAILED)

    def test_published_v2_rebuild_guide(self):
        import re,shlex,subprocess,sys
        blocks=re.findall(r'```sh\n(.*?)```',Path('docs/REBUILD_V2.md').read_text(),re.S)
        self.assertEqual(len(blocks),1);root=self.root/'guide';root.mkdir();results=[]
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);self.assertEqual(args.pop(0),'python')
            result=subprocess.run([sys.executable,*[part.replace('OUTPUT',str(root)) for part in args]],capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);results.append(json.loads(result.stdout))
        self.assertEqual(results[-1]['schema'],'recap.rebuild-receipt.v2')
        self.assertEqual(results[-1]['status'],rebuild.PASSED);self.assertFalse(results[-1]['full_archive_restored'])
