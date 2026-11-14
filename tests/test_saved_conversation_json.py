"""Exact private show JSON, one exclusive output, ASCII receipt only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes
from recaplib.conversation_view import conversation
from recaplib.conversation_document import save_conversation
from recaplib.session_workflow import import_export
ROOT=Path(__file__).resolve().parents[1]


class SavedConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'archive.sqlite'
        rows=[dict(conversation_id='private-id',message_id=str(i),role='user',timestamp='supplied',title='한글 제목',text=text)
              for i,text in enumerate(['한글 🌱 <img> ```\n\x00','second','third'])]
        ingest_bytes(self.db,'synthetic',(''.join(json.dumps(row)+'\n' for row in rows)).encode())

    def save(self,**kw):return save_conversation(self.db,'synthetic','private-id',output=self.root/'show.json',**kw)

    def test_exact_object_unicode_and_private_receipt(self):
        before=self.db.read_bytes();receipt=self.save();raw=(self.root/'show.json').read_bytes()
        self.assertEqual(json.loads(raw),conversation(self.db,'synthetic','private-id'))
        self.assertIn('한글 🌱'.encode(),raw);self.assertTrue(raw.endswith(b'\n'));self.assertNotIn(b'\r\n',raw)
        self.assertEqual(receipt['sha256'],hashlib.sha256(raw).hexdigest())
        for value in ['private-id','한글','second']:self.assertNotIn(value,json.dumps(receipt,ensure_ascii=False))
        self.assertEqual(self.db.read_bytes(),before)

    def test_selection_parity(self):
        for index,kwargs in enumerate([dict(limit=1,offset=1),dict(message_id='2'),dict(around_message_id='1',before=1,after=0)]):
            output=self.root/str(index)
            save_conversation(self.db,'synthetic','private-id',output=output,**kwargs)
            self.assertEqual(json.loads(output.read_bytes()),conversation(self.db,'synthetic','private-id',**kwargs))

    def test_existing_output_rejected_before_archive_read(self):
        output=self.root/'show.json';output.write_bytes(b'preserved')
        with patch('recaplib.conversation_document.conversation',side_effect=AssertionError('must preflight')):
            with self.assertRaises(FileExistsError):self.save()
        self.assertEqual(output.read_bytes(),b'preserved')

    def test_invalid_selection_missing_conversation_and_size_fail_without_file(self):
        for kw in [dict(limit=0),dict(message_id='absent')]:
            with self.assertRaises(ValueError):self.save(**kw)
            self.assertFalse((self.root/'show.json').exists())
        with patch('recaplib.conversation_document.MAX_OUTPUT_BYTES',1):
            with self.assertRaisesRegex(ValueError,'output limit'):self.save()
        self.assertFalse((self.root/'show.json').exists())

    def test_unicode_surrogates_roundtrip_as_json_escapes(self):
        value=dict(text='한글\ud800 separated \udfff')
        with patch('recaplib.conversation_document.conversation',return_value=value):self.save()
        raw=(self.root/'show.json').read_bytes();raw.decode('utf-8')
        self.assertEqual(json.loads(raw),value)

    def test_provenance_remains_identical(self):
        import_export(self.db,'web',ROOT/'examples/web-export.json','web')
        from recaplib.conversation_view import conversations
        cid=conversations(self.db,'web')['conversations'][0]['conversation']
        output=self.root/'web.json';save_conversation(self.db,'web',cid,output=output)
        self.assertEqual(json.loads(output.read_bytes()),conversation(self.db,'web',cid))

    def test_standalone_and_unified_ascii_receipt_parity(self):
        env=dict(os.environ,PYTHONIOENCODING='ascii');receipts=[]
        for index,script in enumerate(['recap.py','conversation_view.py']):
            output=self.root/('cli'+str(index))
            run=subprocess.run([sys.executable,str(ROOT/script),'--db',str(self.db),'show','--source','synthetic','--conversation','private-id','--output',str(output)],env=env,capture_output=True,check=True)
            self.assertTrue(run.stdout.isascii());receipts.append(json.loads(run.stdout))
        self.assertEqual(receipts[0],receipts[1]);self.assertEqual((self.root/'cli0').read_bytes(),(self.root/'cli1').read_bytes())

    def test_documented_walkthrough(self):
        import re
        import shlex
        block=re.search(r'```sh\n(.*?)```',(ROOT/'docs/SAVED_CONVERSATION_JSON.md').read_text(),re.S).group(1)
        output=self.root/'walkthrough space';last=None
        for line in block.strip().splitlines():
            args=[x.replace('OUTPUT',str(output)) for x in shlex.split(line)]
            if args[0]=='mkdir':Path(args[1]).mkdir();continue
            args[0]=sys.executable
            run=subprocess.run(args,cwd=ROOT,capture_output=True,env=dict(os.environ,PYTHONIOENCODING='ascii'))
            self.assertEqual(run.returncode,0,run.stderr);self.assertTrue(run.stdout.isascii());last=args
        value=json.loads((output/'conversation.json').read_bytes())
        self.assertEqual(value['selection']['returned_messages'],1)
        before=(output/'conversation.json').read_bytes()
        run=subprocess.run(last,cwd=ROOT,capture_output=True)
        self.assertEqual(run.returncode,1);self.assertEqual((output/'conversation.json').read_bytes(),before)
