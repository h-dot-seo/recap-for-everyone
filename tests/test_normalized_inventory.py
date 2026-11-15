"""Normalized inventory is read-only inspection, not selected ingest admission."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import validate_normalized
from recaplib.export_inventory import list_export
from recaplib.session_workflow import import_export,inspect_normalized
from recaplib.title_plan import make_plan

ROOT=Path(__file__).resolve().parents[1]
class NormalizedInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'synthetic.jsonl'
        self.row=dict(conversation_id='c',message_id='m',role='user',timestamp='t',text='PRIVATE BODY',title='First')
    def write(self,rows):
        raw=('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n').encode();self.path.write_bytes(raw);return raw
    def test_titles_order_counts_and_conflicts_are_not_silently_merged(self):
        raw=self.write([self.row,self.row,dict(self.row,text='changed',title='Second'),dict(self.row,message_id='n',title=''),dict(self.row,conversation_id='a',title='Other')])
        with patch('sqlite3.connect',side_effect=AssertionError('no database')):result=list_export(self.path,'normalized')
        self.assertEqual(result['coverage'],validate_normalized(raw)[1]);self.assertEqual(result['selectable_conversations'],0)
        a,c=result['conversations'];self.assertEqual(c['original_titles'],['First','Second',''])
        self.assertEqual(c['metadata_records'],4);self.assertEqual(c['extracted_messages'],4);self.assertEqual(c['role_counts'],{'user':4})
        self.assertFalse(c['selection_supported']);self.assertEqual(c['selection_blocker'],'NOT_SUPPORTED')
        self.assertNotIn('PRIVATE BODY',json.dumps(result));self.assertEqual(result['coverage']['repeated_input'],{'identical':1,'conflicting':1})
    def test_empty_bom_and_physical_newlines(self):
        for raw in (b'',b'\xef\xbb\xbf\r\n',b'\xef\xbb\xbf'+json.dumps(self.row).encode()+b'\r'+json.dumps(dict(self.row,message_id='n')).encode()+b'\r\n'):
            self.path.write_bytes(raw);result=list_export(self.path,'normalized')
            self.assertEqual(result['coverage'],validate_normalized(raw)[1]);self.assertEqual(result['original_sha256'],hashlib.sha256(raw).hexdigest())
    def test_metadata_filter_keeps_group_and_paginates_matching_ids(self):
        self.write([self.row,dict(self.row,title='Second'),dict(self.row,conversation_id='d')])
        result=list_export(self.path,'normalized',contains='first',limit=1)
        self.assertEqual(result['conversations'][0]['original_titles'],['First','Second']);self.assertEqual(result['next_offset'],1)
        self.assertEqual(result['filter']['matched_conversations'],2);self.assertEqual(result['filter']['matched_selectable_conversations'],0)
        self.assertEqual(list_export(self.path,'normalized',contains='first',offset=1)['conversations'][0]['conversation'],'d')
    def test_text_role_and_canonical_unicode_counts_not_body(self):
        self.write([dict(self.row,text='Cafe\u0301 private'),dict(self.row,message_id='n',role='assistant',text='Café private')])
        result=list_export(self.path,'normalized',text_contains='CAFÉ',text_role='user',canonical_unicode=True)
        self.assertEqual(result['filter']['matched_messages'],1);self.assertEqual(result['conversations'][0]['matched_role_counts'],{'user':1})
        self.assertNotIn('Cafe\u0301 private',json.dumps(result,ensure_ascii=False));self.assertNotIn('Café private',json.dumps(result,ensure_ascii=False))
    def test_lease_single_read_and_failure_before_parse(self):
        raw=self.write([self.row]);digest=hashlib.sha256(raw).hexdigest();original=Path.read_bytes;seen=[]
        def read(path):seen.append(path);return original(path)
        with patch.object(Path,'read_bytes',read):result=list_export(self.path,'normalized',expected_export_sha256=digest)
        self.assertEqual(seen,[self.path]);self.assertEqual(result['coverage']['expected_export_sha256'],digest)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('no read')):
            with self.assertRaises(ValueError):list_export(self.path,'normalized',expected_export_sha256='BAD')
        with patch('recaplib.export_inventory.validate_normalized',side_effect=AssertionError('no parse')):
            with self.assertRaises(ValueError):list_export(self.path,'normalized',expected_export_sha256='0'*64)
    def test_unselected_bad_record_still_rejects_and_origin_ignored(self):
        raw=self.write([dict(self.row,origin_sha256='bad',origin_locator=False)]);result=list_export(self.path,'normalized')
        self.assertEqual(result['coverage']['records_with_ignored_members'],1)
        self.path.write_bytes(raw+b'{bad}\n')
        with self.assertRaises(ValueError):list_export(self.path,'normalized',contains='not present')
    def test_cli_parity(self):
        self.write([self.row]);args=[str(self.path),'--format','normalized','--text-contains','PRIVATE','--limit','1']
        a=subprocess.run([sys.executable,'recap.py','list-export',*args],cwd=ROOT,capture_output=True)
        b=subprocess.run([sys.executable,'export_inventory.py',*args],cwd=ROOT,capture_output=True)
        self.assertEqual(a.returncode,0,a.stderr);self.assertEqual((a.returncode,a.stdout,a.stderr),(b.returncode,b.stdout,b.stderr))
    def test_import_plan_and_selected_inspection_remain_closed(self):
        self.write([self.row]);db=self.root/'absent.sqlite'
        with patch('sqlite3.connect',side_effect=AssertionError('no database')):
            for call in (lambda:import_export(db,'s',self.path,'normalized'),lambda:make_plan(db,'s','c',self.path,'normalized'),lambda:inspect_normalized(self.path,'c')):
                with self.assertRaises(ValueError):call()
        self.assertFalse(db.exists())
    def test_guide_commands(self):
        import re,shlex
        blocks=re.findall(r'```sh\n(.*?)```',(ROOT/'docs/NORMALIZED_INVENTORY.md').read_text(encoding='utf-8'),re.S)
        self.assertEqual(len(blocks),1);results=[]
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);args[0]=sys.executable
            r=subprocess.run(args,cwd=ROOT,capture_output=True);self.assertEqual(r.returncode,0,r.stderr);results.append(r.stdout)
        self.assertEqual(results[0],results[1])
