"""Opt-in file tools use synthetic inputs; no network or external clients."""
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
import zipfile

import recap
from recaplib import mcp_server as mcp
from recaplib.command_catalog import describe
from tests._cli import run_cli
from tests.test_mcp_server import encode, initialize, request, ROOT


class McpFileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.inputs=self.root/'inputs';self.inputs.mkdir()
        self.db=self.root/'PRIVATE_ARCHIVE.sqlite';self.db.write_bytes(b'not a database')
        self.web=self.inputs/'web.json';shutil.copyfile(ROOT/'examples/web-export.json',self.web)
        self.local=self.inputs/'local.jsonl';shutil.copyfile(ROOT/'examples/rollback-session.jsonl',self.local)
        self.zip=self.inputs/'web.zip'
        with zipfile.ZipFile(self.zip,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('conversations.json',self.web.read_bytes())

    def run_calls(self,calls,roots=None,budget=mcp.MAX_INPUT_BYTES):
        sink=io.BytesIO()
        mcp.serve(self.db,io.BytesIO(encode(initialize())+b''.join(map(encode,calls))),sink,
                  [self.inputs] if roots is None else roots,budget)
        return [json.loads(line) for line in sink.getvalue().splitlines()][1:]

    def call(self,name,arguments):
        return request('tools/call',dict(name=name,arguments=arguments))

    def snapshot(self):
        result={}
        # Walk without following symlinks; record empty directories and node types.
        def visit(directory):
            for path in directory.iterdir():
                key=path.relative_to(self.root).as_posix()
                if path.is_symlink():result[key]=('symlink',os.readlink(path))
                elif path.is_dir():
                    result[key]=('directory',);visit(path)
                elif path.is_file():result[key]=('file',path.read_bytes())
                else:result[key]=('special',path.lstat().st_mode)
        visit(self.root)
        return result

    def test_inventory_detects_empty_directories_types_and_links(self):
        before=self.snapshot()
        added=self.inputs/'empty';added.mkdir()
        self.assertNotEqual(before,self.snapshot())
        self.assertEqual(self.snapshot()['inputs/empty'],('directory',))
        added.rmdir();added.write_bytes(b'')
        self.assertEqual(self.snapshot()['inputs/empty'],('file',b''))
        added.unlink()
        try:added.symlink_to(self.inputs,target_is_directory=True)
        except (OSError,NotImplementedError):return
        # A cycle is recorded as a link, not followed recursively.
        self.assertEqual(self.snapshot()['inputs/empty'],('symlink',os.readlink(added)))

    def test_opt_in_only_and_schema_allowlist(self):
        for roots,expected in (([],set(mcp.TOOLS)),([self.inputs],set(mcp.TOOLS)|set(mcp.FILE_TOOLS))):
            result=self.run_calls([request('tools/list')],roots)[0]
            entries=result['result']['tools'];self.assertEqual({e['name'] for e in entries},expected)
            self.assertNotIn(str(self.inputs),json.dumps(entries))
            for entry in entries:
                self.assertFalse(entry['inputSchema']['additionalProperties'])
                self.assertFalse(({'output','db','checkpoint','set'}|({'source','proposal'} if entry['name'] in mcp.FILE_TOOLS else set()))&set(entry['inputSchema']['properties']))
        catalog={entry['command']:entry for entry in describe(recap.build_parser())['commands']}
        self.assertTrue(set(mcp.FILE_TOOLS)<=set(catalog))
        for name in mcp.FILE_TOOLS:
            self.assertEqual(catalog[name]['writes']['default'],[])
            write_flags={item['flag'].removeprefix('--').replace('-','_') for item in catalog[name]['writes']['conditional']}
            self.assertFalse(write_flags & set(mcp.FILE_SCHEMAS[name]['properties']))
        reply=self.run_calls([self.call('inspect',dict(input=str(self.web),kind='web'))],[])[0]
        self.assertEqual(reply['error']['code'],-32602)

    def test_five_cli_parity_and_immutable_inputs_without_database_or_network(self):
        cases=[('inspect',dict(input=str(self.web),kind='web'),['inspect',str(self.web),'--format','web']),
               ('list-export',dict(input=str(self.web),kind='web',text_contains='launch'),['list-export',str(self.web),'--format','web','--text-contains','launch']),
               ('inspect-web-zip',dict(input=str(self.zip)),['inspect-web-zip',str(self.zip)]),
               ('web-branch',dict(input=str(self.web),conversation='synthetic-chat',node='m2'),['web-branch',str(self.web),'--conversation','synthetic-chat','--node','m2']),
               ('replay-local',dict(input=str(self.local)),['replay-local',str(self.local)])]
        before=self.snapshot()
        with patch.object(mcp,'readonly',side_effect=AssertionError('DB forbidden')),patch('socket.socket',side_effect=AssertionError('socket forbidden')):
            replies=self.run_calls([self.call(name,args) for name,args,_ in cases])
        # Execute the same five calls through the actual binary stdio entrypoint.
        raw=encode(initialize())+b''.join(encode(self.call(name,args)) for name,args,_ in cases)
        process=subprocess.run([sys.executable,str(ROOT/'recap_mcp.py'),'--db',str(self.db),
            '--allow-input-dir',str(self.inputs)],input=raw,capture_output=True,cwd=ROOT,timeout=20,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='ascii'))
        self.assertEqual(process.returncode,0,process.stderr);self.assertEqual(process.stderr,b'')
        actual=[json.loads(line) for line in process.stdout.splitlines()][1:]
        self.assertEqual(actual,replies)
        self.assertEqual(len(actual),5)
        for reply,(_,_,argv) in zip(actual,cases):
            cli=run_cli(recap.main,argv)
            self.assertEqual(cli.returncode,0,cli.stderr)
            self.assertEqual(reply['result']['content'][0]['text'],cli.stdout.rstrip('\n'))
            self.assertFalse(reply['result']['isError'])
            self.assertEqual(reply['result']['content'][1]['text'],mcp.FILE_BOUNDARY)
        self.assertEqual(before,self.snapshot())

    def test_invalid_paths_never_dispatch_or_echo(self):
        sibling=self.root/'inputs-sibling';sibling.mkdir();outside=sibling/'PRIVATE_FILE';outside.write_bytes(b'{}')
        paths=[outside,self.inputs/'..'/'inputs-sibling'/'PRIVATE_FILE',self.inputs,self.inputs/'PRIVATE_MISSING']
        for path in paths:
            with patch.dict(mcp.FILE_TOOLS,inspect=MagicMock()):
                reply=self.run_calls([self.call('inspect',dict(input=str(path),kind='web'))])[0]
                mcp.FILE_TOOLS['inspect'].assert_not_called()
            self.assertTrue(reply['result']['isError']);self.assertNotIn('PRIVATE_',json.dumps(reply))
        # Canonical parent aliases inside the allowed root are valid, not lexical bans.
        child=self.inputs/'child';child.mkdir()
        alias=child/'..'/self.web.name
        self.assertTrue(os.path.samefile(alias,self.web))
        reply=self.run_calls([self.call('inspect',dict(input=str(alias),kind='web'))])[0]
        self.assertFalse(reply['result']['isError'])

    def test_symlink_targets_and_directory_escape(self):
        outside=self.root/'PRIVATE_OUTSIDE';outside.write_bytes(self.web.read_bytes())
        inside_link=self.inputs/'inside-link';outside_link=self.inputs/'outside-link';directory_link=self.inputs/'directory-link'
        try:
            inside_link.symlink_to(self.web);outside_link.symlink_to(outside);directory_link.symlink_to(self.root,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('symlink creation unavailable')
        for path,failed in ((inside_link,False),(outside_link,True),(directory_link/outside.name,True)):
            reply=self.run_calls([self.call('inspect',dict(input=str(path),kind='web'))])[0]
            self.assertEqual(reply['result']['isError'],failed)

    @unittest.skipUnless(hasattr(os,'mkfifo'),'FIFO unavailable')
    def test_fifo_rejected_without_reader(self):
        fifo=self.inputs/'pipe';os.mkfifo(fifo)
        with patch.dict(mcp.FILE_TOOLS,inspect=MagicMock()):
            reply=self.run_calls([self.call('inspect',dict(input=str(fifo),kind='web'))])[0]
            mcp.FILE_TOOLS['inspect'].assert_not_called()
        self.assertTrue(reply['result']['isError'])

    def test_budget_exact_boundary_and_protocol_errors(self):
        path=self.inputs/'one';path.write_bytes(b'x'*1024*1024)
        for budget,called in ((len(path.read_bytes()),True),(len(path.read_bytes())-1,False),(1,False)):
            reader=MagicMock(return_value={})
            with patch.dict(mcp.FILE_TOOLS,inspect=reader):
                reply=self.run_calls([self.call('inspect',dict(input=str(path),kind='web'))],budget=budget)[0]
            self.assertEqual(reader.called,called);self.assertEqual(reply['result']['isError'],not called)
        for args in (dict(input=str(self.web),kind='web',output='PRIVATE'),dict(input=1,kind='web'),dict(input=str(self.web),kind='bad')):
            self.assertEqual(self.run_calls([self.call('inspect',args)])[0]['error']['code'],-32602)
        self.assertEqual(self.run_calls([self.call('inspect-web-zip',dict(input=str(self.zip),max_member_bytes=mcp.MAX_MEMBER_BYTES+1))])[0]['error']['code'],-32602)

    def test_malformed_files_replay_failure_and_zip_metadata_only(self):
        for raw in (b'{"PRIVATE":1,"PRIVATE":2}',b'[{"x":NaN}]',b'\xff',b'['*3000):
            bad=self.inputs/'PRIVATE_bad';bad.write_bytes(raw)
            reply=self.run_calls([self.call('inspect',dict(input=str(bad),kind='web'))])[0]
            self.assertTrue(reply['result']['isError']);self.assertNotIn('PRIVATE',reply['result']['content'][0]['text'])
        bad.write_bytes(b'{}\n')
        reply=self.run_calls([self.call('replay-local',dict(input=str(bad)))])[0]
        self.assertTrue(reply['result']['isError']);self.assertFalse(json.loads(reply['result']['content'][0]['text'])['supported'])
        with zipfile.ZipFile(self.zip,'w',compression=zipfile.ZIP_DEFLATED) as archive:archive.writestr('conversations.json',b' '*100000)
        before=self.snapshot()
        with patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('no decompression')):
            reply=self.run_calls([self.call('inspect-web-zip',dict(input=str(self.zip),max_member_bytes=10))])[0]
        value=json.loads(reply['result']['content'][0]['text'])
        self.assertFalse(value['members_decompressed']);self.assertFalse(value['candidates'][0]['metadata_eligible'])
        self.assertEqual(before,self.snapshot())

    def test_disappearance_after_preflight_is_safe(self):
        def reader(path,**kwargs):
            path.unlink();return mcp.inspect_export(path,**kwargs)
        with patch.dict(mcp.FILE_TOOLS,inspect=reader):
            reply=self.run_calls([self.call('inspect',dict(input=str(self.web),kind='web'))])[0]
        self.assertTrue(reply['result']['isError']);self.assertNotIn(str(self.web),json.dumps(reply))

    def test_startup_invalid_configuration_and_real_opt_in(self):
        for flags in (['--allow-input-dir',str(self.root/'PRIVATE_MISSING')],['--allow-input-dir',str(self.web)],
                      ['--max-input-bytes','PRIVATE_VALUE'],['--max-input-bytes','0'],['--max-input-bytes',str(mcp.MAX_INPUT_BYTES+1)]):
            result=subprocess.run([sys.executable,str(ROOT/'recap_mcp.py'),'--db',str(self.db),*flags],input=b'',capture_output=True,timeout=10)
            self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,b'');self.assertNotIn(b'PRIVATE_',result.stderr)
        result=subprocess.run([sys.executable,str(ROOT/'recap_mcp.py'),'--db',str(self.db),'--allow-input-dir',str(self.inputs),
            '--allow-input-dir',str(self.inputs.resolve()),'--max-input-bytes','1048576'],input=encode(initialize())+encode(request('tools/list')),capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(json.loads(result.stdout.splitlines()[-1])['result']['tools']),11)

    def test_documented_opt_in_configuration(self):
        text=(ROOT/'docs/MCP_SERVER.md').read_text(encoding='utf-8')
        blocks=re.findall(r'```json\n(.*?)```',text,re.S)
        self.assertGreaterEqual(len(blocks),2)
        config=json.loads(blocks[1]);self.assertEqual(config['command'],'python')
        args=[sys.executable]+[str(self.db) if v=='ARCHIVE.sqlite' else str(self.inputs) if v=='INPUTS' else v for v in config['args']]
        result=subprocess.run(args,input=encode(initialize())+encode(request('tools/list')),capture_output=True,cwd=ROOT,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(len(json.loads(result.stdout.splitlines()[-1])['result']['tools']),11)


if __name__=='__main__':unittest.main()
