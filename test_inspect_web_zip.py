"""Metadata-only candidate discovery before explicit split-export preparation."""
import hashlib
import json
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch
from inspect_web_zip import inspect_web_zip
from prepare_web_export import prepare_web_export
from test_title_queue_workflow import synthetic_exports


class InspectWebZipTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name);self.path=self.directory/'export.zip'
        self.web,self.local=synthetic_exports(self.directory)
        conversations=json.loads(self.web.read_text())
        with zipfile.ZipFile(self.path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('conversations-002.json',json.dumps(conversations[6:]))
            archive.writestr('conversations-001.json',json.dumps(conversations[:6]))
            archive.writestr('account-private.json','SYNTHETIC NOT LISTED OR DECOMPRESSED')

    def test_metadata_only_no_decompression_database_or_writes(self):
        import prepare_web_export as preparation
        original=self.path.read_bytes();before=set(self.directory.iterdir())
        with patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('must not decompress')), \
             patch.object(preparation,'_normalize_bytes',side_effect=AssertionError('must not parse JSON')), \
             patch.object(sqlite3,'connect',side_effect=AssertionError('must not open DB')):
            result=inspect_web_zip(self.path)
        self.assertEqual(result['archive_sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(result['total_candidates'],2);self.assertEqual(result['other_entries_not_listed'],1)
        self.assertEqual([x['numbered_part_hint'] for x in result['candidates']],['002','001'])
        self.assertFalse(result['members_decompressed']);self.assertEqual(result['parts_completeness'],'NOT_ASSESSED')
        self.assertNotIn('account-private',json.dumps(result));self.assertNotIn('SYNTHETIC NOT LISTED',json.dumps(result))
        self.assertEqual(self.path.read_bytes(),original);self.assertEqual(set(self.directory.iterdir()),before)

    def test_page_order_and_name_heuristic_do_not_claim_complete_sequence(self):
        with zipfile.ZipFile(self.path,'a') as archive:
            archive.writestr('nested/CONVERSATIONS_007.JSON','invalid JSON')
            archive.writestr('conversations9.json','[]')
            archive.writestr('different-export.json','[]')
        first=inspect_web_zip(self.path,limit=2)
        second=inspect_web_zip(self.path,limit=2,offset=first['next_offset'])
        self.assertEqual(second['total_candidates'],4);self.assertIsNone(second['next_offset'])
        self.assertEqual([c['numbered_part_hint'] for c in second['candidates']],['007','9'])
        self.assertTrue(second['candidates'][0]['metadata_eligible'])
        with self.assertRaisesRegex(ValueError,'supported web export'):
            prepare_web_export(self.path,second['candidates'][0]['member'],self.directory/'never.json')
        self.assertEqual(inspect_web_zip(self.path,offset=100)['candidates'],[])

    def test_duplicate_unsafe_symlink_and_compression_metadata_are_ineligible(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(self.path,'a') as archive:
                archive.writestr('conversations-001.json','[]')
                archive.writestr('../conversations-003.json','[]')
                info=zipfile.ZipInfo('conversations-004.json');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
                archive.writestr(info,'target')
                archive.writestr('conversations-005.json','[]',compress_type=zipfile.ZIP_BZIP2)
        result=inspect_web_zip(self.path)
        reasons=[c['reason_code'] for c in result['candidates']]
        self.assertEqual(reasons.count('DUPLICATE_MEMBER'),2)
        self.assertIn('UNSAFE_MEMBER_NAME',reasons);self.assertIn('NONREGULAR_MEMBER',reasons)
        self.assertIn('UNSUPPORTED_COMPRESSION',reasons)
        for candidate in result['candidates']:
            if not candidate['metadata_eligible']:
                with self.assertRaises(ValueError):prepare_web_export(self.path,candidate['member'],self.directory/'never.json')
        self.assertFalse((self.directory/'never.json').exists())

    def test_crc_not_checked_until_prepare_and_archive_limits_shared(self):
        content=self.web.read_bytes()
        with zipfile.ZipFile(self.path,'w',compression=zipfile.ZIP_STORED) as archive:archive.writestr('conversations.json',content)
        raw=bytearray(self.path.read_bytes());raw[raw.index(content)]^=1;self.path.write_bytes(raw)
        self.assertTrue(inspect_web_zip(self.path)['candidates'][0]['metadata_eligible'])
        with self.assertRaises(ValueError):prepare_web_export(self.path,'conversations.json',self.directory/'never.json')
        import prepare_web_export as preparation
        with patch.object(preparation,'MAX_ARCHIVE_BYTES',10):
            with self.assertRaises(ValueError):inspect_web_zip(self.path)
        with patch.object(preparation,'MAX_ENTRIES',0):
            with self.assertRaises(ValueError):inspect_web_zip(self.path)

    def test_invalid_pagination_precedes_read_and_one_immutable_archive_snapshot(self):
        import prepare_web_export as preparation
        with patch.object(preparation,'archive_bytes',side_effect=AssertionError('must validate first')):
            for limit,offset in ((0,0),(101,0),(True,0),(1,-1),(1,True),(1,2**63)):
                with self.assertRaises(ValueError):inspect_web_zip(self.path,limit,offset)
        original=preparation.archive_bytes;raw=self.path.read_bytes();calls=[]
        def replace_after_read(path):
            calls.append(path);content=original(path);Path(path).write_bytes(b'changed after snapshot');return content
        with patch.object(preparation,'archive_bytes',replace_after_read):result=inspect_web_zip(self.path)
        self.assertEqual(len(calls),1);self.assertEqual(result['archive_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['total_candidates'],2)

    def test_cli_inspect_split_parts_prepare_import_and_review_with_local_sessions(self):
        db=self.directory/'archive.sqlite'
        def call(*args):
            result=subprocess.run([sys.executable,'recap.py',*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
        inventory=call('--db',db,'inspect-web-zip',self.path)
        self.assertFalse(db.exists());self.assertEqual(inventory['total_candidates'],2)
        for index,candidate in enumerate(inventory['candidates']):
            output=self.directory/f'part{index}.json'
            prepared=call('prepare-web-export',self.path,'--member',candidate['member'],'--output',output,'--expected-archive-sha256',inventory['archive_sha256'])
            self.assertEqual(prepared['archive_sha256'],inventory['archive_sha256'])
            call('--db',db,'import',output,'--format','web','--source','demo')
        call('--db',db,'import',self.local,'--format','local-codex','--source','demo')
        queue=call('--db',db,'review-titles','--source','demo','--limit','24')
        self.assertEqual(queue['total_conversations'],24)
        saved=self.directory/'queue.json';saved.write_text(json.dumps(queue))
        reviewed=call('--db',db,'preview-title',saved,'--conversation','web-05','--title','Prepared split export plan')
        saved.write_text(json.dumps(reviewed));call('--db',db,'apply-title',saved)
        self.assertEqual(call('--db',db,'find','split export')['total_matches'],1)

    def test_preparation_can_bind_inspected_archive_hash_before_decompression(self):
        expected=inspect_web_zip(self.path)['archive_sha256']
        with zipfile.ZipFile(self.path,'a') as archive:archive.writestr('changed-metadata.txt','synthetic change')
        output=self.directory/'never.json'
        with patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('must reject before decompression')):
            with self.assertRaisesRegex(ValueError,'changed after inspection'):
                prepare_web_export(self.path,'conversations-001.json',output,expected)
        self.assertFalse(output.exists())
        for value in (True,'bad','A'*64):
            with self.assertRaises(ValueError):prepare_web_export(self.path,'conversations-001.json',output,value)
