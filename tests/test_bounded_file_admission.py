"""Pre-open type/size checks preserve existing bounded-read contracts."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib import prepare_web_export as preparation, recovery, title_batch, title_adapter
from recaplib.input_files import require_regular_file
ROOT=Path(__file__).resolve().parents[1]


class BoundedFileAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'synthetic.json';self.path.write_bytes(b'{}')

    def calls(self,path):
        return [lambda:preparation.archive_bytes(path),lambda:recovery._read_manifest(path),
                lambda:title_batch.load_supplied_proposals([path]),
                lambda:title_adapter._read_bounded(path,100,'SOURCE_ERROR')]

    def test_directory_rejected_without_open(self):
        with patch.object(Path,'open',side_effect=AssertionError('must reject before open')):
            for call in self.calls(self.root):
                with self.assertRaises(ValueError):call()

    def test_oversize_rejected_without_open_and_existing_error_contract(self):
        with patch.object(preparation,'MAX_ARCHIVE_BYTES',1),patch.object(recovery,'MAX_MANIFEST_BYTES',1),patch.object(title_batch,'MAX_SUPPLIED_BYTES',1),patch.object(Path,'open',side_effect=AssertionError('no open')):
            for call in self.calls(self.path)[:3]:
                with self.assertRaisesRegex(ValueError,'limit'):call()
            with self.assertRaises(title_adapter.AdapterError):title_adapter._read_bounded(self.path,1,'SOURCE_ERROR')

    def test_cumulative_supplied_proposal_budget(self):
        second=self.root/'second.json';second.write_bytes(b'{}')
        original=Path.open;opened=[]
        def open_file(path,*args,**kw):opened.append(path);return original(path,*args,**kw)
        with patch.object(title_batch,'MAX_SUPPLIED_BYTES',3),patch.object(Path,'open',open_file):
            with self.assertRaisesRegex(ValueError,'combined 1 MiB'):title_batch.load_supplied_proposals([self.path,second])
        self.assertEqual(opened,[self.path])

    def test_growth_after_stat_still_bounded_and_rejected(self):
        class Stream(io.BytesIO):
            def read(self,size=-1):self.size=size;return super().read(size)
        for module,constant,action in [
                (preparation,'MAX_ARCHIVE_BYTES',lambda:preparation.archive_bytes(self.path)),
                (recovery,'MAX_MANIFEST_BYTES',lambda:recovery._read_manifest(self.path)),
                (title_batch,'MAX_SUPPLIED_BYTES',lambda:title_batch.load_supplied_proposals([self.path]))]:
            stream=Stream(b'{}xxxxx')
            with patch.object(module,constant,2),patch.object(Path,'open',return_value=stream):
                with self.assertRaises(ValueError):action()
            self.assertEqual(stream.size,3);self.assertTrue(stream.closed)
        stream=Stream(b'{}xxxxx')
        with patch.object(Path,'open',return_value=stream):
            with self.assertRaises(title_adapter.AdapterError):title_adapter._read_bounded(self.path,2,'SOURCE_ERROR')
        self.assertEqual(stream.size,3)

    def test_regular_symlink_keeps_following_semantics(self):
        link=self.root/'link.json'
        try:link.symlink_to(self.path)
        except (OSError,NotImplementedError):self.skipTest('symlink unavailable')
        before=self.path.read_bytes()
        self.assertEqual(preparation.archive_bytes(link),before)
        self.assertEqual(title_batch.load_supplied_proposals([link]),[{}])
        self.assertEqual(title_adapter._read_bounded(link,100,'SOURCE_ERROR'),'{}')
        with patch.object(recovery,'_validate_manifest',return_value='validated'):
            self.assertEqual(recovery._read_manifest(link),(before,'validated'))
        self.assertEqual(self.path.read_bytes(),before);self.assertTrue(link.is_symlink())

    def test_missing_file_and_adapter_error_remain_existing_types(self):
        missing=self.root/'missing'
        for call in self.calls(missing)[:3]:
            with self.assertRaises(FileNotFoundError):call()
        with self.assertRaises(title_adapter.AdapterError):self.calls(missing)[3]()
        self.assertFalse(missing.exists())

    def test_device_rejected_without_read(self):
        device=Path('NUL' if os.name=='nt' else '/dev/null')
        with patch.object(Path,'open',side_effect=AssertionError('must not open device')):
            for call in self.calls(device):
                with self.assertRaises(ValueError):call()

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX FIFO only')
    def test_fifo_refused_in_timeout_bounded_subprocess(self):
        fifo=self.root/'pipe';os.mkfifo(fifo)
        script='''from pathlib import Path
from recaplib import prepare_web_export as p, recovery as r, title_batch as b, title_adapter as a
import sys
path=Path(sys.argv[1])
for call in [lambda:p.archive_bytes(path),lambda:r._read_manifest(path),lambda:b.load_supplied_proposals([path]),lambda:a._read_bounded(path,100,'SOURCE_ERROR')]:
    try:call()
    except ValueError:pass
    else:raise AssertionError('FIFO accepted')
'''
        run=subprocess.run([sys.executable,'-c',script,str(fifo)],cwd=ROOT,capture_output=True,text=True,timeout=5)
        self.assertEqual(run.returncode,0,run.stderr)
