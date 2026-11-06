import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from conversation_search import find
from session_workflow import import_export, titles


class ConversationSearchTests(unittest.TestCase):
    def test_renamed_title_sources_restore_and_readonly(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'archive.sqlite'
            for source in ('one','two'):
                import_export(db,source,'examples/web-export.json','web')
            changed=titles(db,'one','synthetic-chat','기전 연구 계획',0)
            before=hashlib.sha256(db.read_bytes()).hexdigest()
            result=find(db,'기전 orchard')
            self.assertEqual(result['total_matches'],1)
            self.assertEqual(result['matches'][0]['source_id'],'one')
            self.assertEqual(result['matches'][0]['display_title'],'기전 연구 계획')
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(),before)
            self.assertEqual(find(db,'기전',source='two')['matches'],[])
            self.assertEqual(find(db,"%' OR 1=1 --")['matches'],[])
            titles(db,'one','synthetic-chat','New chat',changed['revision'])
            self.assertEqual(find(db,'기전')['matches'],[])
            self.assertEqual(find(db,'orchard',limit=1)['total_matches'],2)
            self.assertTrue(find(db,'orchard',limit=1)['truncated'])

    def test_role_filter_limits_bodies_and_cursor_scope(self):
        from recap import ingest
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'archive.sqlite'
            path = Path(tmp) / 'synthetic.jsonl'
            records = [dict(conversation_id=cid, message_id=mid, role=role, timestamp='synthetic', title=title, text=text)
                for cid, mid, role, title, text in [('a', '1', 'user', 'needle title', 'ordinary'),
                    ('a', '2', 'assistant', 'needle title', 'secretword'), ('b', '3', 'user', 'Other', 'needle'),
                    ('c', '4', 'assistant', 'needle title', 'needle')]]
            path.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
            ingest(db, 'demo', path)
            self.assertEqual(find(db, 'secretword', text_role='user')['total_matches'], 0)
            result = find(db, 'needle', text_role='user', limit=1)
            self.assertEqual(result['total_matches'], 2)
            self.assertEqual(result['matches'][0]['conversation_id'], 'a')
            self.assertEqual(result['matches'][0]['message_count'], 1)
            self.assertEqual(find(db, 'needle', text_role='user', cursor=result['next_cursor'])['matches'][0]['conversation_id'], 'b')
            with self.assertRaises(ValueError): find(db, 'needle', text_role='assistant', cursor=result['next_cursor'])
            with self.assertRaises(ValueError): find(db, 'needle', text_role='invalid')
            for script in ('conversation_search.py', 'recap.py'):
                args = [sys.executable, script, '--db', str(db)] + (['find'] if script == 'recap.py' else [])
                result = subprocess.run(args + ['secretword', '--text-role', 'assistant'], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['total_matches'], 1)

    def test_cli_and_input_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'archive.sqlite'; import_export(db,'demo','examples/web-export.json','web')
            result=subprocess.run([sys.executable,'conversation_search.py','--db',str(db),'ORCHARD'],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['total_matches'],1)
            with self.assertRaises(ValueError): find(db,' ')
            with self.assertRaises(ValueError): find(db,'orchard',limit=0)
