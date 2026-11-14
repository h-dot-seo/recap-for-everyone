"""Fixed ZIP resource bounds are disclosed, not relaxed or streamed."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
from recaplib import prepare_web_export as preparation
from recaplib.inspect_web_zip import inspect_web_zip
from tests.test_title_queue_workflow import synthetic_exports


class ZipLimitDisclosureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'synthetic.zip'

    def write(self, name='conversations.json', content=b'[]', compression=zipfile.ZIP_STORED):
        with zipfile.ZipFile(self.path,'w',compression=compression) as archive:
            archive.writestr(name,content)

    def test_fixed_defaults_and_successful_prepare_receipt(self):
        web,_=synthetic_exports(self.root);self.write(content=web.read_bytes())
        expected=dict(member_bytes=16*1024*1024,ratio=200,entries=1000,
                      archive_ceiling=64*1024*1024,operator_supplied=False)
        inventory=inspect_web_zip(self.path)
        prepared=preparation.prepare_web_export(self.path,'conversations.json',self.root/'prepared.json')
        self.assertEqual(inventory['limits'],expected);self.assertEqual(prepared['limits'],expected)
        self.assertEqual(inventory['candidates'][0]['exceeded_limits'],[])
        self.assertEqual((self.root/'prepared.json').read_bytes(),web.read_bytes())

    def test_call_time_constants_and_metadata_only_size_failure(self):
        self.write(content=b'x'*20)
        with patch.object(preparation,'MAX_MEMBER_BYTES',10),patch.object(preparation,'MAX_RATIO',100), \
             patch.object(preparation,'MAX_ENTRIES',5),patch.object(preparation,'MAX_ARCHIVE_BYTES',1000), \
             patch.object(zipfile.ZipFile,'open',side_effect=AssertionError('no member read')):
            result=inspect_web_zip(self.path)
        self.assertEqual(result['limits'],dict(member_bytes=10,ratio=100,entries=5,archive_ceiling=1000,operator_supplied=False))
        row=result['candidates'][0]
        self.assertEqual(row['reason_code'],'MEMBER_EXPANSION_LIMIT')
        self.assertEqual(row['exceeded_limits'],['member_bytes'])
        self.assertFalse(row['metadata_eligible'])

    def test_ratio_only_and_both_diagnostics(self):
        self.write(content=b'x'*1000,compression=zipfile.ZIP_DEFLATED)
        for member_limit,expected in [(2000,['ratio']),(10,['member_bytes','ratio'])]:
            with self.subTest(member_limit=member_limit),patch.object(preparation,'MAX_MEMBER_BYTES',member_limit),patch.object(preparation,'MAX_RATIO',2):
                row=inspect_web_zip(self.path)['candidates'][0]
                self.assertEqual(row['reason_code'],'MEMBER_EXPANSION_LIMIT')
                self.assertEqual(row['exceeded_limits'],expected)
                with self.assertRaises(ValueError): preparation.prepare_web_export(self.path,'conversations.json',self.root/'never.json')
                self.assertFalse((self.root/'never.json').exists())

    def test_exact_boundaries_and_zero_compressed_denominator(self):
        info=zipfile.ZipInfo('conversations.json');info.file_size=10;info.compress_size=0
        with patch.object(preparation,'MAX_MEMBER_BYTES',10),patch.object(preparation,'MAX_RATIO',10):
            self.assertEqual(preparation.exceeded_member_limits(info),[])
            info.file_size=11
            self.assertEqual(preparation.exceeded_member_limits(info),['member_bytes','ratio'])

    def test_primary_unsafe_and_duplicate_reasons_preserved(self):
        self.write('../conversations.json',b'x'*20)
        with patch.object(preparation,'MAX_MEMBER_BYTES',10):
            row=inspect_web_zip(self.path)['candidates'][0]
        self.assertEqual(row['reason_code'],'UNSAFE_MEMBER_NAME')
        self.assertEqual(row['exceeded_limits'],['member_bytes'])
        self.write(content=b'x'*20)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(self.path,'a') as archive: archive.writestr('conversations.json',b'x'*20)
        with patch.object(preparation,'MAX_MEMBER_BYTES',10):
            rows=inspect_web_zip(self.path)['candidates']
        self.assertTrue(all(r['reason_code']=='DUPLICATE_MEMBER' and r['exceeded_limits']==['member_bytes'] for r in rows))

    def test_top_level_bounds_still_reject_before_zip_construction(self):
        self.write()
        for name,value in [('MAX_ARCHIVE_BYTES',1),('MAX_ENTRIES',0)]:
            with self.subTest(name=name),patch.object(preparation,name,value),patch.object(zipfile,'ZipFile',side_effect=AssertionError('must reject before parsing')):
                with self.assertRaises(ValueError): inspect_web_zip(self.path)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['synthetic.zip'])
