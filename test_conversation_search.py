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

    def test_cli_and_input_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'archive.sqlite'; import_export(db,'demo','examples/web-export.json','web')
            result=subprocess.run([sys.executable,'conversation_search.py','--db',str(db),'ORCHARD'],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['total_matches'],1)
            with self.assertRaises(ValueError): find(db,' ')
            with self.assertRaises(ValueError): find(db,'orchard',limit=0)
