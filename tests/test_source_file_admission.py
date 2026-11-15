"""Synthetic regular-file preflight; not a TOCTOU sandbox or byte ceiling."""
import os
from pathlib import Path
import socket
import re
import shlex
import stat
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest
from recaplib.session_workflow import inspect_export
from recaplib.replay_local import reconstruct
from recaplib.web_branch import branch_view
from recaplib.title_plan import make_plan
from recaplib.attributed_title import attributed_evidence
from recaplib.replay_title import replay_evidence
from recaplib.local_parser import parse_artifact

ROOT=Path(__file__).resolve().parents[1]


class SourceFileAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'never.sqlite'

    def calls(self,path):
        return [lambda:ingest(self.db,'synthetic',path),
                lambda:ingest(self.db,'synthetic',path,provenance=[]),
                lambda:inspect_export(path,'web'),
                lambda:branch_view(path,'synthetic'),
                lambda:make_plan(self.db,'synthetic','synthetic',path,'web'),
                lambda:attributed_evidence(self.db,'synthetic','synthetic',path),
                lambda:replay_evidence(self.db,'synthetic','synthetic',path),
                lambda:parse_artifact(path,'synthetic.jsonl')]

    def assert_refused_without_open(self,path):
        with patch.object(Path,'open',side_effect=AssertionError('must reject before open')),patch('sqlite3.connect',side_effect=AssertionError('must reject before DB')):
            for call in self.calls(path):
                with self.subTest(call=call),self.assertRaises(ValueError) as caught:call()
                self.assertNotIn(str(path),str(caught.exception))
            self.assertEqual(reconstruct(path),dict(supported=False,reason_code='SOURCE_ERROR',line=0))
        self.assertFalse(self.db.exists())

    def test_directory_refused_before_source_and_database_open(self):
        self.assert_refused_without_open(self.root)

    def test_device_refused_before_open(self):
        self.assert_refused_without_open(Path('NUL' if os.name=='nt' else '/dev/null'))

    @unittest.skipUnless(hasattr(socket,'AF_UNIX') and os.name!='nt','POSIX filesystem socket only')
    def test_socket_refused_without_connection(self):
        path=self.root/'synthetic.socket'
        try:
            server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        except PermissionError:
            self.skipTest('filesystem sockets prohibited by this execution environment')
        with server:
            server.bind(str(path));self.assert_refused_without_open(path)

    def test_missing_path_preserves_exception_and_projection_reason(self):
        path=self.root/'missing'
        for call in self.calls(path):
            with self.assertRaises(FileNotFoundError):call()
        self.assertEqual(reconstruct(path),dict(supported=False,reason_code='SOURCE_ERROR',line=0))

    def test_input_option_errors_still_precede_source_admission(self):
        with patch.object(Path,'stat',side_effect=AssertionError('no stat')):
            with self.assertRaisesRegex(ValueError,'source must'):ingest(self.db,'',self.root)
            with self.assertRaisesRegex(ValueError,'expected export hash'):inspect_export(self.root,'web',expected_export_sha256='BAD')
            with self.assertRaisesRegex(ValueError,'conversation ID'):branch_view(self.root,'')
        self.assertFalse(self.db.exists())

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX FIFO only')
    def test_fifo_all_source_paths_reject_in_timeout_bounded_process(self):
        path=self.root/'synthetic.fifo';os.mkfifo(path)
        script='''from pathlib import Path
import sys
from tests.test_source_file_admission import SourceFileAdmissionTests
case=SourceFileAdmissionTests();case.setUp()
try:case.assert_refused_without_open(Path(sys.argv[1]))
finally:case.doCleanups()
'''
        result=subprocess.run([sys.executable,'-c',script,str(path)],cwd=ROOT,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX FIFO only')
    def test_actual_cli_fifo_fails_promptly_without_database(self):
        path=self.root/'synthetic.fifo';os.mkfifo(path)
        for args in [ ['--db',str(self.db),'ingest',str(path),'--source','synthetic'],['inspect',str(path),'--format','web'] ]:
            result=subprocess.run([sys.executable,'recap.py',*args],cwd=ROOT,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertNotIn(str(path).encode(),result.stderr);self.assertFalse(self.db.exists())

    def test_socket_metadata_rejected_even_when_runtime_cannot_create_socket(self):
        path=self.root/'synthetic.socket';original=Path.stat
        def observed(value,*args,**kwargs):
            return SimpleNamespace(st_mode=stat.S_IFSOCK) if value==path else original(value,*args,**kwargs)
        with patch.object(Path,'stat',observed):
            self.assert_refused_without_open(path)

    def test_regular_symlink_retains_original_read_path_and_single_read_seams(self):
        target=self.root/'synthetic.jsonl';target.write_bytes(b'[]')
        link=self.root/'synthetic-link.jsonl'
        try:link.symlink_to(target)
        except (OSError,NotImplementedError):self.skipTest('regular symlink unavailable')
        opener=Path.open
        for call in self.calls(link):
            opened=[]
            def tracked(path,*args,**kwargs):opened.append(path);return opener(path,*args,**kwargs)
            with patch.object(Path,'open',tracked):
                try:call()
                except ValueError as error:self.assertNotIn('regular file',str(error))
            self.assertEqual(opened,[link])
        self.assertNotEqual(reconstruct(link)['reason_code'],'SOURCE_ERROR')
        self.assertEqual(target.read_bytes(),b'[]');self.assertTrue(link.is_symlink());self.assertFalse(self.db.exists())

    def test_byte_apis_do_not_gain_filesystem_admission(self):
        from recaplib.archive import ingest_bytes
        from recaplib.session_workflow import _normalize_bytes
        with patch.object(Path,'stat',side_effect=AssertionError('byte input must not stat')):
            self.assertEqual(ingest_bytes(self.db,'synthetic',b'')['records'],0)
            self.assertEqual(_normalize_bytes(b'[]','synthetic.json','web'),[])

    def test_published_source_admission_guide(self):
        blocks=re.findall(r'```sh\n(.*?)```',Path('docs/SOURCE_FILE_ADMISSION.md').read_text(),re.S)
        self.assertEqual(len(blocks),1)
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);args[0]=sys.executable
            result=subprocess.run([s.replace('OUTPUT',str(self.root)) for s in args],capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
