"""Bounded synthetic ZIP preparation; never process real account exports."""
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from recaplib.prepare_web_export import prepare_web_export


class PrepareWebExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name);self.archive=self.directory/'synthetic.zip';self.output=self.directory/'prepared.json'
        self.content=Path('examples/web-export.json').read_bytes()
        self.write_zip()

    def write_zip(self,content=None,name='conversations.json',compression=zipfile.ZIP_DEFLATED):
        with zipfile.ZipFile(self.archive,'w',compression=compression) as archive:
            archive.writestr(name,self.content if content is None else content)
            archive.writestr('account-metadata.json','{"synthetic": true}')

    def prepare(self,member='conversations.json',output=None):return prepare_web_export(self.archive,member,output or self.output)

    def test_exact_bytes_hashes_no_other_member_or_database_access(self):
        original=self.archive.read_bytes()
        with patch.object(sqlite3,'connect',side_effect=AssertionError('no database access')):
            result=self.prepare()
        self.assertEqual(self.output.read_bytes(),self.content);self.assertEqual(self.archive.read_bytes(),original)
        self.assertEqual(result['archive_sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(result['prepared_sha256'],hashlib.sha256(self.content).hexdigest())
        self.assertEqual(result['coverage']['original_sha256'],result['prepared_sha256'])
        self.assertFalse(result['database_access']);self.assertTrue(result['staging_cleanup_complete'])
        self.assertFalse((self.directory/'account-metadata.json').exists())
        self.assertEqual(list(self.directory.glob('.recap-prepare-*')),[])

    def test_existing_destination_and_simultaneous_writers_never_overwrite(self):
        self.output.write_bytes(b'KEEP EXISTING')
        with self.assertRaises(FileExistsError):self.prepare()
        self.assertEqual(self.output.read_bytes(),b'KEEP EXISTING');self.output.unlink()
        def attempt(_):
            try:self.prepare();return 'created'
            except FileExistsError:return 'exists'
        with ThreadPoolExecutor(max_workers=2) as executor:self.assertEqual(sorted(executor.map(attempt,range(2))),['created','exists'])
        self.assertEqual(self.output.read_bytes(),self.content);self.assertEqual(list(self.directory.glob('.recap-prepare-*')),[])

    def test_traversal_duplicate_encrypted_symlink_and_directory_members_rejected(self):
        for member in ('../conversations.json','/conversations.json','a\\b.json','C:conversations.json','a//b.json','a/./b.json'):
            with self.assertRaises(ValueError):self.prepare(member)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(self.archive,'w') as archive:
                archive.writestr('conversations.json',self.content);archive.writestr('conversations.json',self.content)
        with self.assertRaisesRegex(ValueError,'exactly one'):self.prepare()
        info=zipfile.ZipInfo('conversations.json');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
        with zipfile.ZipFile(self.archive,'w') as archive:archive.writestr(info,b'synthetic-target')
        with self.assertRaisesRegex(ValueError,'regular file'):self.prepare()
        self.write_zip();raw=bytearray(self.archive.read_bytes())
        for signature,flag_offset in ((b'PK\x03\x04',6),(b'PK\x01\x02',8)):
            index=raw.index(signature);raw[index+flag_offset]|=1
        self.archive.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'encrypted'):self.prepare()
        self.assertFalse(self.output.exists())

    def test_corrupt_crc_invalid_json_and_unrecognized_shapes_leave_no_output(self):
        self.write_zip(compression=zipfile.ZIP_STORED)
        raw=bytearray(self.archive.read_bytes());index=raw.index(self.content);raw[index]^=1;self.archive.write_bytes(raw)
        with self.assertRaises(ValueError):self.prepare()
        for content in (b'not JSON',b'{}',b'[{"id":"x","id":"y","mapping":{}}]'):
            self.write_zip(content)
            with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.output.exists());self.assertEqual(list(self.directory.glob('.recap-prepare-*')),[])

    def test_limits_checked_without_large_test_allocations(self):
        from recaplib import prepare_web_export as module
        for name,value in [('MAX_ARCHIVE_BYTES',10),('MAX_MEMBER_BYTES',10),('MAX_ENTRIES',1),('MAX_RATIO',1)]:
            with patch.object(module,name,value):
                with self.assertRaises(ValueError):self.prepare()
        self.assertFalse(self.output.exists())

    def test_link_failure_cleanup_and_postpublication_cleanup_reporting(self):
        from recaplib import prepare_web_export as module
        with patch.object(module.os,'link',side_effect=OSError('synthetic unsupported hard link')):
            with self.assertRaises(OSError):self.prepare()
        self.assertFalse(self.output.exists());self.assertEqual(list(self.directory.glob('.recap-prepare-*')),[])
        original_unlink=Path.unlink
        def deny_staging_unlink(path,*args,**kwargs):
            if path.name.startswith('.recap-prepare-'):raise OSError('synthetic cleanup failure')
            return original_unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',deny_staging_unlink):result=self.prepare()
        self.assertEqual(self.output.read_bytes(),self.content);self.assertFalse(result['staging_cleanup_complete'])
        self.assertTrue((self.directory/result['remaining_staging_file']).exists())

    def test_numbered_member_cli_prepare_import_title_and_export_hash_search(self):
        self.write_zip(name='conversations-001.json')
        db=self.directory/'archive.sqlite'
        def call(*args,ok=True):
            result=subprocess.run([sys.executable,'recap.py',*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0 if ok else 1,result.stderr);self.assertNotIn('Traceback',result.stderr)
            return json.loads(result.stdout) if ok else result
        result=call('--db',db,'prepare-web-export',self.archive,'--member','conversations-001.json','--output',self.output)
        self.assertFalse(db.exists())
        call('--db',db,'import',self.output,'--format','web','--source','prepared')
        current=call('--db',db,'title','--source','prepared','--conversation','synthetic-chat')
        call('--db',db,'title','--source','prepared','--conversation','synthetic-chat','--set','Prepared orchard label','--expected-revision',current['revision'])
        self.assertEqual(call('--db',db,'find','orchard','--export-sha256',result['prepared_sha256'])['total_matches'],1)
        self.assertEqual(call('--db',db,'find','orchard','--export-sha256',result['archive_sha256'])['total_matches'],0)
        call('prepare-web-export',self.archive,'--member','conversations-001.json','--output',self.output,ok=False)
        self.assertEqual(self.output.read_bytes(),self.content)

    def test_only_selected_nested_stored_member_is_prepared(self):
        self.write_zip(name='part/conversations-002.json',compression=zipfile.ZIP_STORED)
        with zipfile.ZipFile(self.archive,'a') as archive:archive.writestr('../unsafe-unselected.json',b'not processed')
        result=self.prepare('part/conversations-002.json')
        self.assertEqual(self.output.read_bytes(),self.content)
        self.assertEqual(result['selected_member'],'part/conversations-002.json')
        self.assertFalse((self.directory/'part').exists())

    def test_dos_directory_and_unsupported_compression_rejected(self):
        info=zipfile.ZipInfo('conversations.json');info.external_attr=0x10
        with zipfile.ZipFile(self.archive,'w') as archive:archive.writestr(info,self.content)
        with self.assertRaisesRegex(ValueError,'regular file'):self.prepare()
        self.write_zip(compression=zipfile.ZIP_BZIP2)
        with self.assertRaisesRegex(ValueError,'stored or deflated'):self.prepare()
        self.assertFalse(self.output.exists())
