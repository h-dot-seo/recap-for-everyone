"""Invented 24-conversation web/local organization scenario."""
import json
import sqlite3
from contextlib import closing
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from session_workflow import import_export, titles
from title_batch import review_queue, select_proposal
from title_proposal import preview, apply_preview


def synthetic_exports(directory):
    web=[];local=[]
    for index in range(12):
        web_text='Synthetic web planning topic '+str(index)
        local_text='Synthetic local planning topic '+str(index)
        if index < 2: web_text=local_text='Repeated synthetic planning topic'
        if index == 2: web_text='Hello';local_text='안녕하세요'
        if index == 4: web_text='Synthetic contact '+'invented'+'@'+'example.invalid'
        role='assistant' if index == 3 else 'user'
        web.append(dict(id=f'web-{index:02}',title='New chat',mapping={
            'm1':dict(parent=None,message=dict(author=dict(role=role),content=dict(parts=[web_text]))),
            'm2':dict(parent='m1',message=dict(author=dict(role='assistant'),content=dict(parts=['Synthetic reply'])))
        }))
        local.extend([dict(type='session_meta',payload=dict(id=f'local-{index:02}')),
                      dict(type='response_item',payload=dict(type='message',role=role,id=f'local-message-{index}',
                           content=[dict(type='input_text' if role=='user' else 'output_text',text=local_text)]))])
    web_path=directory/'web.json';local_path=directory/'local.jsonl'
    web_path.write_text(json.dumps(web),encoding='utf-8')
    local_path.write_text(''.join(json.dumps(r)+'\n' for r in local),encoding='utf-8')
    return web_path,local_path


class TitleQueueWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name);self.db=self.directory/'archive.sqlite'
        self.web,self.local=synthetic_exports(self.directory)
        import_export(self.db,'demo',self.web,'web');import_export(self.db,'demo',self.local,'local-codex')

    def test_twenty_four_conversation_workflow_excludes_completed_local_renames(self):
        raw=[self.web.read_bytes(),self.local.read_bytes()]
        for cid in ('local-00','local-01','local-02'):titles(self.db,'demo',cid,'Operator label '+cid,0)
        before=self.db.read_bytes();queue=review_queue(self.db,'demo',limit=5,unrenamed_only=True)
        self.assertEqual(before,self.db.read_bytes());self.assertEqual(queue['total_conversations'],21)
        self.assertEqual(queue['source_total_conversations'],24);self.assertEqual(queue['excluded_renamed_conversations'],3)
        self.assertFalse(any(item['previously_renamed'] for item in queue['items']))
        self.assertEqual(queue['items'][0]['conversation'],'local-03')
        self.assertEqual(queue['items'][0]['status'],'UNAVAILABLE')
        for cid in ('local-04','local-05'):
            apply_preview(self.db,preview(self.db,select_proposal(queue,cid),'Operator label '+cid))
        next_page=review_queue(self.db,'demo',limit=5,unrenamed_only=True)
        self.assertEqual(next_page['total_conversations'],19);self.assertEqual(next_page['excluded_renamed_conversations'],5)
        self.assertNotIn('local-04',[i['conversation'] for i in next_page['items']])
        self.assertNotIn('local-05',[i['conversation'] for i in next_page['items']])
        self.assertEqual(review_queue(self.db,'demo',limit=100)['total_conversations'],24)
        self.assertEqual(raw,[self.web.read_bytes(),self.local.read_bytes()])

    def test_eligible_pagination_and_collision_check_still_include_renamed_titles(self):
        titles(self.db,'demo','local-00','Repeated synthetic planning topic',0)
        all_items=[];offset=0
        while True:
            queue=review_queue(self.db,'demo',limit=4,offset=offset,unrenamed_only=True)
            all_items.extend(queue['items'])
            if queue['next_offset'] is None:break
            offset=queue['next_offset']
        self.assertEqual(len(all_items),23);self.assertEqual(len({i['conversation'] for i in all_items}),23)
        candidate=next(i for i in all_items if i['conversation']=='local-01')
        self.assertEqual(candidate['collisions']['existing_title_count'],1)
        self.assertEqual(candidate['collisions']['existing_title_conversations'],['local-00'])

    def test_any_history_including_reversion_is_excluded_but_other_source_not(self):
        titles(self.db,'demo','web-00','Temporary synthetic title',0)
        revision=titles(self.db,'demo','web-00')['revision']
        titles(self.db,'demo','web-00','New chat',revision)
        import_export(self.db,'other',self.web,'web')
        queue=review_queue(self.db,'demo',limit=100,unrenamed_only=True)
        self.assertNotIn('web-00',[item['conversation'] for item in queue['items']])
        self.assertEqual(review_queue(self.db,'other',unrenamed_only=True)['total_conversations'],12)
        self.assertEqual(titles(self.db,'demo','web-00')['display_title'],'New chat')

    def test_no_history_legacy_database_and_invalid_option(self):
        queue=review_queue(self.db,'demo',unrenamed_only=True)
        self.assertEqual(queue['total_conversations'],24);self.assertEqual(queue['excluded_renamed_conversations'],0)
        with self.assertRaises(ValueError):review_queue(self.db,'demo',unrenamed_only=1)

    def test_cli_selected_preview_apply_then_refresh_and_raw_search(self):
        def call(*args):
            result=subprocess.run([sys.executable,'recap.py','--db',str(self.db),*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
        queue=call('review-titles','--source','demo','--limit','24','--unrenamed-only')
        saved=self.directory/'queue.json';saved.write_text(json.dumps(queue))
        reviewed=call('preview-title',saved,'--conversation','web-04','--title','Synthetic contact planning')
        saved.write_text(json.dumps(reviewed));call('apply-title',saved)
        refreshed=call('review-titles','--source','demo','--limit','24','--unrenamed-only')
        self.assertEqual(refreshed['total_conversations'],23)
        self.assertNotIn('web-04',[i['conversation'] for i in refreshed['items']])
        self.assertEqual(call('find','invented','--source','demo')['total_matches'],1)
        self.assertEqual(call('list','--source','demo')['total'],24)

    def test_filter_counts_and_page_share_snapshot_during_concurrent_rename(self):
        import title_batch
        with closing(sqlite3.connect(self.db)) as connection:connection.execute('PRAGMA journal_mode=WAL')
        original=title_batch._inventory
        def rename_after_inventory(connection,*args,**kwargs):
            records=original(connection,*args,**kwargs)
            titles(self.db,'demo','local-00','Concurrent synthetic rename',0)
            return records
        with patch.object(title_batch,'_inventory',rename_after_inventory):
            queue=review_queue(self.db,'demo',unrenamed_only=True)
        self.assertEqual(queue['total_conversations'],24)
        self.assertEqual(queue['items'][0]['conversation'],'local-00')
        self.assertEqual(queue['items'][0]['current_revision'],0)
        self.assertEqual(review_queue(self.db,'demo',unrenamed_only=True)['total_conversations'],23)
