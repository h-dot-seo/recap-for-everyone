"""Bounded document admission preserves decoding, not immutable-path guarantees."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib import input_files
from recaplib.input_files import read_document_bytes,read_document_text
from recaplib.title_proposal import read_document
from recaplib.strict_json import loads

ROOT=Path(__file__).resolve().parents[1]
class TitleDocumentAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'synthetic.json';self.db=self.root/'absent.sqlite'
    def test_exact_byte_boundary_and_multibyte(self):
        raw='"é"'.encode();self.path.write_bytes(raw)
        with patch.object(input_files,'MAX_DOCUMENT_BYTES',len(raw)):
            self.assertEqual(read_document(self.path),'é')
        with patch.object(input_files,'MAX_DOCUMENT_BYTES',len(raw)-1),patch.object(Path,'read_bytes',side_effect=AssertionError('no read')):
            with self.assertRaisesRegex(ValueError,'8 MiB'):read_document(self.path)
    def test_actual_eight_mib_boundary(self):
        size=8*1024*1024;self.path.write_bytes(b'"'+b'x'*(size-2)+b'"')
        self.assertEqual(len(read_document_bytes(self.path)),size)
        with self.path.open('ab') as stream:stream.write(b' ')
        with patch.object(Path,'read_bytes',side_effect=AssertionError('no read')):
            with self.assertRaises(ValueError):read_document_bytes(self.path)
    def test_growth_postread_rejected_and_one_read(self):
        self.path.write_bytes(b'{}');seen=[]
        def grown(path):seen.append(path);return b'12345'
        with patch.object(input_files,'MAX_DOCUMENT_BYTES',4),patch.object(Path,'read_bytes',grown):
            with self.assertRaises(ValueError):read_document_bytes(self.path)
        self.assertEqual(seen,[self.path])
    def test_directory_and_device_before_read(self):
        for path in (self.root,Path('NUL' if os.name=='nt' else '/dev/null')):
            with patch.object(Path,'read_bytes',side_effect=AssertionError('no read')),patch('sqlite3.connect',side_effect=AssertionError('no database')):
                with self.assertRaises(ValueError) as error:read_document(path)
                self.assertNotIn(str(self.root),str(error.exception))
    def test_missing_path_preserves_oserror(self):
        with self.assertRaises(FileNotFoundError):read_document(self.path)
    def test_bom_and_universal_newline_contracts(self):
        for ending in (b'\n',b'\r',b'\r\n'):
            raw=b'{'+ending+b'"a":1'+ending+b'}';self.path.write_bytes(raw)
            self.assertEqual(read_document(self.path),{'a':1});self.assertEqual(loads(read_document_text(self.path)),{'a':1})
            self.assertEqual(read_document_text(self.path),self.path.read_text(encoding='utf-8'))
            self.path.write_bytes(b'\xef\xbb\xbf'+raw);self.assertEqual(read_document(self.path),{'a':1})
            with self.assertRaises(ValueError):loads(read_document_text(self.path))
    def test_regular_symlink_original_read_path(self):
        self.path.write_bytes(b'{}');link=self.root/'link.json'
        try:link.symlink_to(self.path)
        except (OSError,NotImplementedError):self.skipTest('symlink unavailable')
        original=Path.read_bytes;seen=[]
        def read(path):seen.append(path);return original(path)
        with patch.object(Path,'read_bytes',read):self.assertEqual(read_document(link),{})
        self.assertEqual(seen,[link])
    def test_invalid_json_newline_error_matches_old_read_text(self):
        self.path.write_bytes(b'{\r\n"a":\r\nBROKEN}')
        errors=[]
        for text in (self.path.read_text(encoding='utf-8'),read_document_text(self.path)):
            try:loads(text)
            except ValueError as error:errors.append(str(error))
        self.assertEqual(len(errors),2);self.assertEqual(errors[0],errors[1])
    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX FIFO only')
    def test_cli_fifo_preview_plan_and_transfer_fail_promptly(self):
        os.mkfifo(self.path)
        cases=[['recap.py','--db',str(self.db),'preview-title',str(self.path)],
               ['recap.py','--db',str(self.db),'check-title-plan','unused',str(self.path)],
               ['title_plan.py','--db',str(self.db),'check','unused',str(self.path)],
               ['recap.py','--db',str(self.db),'title-adapter-dry-run','unused','unused',str(self.path)]]
        for args in cases:
            r=subprocess.run([sys.executable,*args],cwd=ROOT,capture_output=True,timeout=5)
            self.assertEqual(r.returncode,1,(args,r.stderr));self.assertIn(b'regular file',r.stderr);self.assertFalse(self.db.exists())
    def test_existing_smaller_budgets_unchanged(self):
        from recaplib import title_adapter,title_batch
        self.assertEqual(title_adapter.MAX_PREPARED_DOCUMENT_BYTES,8*1024*1024)
        self.assertEqual(title_batch.MAX_SUPPLIED_BYTES,1024*1024)
