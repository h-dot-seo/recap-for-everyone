"""Synthetic review decisions: leased, additive, atomic and separate from titles."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from session_workflow import import_export, titles
from title_batch import review_queue
from title_review_state import review_state


class ReviewStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'archive.sqlite'
        self.source=Path('examples/web-export.json')
        import_export(self.db,'web',self.source,'web')

    def read(self):return review_state(self.db,'web','synthetic-chat')

    def write(self,state,lease=None):
        lease=lease or self.read()
        return review_state(self.db,'web','synthetic-chat',state,lease['state_revision'],lease['expected_title_revision'],lease['expected_content_sha256'])

    def test_legacy_read_does_not_create_schema_and_decisions_do_not_rename(self):
        before=self.db.read_bytes();raw=self.source.read_bytes();initial=self.read()
        self.assertEqual(initial['state'],'open');self.assertEqual(initial['state_revision'],0)
        self.assertEqual(before,self.db.read_bytes())
        skipped=self.write('skipped',initial);self.assertTrue(skipped['decision_current'])
        self.assertEqual(skipped['state'],'skipped')
        deferred=self.write('deferred',skipped);opened=self.write('open',deferred)
        self.assertGreater(opened['state_revision'],deferred['state_revision'])
        self.assertEqual(titles(self.db,'web','synthetic-chat')['revision'],0)
        self.assertEqual(self.source.read_bytes(),raw)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT state FROM title_review_history ORDER BY id').fetchall(),[('skipped',),('deferred',),('open',)])
            self.assertEqual(connection.execute('SELECT count(*) FROM messages').fetchone()[0],2)

    def test_stale_state_content_and_title_leases_rejected(self):
        old=self.read();self.write('skipped',old);before=self.db.read_bytes()
        with self.assertRaisesRegex(ValueError,'stale'):self.write('deferred',old)
        self.assertEqual(before,self.db.read_bytes())
        lease=self.read();titles(self.db,'web','synthetic-chat','Reviewed title',0)
        with self.assertRaisesRegex(ValueError,'stale'):self.write('deferred',lease)
        current=self.read();self.assertEqual(current['state'],'open');self.assertTrue(current['stale_decision'])
        self.assertEqual(current['recorded_state'],'skipped')
        self.write('deferred',current)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE messages SET text='Changed synthetic text' WHERE role='user'");connection.commit()
        changed=self.read();self.assertTrue(changed['stale_decision']);self.assertEqual(changed['state'],'open')
        self.assertEqual(changed['recorded_state'],'deferred')
        with self.assertRaisesRegex(ValueError,'stale'):self.write('skipped',current)

    def test_queue_state_is_visible_without_hiding_or_applying(self):
        self.write('deferred')
        queue=review_queue(self.db,'web',unrenamed_only=True)
        self.assertEqual(queue['total_conversations'],1)
        self.assertEqual(queue['items'][0]['review_state']['state'],'deferred')
        self.assertEqual(queue['items'][0]['current_revision'],0)
        titles(self.db,'web','synthetic-chat','Explicit title',0)
        queue=review_queue(self.db,'web')
        self.assertEqual(queue['items'][0]['review_state']['state'],'open')
        self.assertTrue(queue['items'][0]['review_state']['stale_decision'])
        self.assertTrue(queue['items'][0]['previously_renamed'])

    def test_invalid_inputs_and_unknown_conversation_do_not_create_schema(self):
        lease=self.read();before=self.db.read_bytes()
        for state,revision in [('invalid',0),('skipped',None),('skipped',True),('skipped',2**63)]:
            with self.assertRaises(ValueError):review_state(self.db,'web','synthetic-chat',state,revision,0,lease['expected_content_sha256'])
        with self.assertRaises(ValueError):review_state(self.db,'web','synthetic-chat','skipped',0,0,'bad')
        with self.assertRaises(ValueError):review_state(self.db,'web','missing','skipped',0,0,lease['expected_content_sha256'])
        with self.assertRaises(ValueError):review_state(self.db,'web','synthetic-chat',expected_state_revision=0)
        self.assertEqual(before,self.db.read_bytes())
        missing=Path(self.tmp.name)/'missing.sqlite'
        with self.assertRaises(sqlite3.Error):review_state(missing,'web','synthetic-chat','skipped',0,0,lease['expected_content_sha256'])
        self.assertFalse(missing.exists())

    def test_first_write_failure_rolls_back_schema_and_event_atomically(self):
        import title_review_state
        lease=self.read();before=self.db.read_bytes()
        connection=sqlite3.connect(self.db)
        def authorizer(action,table,*unused):
            return sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_INSERT and table=='title_review_history' else sqlite3.SQLITE_OK
        connection.set_authorizer(authorizer)
        with patch.object(title_review_state.sqlite3,'connect',return_value=connection):
            with self.assertRaises(sqlite3.DatabaseError):self.write('skipped',lease)
        self.assertEqual(before,self.db.read_bytes())
        with closing(sqlite3.connect(self.db)) as check:
            self.assertIsNone(check.execute("SELECT name FROM sqlite_master WHERE name='title_review_history'").fetchone())

    def test_concurrent_same_lease_has_exactly_one_winner(self):
        lease=self.read()
        def attempt(state):
            try:return self.write(state,lease)['state']
            except ValueError as error:
                self.assertIn('stale',str(error));return 'STALE'
        with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(attempt,['skipped','deferred']))
        self.assertEqual(results.count('STALE'),1)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM title_review_history').fetchone()[0],1)
        self.assertEqual(titles(self.db,'web','synthetic-chat')['revision'],0)

    def test_source_isolation_and_same_state_repeat_requires_fresh_lease(self):
        import_export(self.db,'other',self.source,'web')
        old=self.read();self.write('skipped',old)
        with self.assertRaises(ValueError):self.write('skipped',old)
        self.assertEqual(review_state(self.db,'other','synthetic-chat')['state'],'open')
        current=self.read();again=self.write('skipped',current)
        self.assertGreater(again['state_revision'],current['state_revision'])

    def test_cli_read_defer_reopen_and_stale_failure(self):
        def call(*args,ok=True):
            result=subprocess.run([sys.executable,'recap.py','--db',str(self.db),'review-state','--source','web','--conversation','synthetic-chat',*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0 if ok else 1,result.stderr);self.assertNotIn('Traceback',result.stderr)
            return json.loads(result.stdout) if ok else result
        lease=call()
        args=('--set','deferred','--expected-state-revision',lease['state_revision'],'--expected-title-revision',lease['expected_title_revision'],'--expected-content-sha256',lease['expected_content_sha256'])
        changed=call(*args);self.assertEqual(changed['state'],'deferred')
        before=self.db.read_bytes();call(*args,ok=False);self.assertEqual(before,self.db.read_bytes())
        reopened=call('--set','open','--expected-state-revision',changed['state_revision'],'--expected-title-revision',changed['expected_title_revision'],'--expected-content-sha256',changed['expected_content_sha256'])
        self.assertEqual(reopened['state'],'open')
        call('--set','skipped',ok=False)

    def test_queue_decision_is_in_same_snapshot_as_title_and_content(self):
        import title_batch
        self.write('skipped')
        with closing(sqlite3.connect(self.db)) as connection:connection.execute('PRAGMA journal_mode=WAL')
        original=title_batch.state_snapshot
        def change_then_read(connection,source,conversation,digest,title_revision):
            self.write('deferred')
            return original(connection,source,conversation,digest,title_revision)
        with patch.object(title_batch,'state_snapshot',change_then_read):queue=review_queue(self.db,'web')
        self.assertEqual(queue['items'][0]['review_state']['state'],'skipped')
        self.assertEqual(self.read()['state'],'deferred')
