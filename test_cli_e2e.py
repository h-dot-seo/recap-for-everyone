import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliScenario(unittest.TestCase):
    def call(self, script, *args, success=True):
        result=subprocess.run([sys.executable,script,*map(str,args)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode==0,success,result.stderr)
        return json.loads(result.stdout) if success else result.stderr

    def test_import_search_review_apply_reject_and_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'archive.sqlite'
            args=('--db',db,'import','examples/web-export.json','--format','web','--source','demo')
            self.assertEqual(self.call('session_workflow.py',*args)['inserted'],2)
            self.assertEqual(self.call('session_workflow.py',*args)['inserted'],0)
            self.call('session_workflow.py','--db',db,'import','examples/local-session.jsonl','--format','local','--source','local')
            self.assertEqual(len(self.call('recap.py','--db',db,'search','orchard')),2)
            snapshot=self.call('title_proposal.py','--db',db,'snapshot','--source','demo','--conversation','synthetic-chat')
            proposal=dict(source='demo',conversation='synthetic-chat',content_sha256=snapshot['content_sha256'],title='Synthetic orchard plan',provider='synthetic-mock',evidence_message_ids=['m1'])
            path=Path(folder)/'proposal.json'; path.write_text(json.dumps(proposal),encoding='utf-8')
            reviewed=self.call('title_proposal.py','--db',db,'preview',path)
            path.write_text(json.dumps(reviewed),encoding='utf-8')
            changed=self.call('title_proposal.py','--db',db,'apply',path)
            self.call('title_proposal.py','--db',db,'apply',path,success=False)
            restored=self.call('session_workflow.py','--db',db,'title','--source','demo','--conversation','synthetic-chat','--set','New chat','--expected-revision',changed['revision'])
            self.assertEqual(restored['display_title'],'New chat')

    def test_malformed_web_input_has_no_partial_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'archive.sqlite'; path=Path(folder)/'bad.json'
            path.write_text(json.dumps([dict(id='synthetic',mapping={'m':dict(parent='missing',message=None)})]))
            self.call('session_workflow.py','--db',db,'import',path,'--format','web','--source','demo',success=False)
            self.assertFalse(db.exists())
