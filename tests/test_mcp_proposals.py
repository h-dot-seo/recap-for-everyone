"""Explicit synthetic supplied proposals; no approval or external provider."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import recap
from recaplib import mcp_server as mcp, title_batch
from recaplib.archive import ingest_bytes
from recaplib.branch_title import suggest_branch
from recaplib.session_workflow import import_export
from recaplib.title_suggestion import suggest
from recaplib.title_proposal import snapshot
from tests._cli import run_cli
from tests.test_mcp_server import ROOT, encode, initialize, request
from tests import test_mcp_files as file_tests


class McpProposalTests(unittest.TestCase):
    inventory=file_tests.McpFileTests.snapshot

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.inputs=self.root/'inputs';self.inputs.mkdir()
        self.db=self.root/'archive.sqlite'
        rows=[dict(conversation_id=c,message_id=c+'-u',role='user',timestamp='synthetic',text='Raw '+c+' orchard',title='Shared title' if c=='c' else 'Old '+c) for c in 'abc']
        raw=''.join(json.dumps(row)+'\n' for row in rows).encode()
        (self.inputs/'source.jsonl').write_bytes(raw);ingest_bytes(self.db,'mixed',raw)
        self.proposal=self.save(self.candidate())

    def candidate(self,cid='a',**changes):
        value=dict(source='mixed',conversation=cid,content_sha256=snapshot(self.db,'mixed',cid)[1],title='Supplied '+cid,
                   evidence_message_ids=[cid+'-u'],provider='operator')
        value.update(changes);return value

    def save(self,value,name='proposal.json'):
        path=self.inputs/name;path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8');return path

    def run_calls(self,calls,roots=True,budget=mcp.MAX_INPUT_BYTES,real=False):
        raw=encode(initialize())+b''.join(map(encode,calls))
        if real:
            args=[sys.executable,str(ROOT/'recap_mcp.py'),'--db',str(self.db)]
            if roots:args+=['--allow-input-dir',str(self.inputs)]
            args+=['--max-input-bytes',str(budget)]
            process=subprocess.run(args,input=raw,capture_output=True,cwd=ROOT,timeout=20,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='ascii'))
            self.assertEqual(process.returncode,0,process.stderr);self.assertEqual(process.stderr,b'')
            output=process.stdout
        else:
            sink=io.BytesIO();mcp.serve(self.db,io.BytesIO(raw),sink,[self.inputs] if roots else [],budget);output=sink.getvalue()
        return [json.loads(line) for line in output.splitlines()][1:]

    def call(self,paths=None,**kwargs):
        args=dict(source='mixed');args.update(kwargs)
        if paths is not None:args['proposal']=[str(p) for p in paths]
        return request('tools/call',dict(name='review-titles',arguments=args))

    def result(self,paths=None,**kwargs):
        reply=self.run_calls([self.call(paths,**kwargs)])[0]
        self.assertNotIn('error',reply)
        return reply['result']

    def test_default_interface_unchanged_and_opt_in_schema(self):
        # Frozen merged-round37 initialize + tools/list wire bytes (no filesystem paths).
        sink=io.BytesIO()
        mcp.serve(self.db,io.BytesIO(encode(initialize())+encode(request('tools/list'))),sink)
        self.assertEqual(hashlib.sha256(sink.getvalue()).hexdigest(),
                         '4acff2698d7d4d081c298af9541a67522f62348c7b0e124d02ee9e91b0c3a107')
        plain=self.run_calls([request('tools/list')],roots=False)[0]['result']['tools']
        self.assertEqual(len(plain),6)
        for tool in plain:self.assertEqual(tool['inputSchema'],mcp.SCHEMAS[tool['name']])
        opted=self.run_calls([request('tools/list')])[0]['result']['tools']
        changed=[t for t in opted if t['name']=='review-titles'][0]['inputSchema']
        self.assertEqual(set(changed['properties'])-set(mcp.SCHEMAS['review-titles']['properties']),{'proposal','supplied_only'})
        self.assertEqual(mcp.SCHEMAS['review-titles'],mcp._contract('review-titles',False))
        for tool in opted:
            if tool['name'] in mcp.FILE_SCHEMAS:self.assertEqual(tool['inputSchema'],mcp.FILE_SCHEMAS[tool['name']])
        calls=[request('tools/list'),self.call()]
        plain_review=self.run_calls([self.call()],roots=False)[0]
        self.assertEqual(plain_review,self.run_calls([self.call()])[0])
        self.assertEqual(plain_review['result']['content'][1]['text'],mcp.BOUNDARY)
        for extra in ({'proposal':[str(self.proposal)]},{'supplied_only':False}):
            reply=self.run_calls([request('tools/call',dict(name='review-titles',arguments=dict(source='mixed',**extra)))],roots=False)[0]
            self.assertEqual(reply['error']['code'],-32602)

    def test_real_process_branch_local_operator_cli_parity_and_tree_unchanged(self):
        web=self.inputs/'branches.json'
        web.write_text(json.dumps([dict(id='branched',title='Old',current_node='chosen',mapping={
            'chosen':dict(parent=None,message=dict(author=dict(role='user'),content=dict(parts=['Fictional orchard branch'])))})]),encoding='utf-8')
        import_export(self.db,'mixed',web,'web')
        paths=[self.proposal,self.save(suggest(self.db,'mixed','b'),'local.json'),self.save(suggest_branch(self.db,'mixed','branched',web),'branch.json')]
        before=self.inventory()
        calls=[self.call(paths),self.call(paths,supplied_only=True,limit=1,offset=1)]
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            direct=self.run_calls(calls)
        replies=self.run_calls(calls,real=True);self.assertEqual(replies,direct)
        for reply,extra in zip(replies,([],['--supplied-only','--limit','1','--offset','1'])):
            argv=['--db',str(self.db),'review-titles','--source','mixed']
            for path in paths:argv+=['--proposal',str(path)]
            cli=run_cli(recap.main,argv+extra)
            self.assertEqual(cli.returncode,0,cli.stderr)
            self.assertEqual(reply['result']['content'][0]['text'],cli.stdout.rstrip('\n'))
            self.assertEqual(reply['result']['content'][1]['text'],mcp.FILE_BOUNDARY)
            self.assertFalse(reply['result']['isError'])
        self.assertEqual(before,self.inventory())

    def test_stale_collision_offpage_and_invalid_context_semantics(self):
        paths=[self.save(self.candidate(title='Shared title'),'a.json'),self.save(self.candidate('b',title='Shared title'),'b.json')]
        value=json.loads(self.result(paths)['content'][0]['text'])
        for item in value['items'][:2]:
            self.assertEqual(item['collisions']['page_proposal_count'],1)
            self.assertEqual(item['collisions']['existing_title_conversations'],['c'])
        stale=self.save(self.candidate(content_sha256='0'*64),'stale.json')
        invalid=self.save(self.candidate('b',evidence_message_ids=['a-u']),'invalid.json')
        value=json.loads(self.result([stale,invalid],limit=1)['content'][0]['text'])
        self.assertEqual(value['items'][0]['reason_code'],'SUPPLIED_PROPOSAL_STALE')
        self.assertEqual(value['supplied_proposals']['not_on_page'],1)
        value=json.loads(self.result([stale,invalid],limit=1,offset=1)['content'][0]['text'])
        self.assertEqual(value['items'][0]['reason_code'],'SUPPLIED_PROPOSAL_INVALID')
        value=json.loads(self.result([invalid],supplied_only=True)['content'][0]['text'])
        self.assertEqual([item['conversation'] for item in value['items']],['b'])

    def test_identity_validation_before_database(self):
        wrong=self.save(self.candidate(source='PRIVATE_WRONG'),'wrong.json')
        for paths in ([wrong],[self.proposal,self.proposal]):
            with patch.object(title_batch,'readonly',side_effect=AssertionError('DB forbidden')):
                result=self.result(paths)
            self.assertTrue(result['isError']);self.assertNotIn('PRIVATE_WRONG',json.dumps(result))
        with patch.object(title_batch,'readonly',side_effect=AssertionError('DB forbidden')):
            self.assertTrue(self.result([self.proposal],source='')['isError'])

    def test_array_schema_errors_do_not_read_or_open_database(self):
        invalid=[[],[None],[False],[1],[''],[str(self.proposal)]*1001,'path',{},None]
        for value in invalid:
            call=self.call();call['params']['arguments']['proposal']=value
            with patch.object(mcp,'load_supplied_proposals',side_effect=AssertionError('read forbidden')),patch.object(title_batch,'readonly',side_effect=AssertionError('DB forbidden')):
                reply=self.run_calls([call])[0]
            self.assertEqual(reply['error']['code'],-32602)
        for extras in ({'supplied_only':True},{'supplied_only':1},{'output':'PRIVATE_PATH'},{'checkpoint':'PRIVATE_PATH'}):
            call=self.call();call['params']['arguments'].update(extras)
            self.assertEqual(self.run_calls([call])[0]['error']['code'],-32602)

    def test_all_paths_admitted_before_loader_with_escape_link_fifo(self):
        outside=self.root/'PRIVATE_OUTSIDE.json';outside.write_bytes(self.proposal.read_bytes())
        paths=[self.inputs/'..'/outside.name,self.inputs/'PRIVATE_MISSING',self.inputs]
        link=self.inputs/'link'
        try:link.symlink_to(outside);paths.append(link)
        except (OSError,NotImplementedError):pass
        if hasattr(os,'mkfifo'):
            fifo=self.inputs/'pipe';os.mkfifo(fifo);paths.append(fifo)
        for invalid in paths:
            with patch.object(mcp,'load_supplied_proposals',side_effect=AssertionError('read forbidden')),patch.object(title_batch,'readonly',side_effect=AssertionError('DB forbidden')):
                result=self.result([self.proposal,invalid])
            self.assertTrue(result['isError']);self.assertNotIn(str(self.root),json.dumps(result))
            self.assertNotIn('PRIVATE_',result['content'][0]['text'])

    def test_individual_combined_and_lowered_budget_before_loader(self):
        second=self.save(self.candidate('b'),'second.json')
        size=self.proposal.stat().st_size+second.stat().st_size
        exact=self.run_calls([self.call([self.proposal,second])],budget=size)[0]
        self.assertFalse(exact['result']['isError'])
        oversized=self.inputs/'huge.json';oversized.write_bytes(b' '*mcp.MAX_SUPPLIED_BYTES+b'{}')
        half=self.inputs/'half.json';half.write_bytes(b' '* (mcp.MAX_SUPPLIED_BYTES//2))
        for paths,budget in (([self.proposal,second],size-1),([self.proposal],1),([oversized],mcp.MAX_INPUT_BYTES),([half,half,self.proposal],mcp.MAX_INPUT_BYTES)):
            with patch.object(mcp,'load_supplied_proposals',side_effect=AssertionError('read forbidden')),patch.object(title_batch,'readonly',side_effect=AssertionError('DB forbidden')):
                reply=self.run_calls([self.call(paths)],budget=budget)[0]
            self.assertTrue(reply['result']['isError'])

    def test_loader_strict_json_bom_and_safe_failures(self):
        path=self.inputs/'PRIVATE_bad.json'
        malformed=[b'{"source":"mixed","source":"other"}',b'{"x":NaN}',b'{"x":1e999}',b'['*3000,b'\xff']
        for raw in malformed:
            path.write_bytes(raw)
            with patch.object(title_batch,'readonly',side_effect=AssertionError('DB forbidden')):result=self.result([path])
            self.assertTrue(result['isError']);self.assertNotIn('PRIVATE_',result['content'][0]['text'])
        path.write_bytes(b'\xef\xbb\xbf'+self.proposal.read_bytes())
        self.assertFalse(self.result([path])['isError'])
        with patch.object(mcp,'load_supplied_proposals',side_effect=OSError('PRIVATE_OS_PATH')):
            result=self.result([path])
        self.assertTrue(result['isError']);self.assertNotIn('PRIVATE_OS_PATH',json.dumps(result))

    def test_loader_retains_actual_one_mib_bound_after_preflight(self):
        loader=mcp.load_supplied_proposals
        def grown(paths):
            paths[0].write_bytes(b' '*(mcp.MAX_SUPPLIED_BYTES+1))
            return loader(paths)
        with patch.object(mcp,'load_supplied_proposals',side_effect=grown),patch.object(title_batch,'readonly',side_effect=AssertionError('DB forbidden')):
            self.assertTrue(self.result([self.proposal])['isError'])

    def test_documented_request(self):
        blocks=re.findall(r'```json\n(.*?)```',(ROOT/'docs/MCP_SERVER.md').read_text(encoding='utf-8'),re.S)
        self.assertGreaterEqual(len(blocks),3)
        call=json.loads(blocks[2]);self.assertEqual(call['method'],'tools/call')
        self.assertEqual(call['params']['name'],'review-titles')
        args=call['params']['arguments'];self.assertEqual(args['proposal'],['PROPOSAL.json']);self.assertIs(args['supplied_only'],True)
        args['source']='mixed';args['proposal']=[str(self.proposal)]
        reply=self.run_calls([call],real=True)[0];self.assertFalse(reply['result']['isError'])


if __name__=='__main__':unittest.main()
