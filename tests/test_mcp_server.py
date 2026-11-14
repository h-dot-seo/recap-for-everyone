"""Fictional DELETE-mode archives and explicit EOF-terminated MCP clients."""
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import recap
from recaplib import mcp_server as mcp
from recaplib.archive import ingest_bytes
from recaplib.command_catalog import describe
from tests._cli import run_cli

ROOT=Path(__file__).resolve().parents[1]


def request(method,params=None,identity=1):
    result=dict(jsonrpc='2.0',id=identity,method=method)
    if params is not None:result['params']=params
    return result


def initialize():
    return request('initialize',dict(protocolVersion='2025-06-18',capabilities={},clientInfo=dict(name='synthetic',version='1')),0)


def encode(value):
    return (json.dumps(value,ensure_ascii=True)+'\n').encode()


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.db=self.root/'archive.sqlite'
        ingest_bytes(self.db,'demo',b'{"conversation_id":"c","message_id":"m","role":"user","timestamp":"unknown","text":"synthetic orchard","title":"Synthetic title"}\n')

    def run_bytes(self,raw,args=None):
        result=subprocess.run(args or [sys.executable,str(ROOT/'recap_mcp.py'),'--db',str(self.db)],
            input=raw,capture_output=True,cwd=ROOT,timeout=20,
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='ascii'))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stderr,b'')
        return [json.loads(line) for line in result.stdout.splitlines()]

    def inprocess(self,raw):
        sink=io.BytesIO();mcp.serve(self.db,io.BytesIO(raw),sink)
        return sink.getvalue(),[json.loads(line) for line in sink.getvalue().splitlines()]

    def test_real_process_all_six_cli_parity_and_full_tree_immutable(self):
        cases=[('list',{},['list']),('find',{'query':'orchard'},['find','orchard']),
               ('show',{'source':'demo','conversation':'c'},['show','--source','demo','--conversation','c']),
               ('title-history',{'source':'demo','conversation':'c'},['title-history','--source','demo','--conversation','c']),
               ('stats',{},['stats']),('review-titles',{'source':'demo'},['review-titles','--source','demo'])]
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        raw=encode(initialize())+b''.join(encode(request('tools/call',dict(name=name,arguments=arguments),i+1)) for i,(name,arguments,_) in enumerate(cases))
        replies=self.run_bytes(raw)
        self.assertEqual(replies[0]['result']['protocolVersion'],mcp.PROTOCOL_VERSION)
        for reply,(_,_,argv) in zip(replies[1:],cases):
            cli=run_cli(recap.main,['--db',str(self.db),*argv])
            self.assertEqual(cli.returncode,0,cli.stderr)
            result=reply['result'];self.assertFalse(result['isError'])
            self.assertEqual(result['content'][0]['text'],cli.stdout.rstrip('\n'))
            self.assertEqual(result['content'][1]['text'],mcp.BOUNDARY)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_list_allowlist_and_manual_schema_no_write_or_file_parameters(self):
        replies=self.run_bytes(encode(initialize())+encode(request('tools/list')))
        tools=replies[-1]['result']['tools']
        self.assertEqual({t['name'] for t in tools},{'list','find','show','title-history','stats','review-titles'})
        for tool in tools:
            schema=tool['inputSchema'];self.assertFalse(schema['additionalProperties'])
            self.assertFalse({'db','output','set','expected_revision','proposal','checkpoint','input'}&set(schema['properties']))
            self.assertTrue(tool['annotations']['readOnlyHint'])
        catalog={row['command']:row for row in describe(recap.build_parser())['commands']}
        self.assertTrue(set(mcp.TOOLS)<=set(catalog))
        for name in mcp.TOOLS:
            self.assertEqual(catalog[name]['writes']['default'],[])
            flags={row['flag'].removeprefix('--').replace('-','_') for row in catalog[name]['writes']['conditional']}
            self.assertFalse(flags & set(mcp.SCHEMAS[name]['properties']))

    def test_initialization_ping_notifications_never_execute(self):
        tool=request('tools/call',dict(name='stats'));notification=dict(tool);notification.pop('id')
        raw=encode(tool)+encode(request('ping'))+encode(notification)+encode(initialize())+encode(dict(jsonrpc='2.0',method='notifications/initialized'))+encode(notification)+encode(request('notifications/anything'))+encode(request('ping',identity='done'))
        with patch.dict(mcp.TOOLS,stats=MagicMock(side_effect=AssertionError('must not execute'))):
            _,replies=self.inprocess(raw)
            mcp.TOOLS['stats'].assert_not_called()
        self.assertEqual(len(replies),5)
        self.assertEqual(replies[-2]['error']['code'],-32601)
        self.assertEqual(replies[0]['error']['code'],-32600)
        self.assertEqual(replies[1]['result'],{})
        self.assertEqual(replies[-1]['id'],'done')

    def test_initialization_validation_negotiation_and_repetition(self):
        for params in ({},dict(protocolVersion=True,capabilities={},clientInfo=dict(name='x',version='1')),
                       dict(protocolVersion='2025-06-18',capabilities=[],clientInfo=dict(name='x',version='1')),
                       dict(protocolVersion='2025-06-18',capabilities={},clientInfo=dict(name='x'))):
            replies=self.inprocess(encode(request('initialize',params)))[1]
            self.assertEqual(replies[0]['error']['code'],-32602)
        value=initialize();value['params']['protocolVersion']='different-supported-client-version'
        _,replies=self.inprocess(encode(value)+encode(initialize())+encode(request('tools/list',{'cursor':'unsupported'})))
        self.assertEqual(replies[0]['result']['protocolVersion'],'2025-06-18')
        self.assertEqual(replies[1]['error']['code'],-32600)
        self.assertEqual(replies[2]['error']['code'],-32602)
        # Missing archive is not opened at startup, initialization or ping.
        with patch.object(mcp,'readonly',side_effect=AssertionError('database opened')):
            _,replies=self.inprocess(encode(initialize())+encode(request('ping')))
        self.assertEqual(replies[-1]['result'],{})

    def test_strict_json_request_envelopes_and_ids(self):
        malformed=[b'{',b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":1e999}',b'['*3000,b'\xff',b'"\\ud800"']
        for raw in malformed:
            with self.subTest(raw=raw[:30]):
                _,replies=self.inprocess(raw+b'\n')
                self.assertEqual(replies[0]['error']['code'],-32700)
        invalid=[[],{},dict(jsonrpc='1.0',id=1,method='ping'),request('ping',identity=None),
                 request('ping',identity=True),request('ping',identity=1.2),dict(request('ping'),extra=True),request('ping',[])]
        for value in invalid:
            with self.subTest(value=value):
                self.assertEqual(self.inprocess(encode(value))[1][0]['error']['code'],-32600)
        for identity in (0,-1,'id'):
            self.assertEqual(self.inprocess(encode(request('ping',identity=identity)))[1][0]['id'],identity)

    def test_invalid_params_and_write_tools_rejected_without_dispatch(self):
        cases=[dict(name='import',arguments={}),dict(name='stats',arguments={'db':'PRIVATE_PATH'}),
               dict(name='show',arguments={'source':'demo','conversation':'c','output':'PRIVATE_PATH'}),
               dict(name='list',arguments={'limit':True}),dict(name='list',arguments={'offset':-1}),
               dict(name='review-titles',arguments={'source':'demo','limit':101}),
               dict(name='find',arguments={'query':False}),dict(name='show',arguments={}),
               dict(name='review-titles',arguments={'source':'demo','checkpoint':'PRIVATE_PATH'}),
               dict(name='stats',arguments=None)]
        raw=encode(initialize())+b''.join(encode(request('tools/call',case,i+1)) for i,case in enumerate(cases))
        with patch.dict(mcp.TOOLS,{name:MagicMock(side_effect=AssertionError('dispatch forbidden')) for name in mcp.TOOLS}):
            _,replies=self.inprocess(raw)
        for reply in replies[1:]:
            self.assertEqual(reply['error']['code'],-32602)
            self.assertNotIn('PRIVATE',json.dumps(reply))
        self.assertEqual(self.inprocess(encode(request('unknown')))[1][0]['error']['code'],-32601)

    def test_request_limit_terminates_and_result_limit_is_bounded(self):
        replies=self.run_bytes(b'x'*(mcp.MAX_REQUEST_BYTES+1)+b'\n'+encode(request('ping')))
        self.assertEqual(len(replies),1);self.assertEqual(replies[0]['error']['code'],-32700)
        with patch.object(mcp,'MAX_RESPONSE_BYTES',1024),patch.dict(mcp.TOOLS,stats=lambda db:{'private':'X'*3000}):
            raw,replies=self.inprocess(encode(initialize())+encode(request('tools/call',dict(name='stats'))))
        self.assertTrue(all(len(line)+1<=1024 for line in raw.splitlines()))
        self.assertTrue(replies[-1]['result']['isError'])
        self.assertIn('smaller limit',replies[-1]['result']['content'][0]['text'])
        # Bound serialized ASCII IDs before any dispatch and terminate the session.
        for identity in ('i'*255, '☃'*43, 10**256):
            with patch.dict(mcp.TOOLS,stats=MagicMock()):
                raw,replies=self.inprocess(encode(initialize())+encode(request('tools/call',dict(name='stats'),identity))+encode(request('ping')))
                mcp.TOOLS['stats'].assert_not_called()
            self.assertEqual(len(replies),2)
            self.assertEqual(replies[-1]['error']['code'],-32600)
            self.assertIsNone(replies[-1]['id'])
        for identity in ('i'*254, 10**255):
            with patch.object(mcp,'MAX_RESPONSE_BYTES',1024),patch.dict(mcp.TOOLS,stats=lambda db:{'large':'X'*3000}):
                raw,replies=self.inprocess(encode(initialize())+encode(request('tools/call',dict(name='stats'),identity)))
            self.assertEqual(replies[-1]['id'],identity)
            self.assertTrue(replies[-1]['result']['isError'])
            self.assertTrue(all(len(line)+1<=1024 for line in raw.splitlines()))

    def test_standard_request_metadata_and_help_boundary(self):
        calls=[initialize(),request('ping'),request('tools/list'),request('tools/call',dict(name='stats'))]
        for call in calls:call.setdefault('params',{})['_meta']={'progressToken':'ignored'}
        replies=self.inprocess(b''.join(map(encode,calls)))[1]
        self.assertTrue(all('result' in reply for reply in replies))
        for call in calls:
            call['params']['_meta']=[]
            replies=self.inprocess(encode(initialize())+encode(call))[1]
            # initialize is tested in a fresh session, not as repeated init.
            if call['method']=='initialize':replies=self.inprocess(encode(call))[1]
            self.assertEqual(replies[-1]['error']['code'],-32602)
        replies=self.inprocess(encode(initialize())+encode(request('tools/call',dict(name='stats',arguments={'_meta':{}}))))[1]
        self.assertEqual(replies[-1]['error']['code'],-32602)
        help_text=' '.join(mcp.build_parser().format_help().split())
        for phrase in ('UNTRUSTED','approval','client and its model provider','authorization is required'):
            self.assertIn(phrase,help_text)

    def test_known_failure_diagnostics_internal_errors_and_no_sockets(self):
        raw=encode(initialize())+encode(request('tools/call',dict(name='stats')))
        for error in (OSError('PRIVATE_OS'),sqlite3.Error('PRIVATE_SQL')):
            with patch.dict(mcp.TOOLS,stats=MagicMock(side_effect=error)),patch('socket.socket',side_effect=AssertionError('no sockets')):
                _,replies=self.inprocess(raw)
            self.assertTrue(replies[-1]['result']['isError']);self.assertNotIn('PRIVATE_',json.dumps(replies))
        with patch.dict(mcp.TOOLS,stats=MagicMock(side_effect=RuntimeError('PRIVATE_INTERNAL'))):
            output,replies=self.inprocess(raw)
        self.assertEqual(replies[-1]['error']['code'],-32603)
        self.assertNotIn(b'PRIVATE_INTERNAL',output);self.assertNotIn(b'Traceback',output)

    def test_owned_stats_connection_closed_on_query_failure(self):
        connection=MagicMock();connection.execute.side_effect=sqlite3.Error('synthetic')
        with patch.object(mcp,'readonly',return_value=connection),self.assertRaises(sqlite3.Error):mcp.stats(self.db)
        connection.close.assert_called_once()
        connection.execute.assert_called_once_with('BEGIN')
        success=MagicMock()
        success.execute.return_value.fetchone.side_effect=[(3,),(2,)]
        with patch.object(mcp,'readonly',return_value=success):
            self.assertEqual(mcp.stats(self.db),dict(messages=3,artifacts=2))
        self.assertEqual(success.execute.call_args_list[0].args,('BEGIN',))
        success.close.assert_called_once()

    def test_documented_configuration_is_launchable(self):
        text=(ROOT/'docs/MCP_SERVER.md').read_text(encoding='utf-8')
        config=json.loads(re.search(r'```json\n(.*?)```',text,re.S).group(1))
        self.assertEqual(config,dict(command='python',args=['recap_mcp.py','--db','ARCHIVE.sqlite']))
        args=[sys.executable]+[str(self.db) if part=='ARCHIVE.sqlite' else part for part in config['args']]
        replies=self.run_bytes(encode(initialize())+encode(request('ping')),args)
        self.assertEqual(replies[-1]['result'],{})


if __name__=='__main__':unittest.main()
