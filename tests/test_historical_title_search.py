"""Find an organized conversation by an old local label without changing history."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from recap import ingest
from recaplib.session_workflow import import_export,titles
from recaplib.conversation_search import find
from tests.test_title_queue_workflow import synthetic_exports


class HistoricalTitleSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name);self.db=self.directory/'archive.sqlite'
        self.web,self.local=synthetic_exports(self.directory)
        import_export(self.db,'demo',self.web,'web');import_export(self.db,'demo',self.local,'local-codex')

    def rename(self,cid,label):
        current=titles(self.db,'demo',cid)
        return titles(self.db,'demo',cid,label,current['revision'])

    def test_old_label_finds_current_conversation_only_when_opted_in(self):
        first=self.rename('web-05','Orchard watering comparison')
        final=self.rename('web-05','Irrigation shade plan')
        self.assertEqual(find(self.db,'watering')['total_matches'],0)
        before=self.db.read_bytes();result=find(self.db,'watering',include_title_history=True)
        self.assertEqual(result['total_matches'],1)
        hit=result['matches'][0]
        self.assertEqual(hit['display_title'],'Irrigation shade plan');self.assertEqual(hit['title_revision'],final['revision'])
        self.assertFalse(hit['matched_title']);self.assertTrue(hit['matched_historical_title'])
        self.assertEqual(hit['historical_title_matches'],[dict(title='Orchard watering comparison',title_revision=first['revision'],origin='prior_local_override')])
        self.assertEqual(before,self.db.read_bytes())

    def test_archived_original_is_prior_only_after_local_override(self):
        self.rename('web-00','Distinct current label')
        result=find(self.db,'new chat',source='demo',include_title_history=True)
        hit=next(x for x in result['matches'] if x['conversation_id']=='web-00')
        self.assertEqual(hit['historical_title_matches'][0]['origin'],'archived_original_title')
        self.assertEqual(hit['historical_title_matches'][0]['title_revision'],0)
        self.assertFalse(hit['matched_title'])
        untouched=next(x for x in result['matches'] if x['conversation_id']=='web-01')
        self.assertFalse(untouched['matched_historical_title'])

    def test_ranking_current_then_historical_then_body_and_exact_totals(self):
        self.rename('web-00','Rankneedle current')
        self.rename('local-00','Rankneedle old');self.rename('local-00','Unrelated label')
        path=self.directory/'extra.jsonl'
        path.write_text(json.dumps(dict(conversation_id='aaa-body',message_id='u',role='user',timestamp='synthetic',text='Rankneedle in body',title='Other'))+'\n')
        ingest(self.db,'demo',path)
        result=find(self.db,'rankneedle',limit=2,include_title_history=True)
        self.assertEqual(result['total_matches'],3);self.assertTrue(result['truncated'])
        self.assertEqual([r['conversation_id'] for r in result['matches']],['web-00','local-00'])

    def test_terms_can_span_current_history_and_body_with_bounded_history_samples(self):
        for i in range(6):self.rename('web-05',f'Historicalneedle version {i}')
        self.rename('web-05','Currentneedle')
        result=find(self.db,'historicalneedle currentneedle planning',include_title_history=True)
        hit=result['matches'][0]
        self.assertEqual(hit['historical_title_match_count'],6)
        self.assertEqual(len(hit['historical_title_matches']),3);self.assertTrue(hit['historical_title_matches_truncated'])
        self.assertEqual([r['title'] for r in hit['historical_title_matches']],['Historicalneedle version 5','Historicalneedle version 4','Historicalneedle version 3'])
        self.assertTrue(hit['message_matches'])

    def test_source_isolation_missing_history_and_invalid_option(self):
        self.assertEqual(find(self.db,'unlikely-history-label',include_title_history=True)['total_matches'],0)
        import_export(self.db,'other',self.web,'web')
        self.rename('web-00','Historicalneedle old');self.rename('web-00','Current label')
        self.assertEqual(find(self.db,'historicalneedle',source='other',include_title_history=True)['total_matches'],0)
        with self.assertRaises(ValueError):find(self.db,'anything',include_title_history=1)
        missing=self.directory/'missing.sqlite'
        with self.assertRaises(sqlite3.Error):find(missing,'anything',include_title_history=True)
        self.assertFalse(missing.exists())

    def test_one_read_snapshot_during_concurrent_rename(self):
        from recaplib import conversation_search
        self.rename('web-05','Snapshotneedle old');self.rename('web-05','Before concurrent title')
        with closing(sqlite3.connect(self.db)) as c:c.execute('PRAGMA journal_mode=WAL')
        real_readonly=conversation_search.readonly;changed=[]
        def open_with_trace(path):
            connection=real_readonly(path)
            def trace(sql):
                if sql.startswith('SELECT * FROM messages') and not changed:
                    changed.append(True);self.rename('web-05','After concurrent title')
            connection.set_trace_callback(trace);return connection
        with patch.object(conversation_search,'readonly',open_with_trace):result=find(self.db,'snapshotneedle',include_title_history=True)
        self.assertTrue(changed)
        self.assertEqual(result['matches'][0]['display_title'],'Before concurrent title')
        self.assertEqual(find(self.db,'snapshotneedle',include_title_history=True)['matches'][0]['display_title'],'After concurrent title')

    def test_cli_retrieves_old_title_after_edit_defer_revisit_and_preserves_data(self):
        def call(script,*args):
            result=subprocess.run([sys.executable,script,'--db',str(self.db),*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
        saved=self.directory/'queue.json'
        queue=call('recap.py','review-titles','--source','demo','--limit','24');saved.write_text(json.dumps(queue))
        call('recap.py','review-state','--source','demo','--conversation','web-05','--set','deferred','--from-queue',saved)
        deferred=call('recap.py','review-titles','--source','demo','--state','deferred');saved.write_text(json.dumps(deferred))
        for label in ('Orchard watering comparison','Irrigation shade plan'):
            reviewed=call('recap.py','preview-title',saved,'--conversation','web-05','--title',label)
            review_file=self.directory/'reviewed.json';review_file.write_text(json.dumps(reviewed));call('recap.py','apply-title',review_file)
        before=self.db.read_bytes()
        self.assertEqual(call('recap.py','find','watering')['total_matches'],0)
        found=call('recap.py','find','watering','--include-title-history')
        self.assertEqual(found,call('conversation_search.py','watering','--include-title-history'))
        self.assertEqual(found['matches'][0]['display_title'],'Irrigation shade plan')
        self.assertEqual(call('recap.py','list','--source','demo')['total'],24)
        self.assertEqual(call('recap.py','find','synthetic')['total_matches'],23)  # Korean greeting-only local session has no such word
        self.assertEqual(before,self.db.read_bytes())
