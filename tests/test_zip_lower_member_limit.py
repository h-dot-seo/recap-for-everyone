"""Operator-selected member bounds can reduce, never raise, existing limits."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from recaplib import prepare_web_export as p
from recaplib.inspect_web_zip import inspect_web_zip
from tests.test_title_queue_workflow import synthetic_exports
ROOT=Path(__file__).resolve().parents[1]


class LowerMemberLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'synthetic.zip'
        web,_=synthetic_exports(self.root);self.content=web.read_bytes()
        with zipfile.ZipFile(self.path,'w') as archive: archive.writestr('conversations.json',self.content)

    def test_invalid_type_and_range_before_read(self):
        with patch.object(p,'archive_bytes',side_effect=AssertionError('must validate before read')):
            for value in [True,False,0,-1,1.5,'10',p.MAX_MEMBER_BYTES+1]:
                for action in [lambda:inspect_web_zip(self.path,max_member_bytes=value),
                               lambda:p.prepare_web_export(self.path,'conversations.json',self.root/'no',max_member_bytes=value)]:
                    with self.subTest(value=value),self.assertRaisesRegex(ValueError,'max_member_bytes'):action()

    def test_lower_bound_filters_without_decompression(self):
        with patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('metadata only')):
            result=inspect_web_zip(self.path,max_member_bytes=1)
        self.assertEqual(result['limits']['member_bytes'],1)
        self.assertTrue(result['limits']['operator_supplied'])
        self.assertEqual(result['candidates'][0]['exceeded_limits'],['member_bytes'])
        self.assertEqual(result['candidates'][0]['reason_code'],'MEMBER_EXPANSION_LIMIT')

    def test_rejection_before_member_read_or_staging(self):
        with patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('no read')),patch.object(p.tempfile,'mkstemp',side_effect=AssertionError('no staging')):
            with self.assertRaisesRegex(ValueError,'member_bytes=1'):
                p.prepare_web_export(self.path,'conversations.json',self.root/'no',max_member_bytes=1)
        self.assertFalse((self.root/'no').exists())

    def test_exact_bound_success_and_actual_read_budget(self):
        reads=[];original=zipfile.ZipExtFile.read
        def read(stream,n=-1):
            reads.append(n);return original(stream,n)
        limit=len(self.content)
        with patch.object(zipfile.ZipExtFile,'read',read):
            result=p.prepare_web_export(self.path,'conversations.json',self.root/'prepared',max_member_bytes=limit)
        self.assertEqual(reads,[limit+1])
        self.assertEqual((self.root/'prepared').read_bytes(),self.content)
        self.assertEqual(result['limits']['member_bytes'],limit)
        self.assertTrue(result['limits']['operator_supplied'])

    def test_ratio_ceiling_not_relaxed_and_runtime_maximum(self):
        with patch.object(p,'MAX_MEMBER_BYTES',20):
            self.assertEqual(p.validate_member_limit(None),20)
            self.assertEqual(p.validate_member_limit(20),20)
            with self.assertRaises(ValueError):p.validate_member_limit(21)
        info=zipfile.ZipInfo('conversations.json');info.file_size=1000;info.compress_size=1
        self.assertEqual(p.exceeded_member_limits(info,1000),['ratio'])

    def test_default_and_explicit_maximum_have_same_eligibility(self):
        default=inspect_web_zip(self.path);explicit=inspect_web_zip(self.path,max_member_bytes=p.MAX_MEMBER_BYTES)
        self.assertEqual(default['candidates'],explicit['candidates'])
        self.assertFalse(default['limits']['operator_supplied'])
        self.assertTrue(explicit['limits']['operator_supplied'])

    def test_hash_lease_and_crc_remain_enforced(self):
        with self.assertRaisesRegex(ValueError,'changed after inspection'):
            p.prepare_web_export(self.path,'conversations.json',self.root/'no',expected_archive_sha256='0'*64,max_member_bytes=len(self.content))
        raw=bytearray(self.path.read_bytes());raw[raw.index(self.content)]^=1;self.path.write_bytes(raw)
        with self.assertRaises(ValueError):p.prepare_web_export(self.path,'conversations.json',self.root/'no',max_member_bytes=len(self.content))
        self.assertFalse((self.root/'no').exists())

    def test_both_cli_options(self):
        limit=str(len(self.content))
        for command,extra in [('inspect-web-zip',[]),('prepare-web-export',['--member','conversations.json','--output',str(self.root/'cli')])]:
            run=subprocess.run([sys.executable,str(ROOT/'recap.py'),command,str(self.path),*extra,'--max-member-bytes',limit],capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(run.stdout)['limits']['member_bytes'],int(limit))
