"""Saved queue leases reduce copy steps without silently renewing permission."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from recaplib.session_workflow import import_export,titles
from recaplib.title_batch import review_queue
from recaplib.title_review_state import review_state,review_state_from_queue
from tests.test_title_queue_workflow import synthetic_exports


class QueueDecisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name);self.db=self.directory/'archive.sqlite'
        self.web,self.local=synthetic_exports(self.directory)
        import_export(self.db,'demo',self.web,'web');import_export(self.db,'demo',self.local,'local-codex')
        self.queue=review_queue(self.db,'demo',limit=100)

    def decide(self,queue=None,cid='web-04',state='deferred',source='demo'):
        return review_state_from_queue(self.db,source,cid,state,self.queue if queue is None else queue)

    def test_saved_lease_used_without_refresh_and_queue_unchanged(self):
        original=copy.deepcopy(self.queue)
        result=self.decide();self.assertEqual(result['state'],'deferred')
        self.assertEqual(self.queue,original)
        before=self.db.read_bytes()
        with self.assertRaisesRegex(ValueError,'stale'):self.decide()
        self.assertEqual(before,self.db.read_bytes())
        self.assertEqual(titles(self.db,'demo','web-04')['revision'],0)
        self.assertEqual(review_state(self.db,'demo','web-05')['state'],'open')

    def test_unavailable_suggestion_can_be_explicitly_skipped(self):
        item=next(i for i in self.queue['items'] if i['conversation']=='web-03')
        self.assertEqual(item['status'],'UNAVAILABLE')
        self.assertEqual(self.decide(cid='web-03',state='skipped')['state'],'skipped')
        self.assertEqual(titles(self.db,'demo','web-03')['revision'],0)

    def test_source_duplicates_missing_item_and_missing_lease_rejected(self):
        before=self.db.read_bytes()
        with self.assertRaises(ValueError):self.decide(source='other')
        with self.assertRaises(ValueError):self.decide(cid='absent')
        with self.assertRaises(ValueError):self.decide(state=None)
        duplicate=copy.deepcopy(self.queue);duplicate['items'].append(next(i for i in duplicate['items'] if i['conversation']=='web-04'))
        with self.assertRaises(ValueError):self.decide(duplicate)
        for key in ('review_state','state_revision','expected_title_revision','expected_content_sha256'):
            queue=copy.deepcopy(self.queue);item=next(i for i in queue['items'] if i['conversation']=='web-04')
            if key=='review_state':del item[key]
            else:del item['review_state'][key]
            with self.assertRaises(ValueError):self.decide(queue)
        self.assertEqual(before,self.db.read_bytes())

    def test_invalid_or_altered_lease_and_changed_title_rejected(self):
        for key,value in [('state_revision',True),('state_revision',1),('expected_title_revision',True),
                          ('expected_title_revision',1),('expected_content_sha256','0'*64)]:
            queue=copy.deepcopy(self.queue)
            next(i for i in queue['items'] if i['conversation']=='web-04')['review_state'][key]=value
            before=self.db.read_bytes()
            with self.assertRaises(ValueError):self.decide(queue)
            self.assertEqual(before,self.db.read_bytes())
        titles(self.db,'demo','web-04','Explicit new title',0)
        with self.assertRaisesRegex(ValueError,'stale'):self.decide()

    def test_two_same_queue_decisions_have_one_winner(self):
        def attempt(state):
            try:return self.decide(state=state)['state']
            except ValueError as error:
                self.assertIn('stale',str(error));return 'STALE'
        with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(attempt,['skipped','deferred']))
        self.assertEqual(results.count('STALE'),1)

    def test_cli_24_session_defer_revisit_edit_reopen_end_to_end(self):
        db=self.directory/'cli.sqlite'
        def call(*args,ok=True):
            result=subprocess.run([sys.executable,'recap.py','--db',str(db),*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0 if ok else 1,result.stderr);self.assertNotIn('Traceback',result.stderr)
            return json.loads(result.stdout) if ok else result
        call('import',self.web,'--format','web','--source','demo')
        call('import',self.local,'--format','local-codex','--source','demo')
        queue=call('review-titles','--source','demo','--limit','24','--state','open')
        self.assertEqual(queue['total_conversations'],24)
        saved=self.directory/'queue.json';saved.write_text(json.dumps(queue));original=saved.read_bytes()
        decision=('review-state','--source','demo','--conversation','web-04','--set','deferred','--from-queue',saved)
        call(*decision);call(*decision,ok=False);self.assertEqual(saved.read_bytes(),original)
        deferred=call('review-titles','--source','demo','--state','deferred')
        self.assertEqual([i['conversation'] for i in deferred['items']],['web-04'])
        saved.write_text(json.dumps(deferred))
        reviewed=call('preview-title',saved,'--conversation','web-04','--title','Synthetic contact planning')
        review_file=self.directory/'reviewed.json';review_file.write_text(json.dumps(reviewed))
        call('apply-title',review_file)
        call('review-state','--source','demo','--conversation','web-04','--set','open','--from-queue',saved,ok=False)
        refreshed=call('review-titles','--source','demo','--limit','24','--state','open')
        item=next(i for i in refreshed['items'] if i['conversation']=='web-04')
        self.assertTrue(item['review_state']['stale_decision'])
        saved.write_text(json.dumps(refreshed))
        call('review-state','--source','demo','--conversation','web-04','--set','open','--from-queue',saved)
        self.assertEqual(call('title','--source','demo','--conversation','web-04')['display_title'],'Synthetic contact planning')
        self.assertEqual(call('find','invented','--source','demo')['total_matches'],1)
        self.assertEqual(call('list','--source','demo')['total'],24)

    def test_cli_disallows_implicit_decision_and_mixed_leases(self):
        saved=self.directory/'queue.json';saved.write_text(json.dumps(self.queue))
        base=[sys.executable,'recap.py','--db',str(self.db),'review-state','--source','demo','--conversation','web-04','--from-queue',str(saved)]
        before=self.db.read_bytes()
        for extra in ([],['--set','skipped','--expected-state-revision','0']):
            result=subprocess.run(base+extra,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,1);self.assertEqual(result.stdout,'');self.assertNotIn('Traceback',result.stderr)
        saved.write_text('{"items":[],"items":[]}')
        result=subprocess.run(base+['--set','skipped'],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,1);self.assertNotIn('Traceback',result.stderr)
        self.assertEqual(before,self.db.read_bytes())
