"""Deterministic synthetic inputs, private observations and fresh-write boundaries."""
import copy
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from recaplib import benchmark as bench

ROOT=Path(__file__).resolve().parents[1]


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.fixture=self.root/'fixture'
        self.work=self.root/'work'
        self.receipt=self.root/'receipt.json'

    def generate(self,n=2,m=2,seed=7):
        return bench.generate_fixture(self.fixture,n,m,seed)

    def test_deterministic_all_bytes_seed_and_fixed_zip(self):
        result=self.generate()
        other=self.root/'same';bench.generate_fixture(other,2,2,7)
        different=self.root/'different';bench.generate_fixture(different,2,2,8)
        self.assertEqual({k:result[k] for k in ('status','conversations','messages','files')},
                         dict(status='GENERATED',conversations=2,messages=4,files=5))
        for name in bench.FILES+('manifest.json',):
            self.assertEqual((self.fixture/name).read_bytes(),(other/name).read_bytes())
            self.assertNotEqual((self.fixture/name).read_bytes(),(different/name).read_bytes())
        with zipfile.ZipFile(self.fixture/'web.zip') as archive:
            info=archive.infolist()[0]
            self.assertEqual(info.date_time,(2000,1,1,0,0,0))
            self.assertEqual(info.compress_type,zipfile.ZIP_STORED)
        if os.name!='nt':self.assertEqual(stat.S_IMODE(self.fixture.stat().st_mode),0o700)
        bench.validate_fixture(self.fixture)

    def test_limits_before_directory_creation(self):
        for n,m,seed in ((0,1,0),(True,1,0),(1,0,0),(50001,1,0),(1000,1000,0),(1,1,-1),(1,1,2**32),(1,1,'private')):
            with self.subTest(n=n,m=m,seed=seed),self.assertRaises(ValueError):
                bench.generate_fixture(self.fixture,n,m,seed)
            self.assertFalse(self.fixture.exists())
        bench._parameters(50000,1,0)
        with patch.object(bench,'MAX_BYTES',10),self.assertRaises(ValueError):self.generate()
        self.assertFalse(self.fixture.exists())

    def test_tampered_private_bytes_even_rehashed_manifest_refused(self):
        self.generate()
        path=self.fixture/'web.json';path.write_bytes(b'PRIVATE REAL EXPORT')
        manifest=json.loads((self.fixture/'manifest.json').read_bytes())
        manifest['files'][0]['sha256']=bench._hash(path.read_bytes())
        manifest['files'][0]['bytes']=len(path.read_bytes())
        (self.fixture/'manifest.json').write_bytes(bench._json(manifest))
        with self.assertRaises(ValueError):bench.run_benchmark(self.fixture,self.work,self.receipt)
        self.assertFalse(self.work.exists());self.assertFalse(self.receipt.exists())

    def test_exact_manifest_unknown_fields_types_and_paths(self):
        self.generate();path=self.fixture/'manifest.json';original=path.read_bytes()
        base=json.loads(original)
        for value in (dict(base,extra=True),dict(base,conversations=True),dict(base,synthetic_only=1),dict(base,seed='PRIVATE')):
            path.write_bytes(bench._json(value))
            with self.assertRaises(ValueError):bench.validate_fixture(self.fixture)
        value=copy.deepcopy(base);value['files'][0]['path']='../outside'
        path.write_bytes(bench._json(value))
        with self.assertRaises(ValueError):bench.validate_fixture(self.fixture)
        path.write_bytes(original)
        (self.fixture/'extra').write_bytes(b'unknown')
        with self.assertRaises(ValueError):bench.validate_fixture(self.fixture)

    def test_existing_output_and_work_refused_before_fixture_read(self):
        self.receipt.write_bytes(b'keep')
        with patch.object(bench,'validate_fixture',side_effect=AssertionError('read')),self.assertRaises(FileExistsError):
            bench.run_benchmark(self.fixture,self.work,self.receipt)
        self.assertFalse(self.work.exists());self.assertEqual(self.receipt.read_bytes(),b'keep')
        self.receipt.unlink();self.work.mkdir()
        with patch.object(bench,'validate_fixture',side_effect=AssertionError('read')),self.assertRaises(FileExistsError):
            bench.run_benchmark(self.fixture,self.work,self.receipt)
        with self.assertRaises(FileExistsError):bench.generate_fixture(self.work)

    def test_symlink_special_and_parent_boundaries(self):
        self.generate();path=self.fixture/'web.json';original=path.read_bytes();path.unlink()
        target=self.root/'target';target.write_bytes(original)
        try:path.symlink_to(target)
        except (OSError,NotImplementedError):pass
        else:
            with self.assertRaises(ValueError):bench.validate_fixture(self.fixture)
            path.unlink()
        if hasattr(os,'mkfifo'):
            os.mkfifo(path)
            with self.assertRaises(ValueError):bench.validate_fixture(self.fixture)
            path.unlink()
        with self.assertRaises(ValueError):bench.generate_fixture(self.root/'missing'/'nested')
        with self.assertRaises(ValueError):bench.run_benchmark(self.fixture,self.work,self.work)

    def test_full_small_measurement_separate_runs_history_and_private_receipt(self):
        self.generate();before={p.name:p.read_bytes() for p in self.fixture.iterdir()}
        result=bench.run_benchmark(self.fixture,self.work,self.receipt,2)
        self.assertEqual({k:result[k] for k in ('status','operations','repetitions','timing_runs','traced_runs')},
                         dict(status='RECORDED',operations=19,repetitions=2,timing_runs=38,traced_runs=38))
        self.assertTrue(result['staging_cleanup_complete']);self.assertTrue(result['receipt_published'])
        self.assertFalse(result['existing_archive_access']);self.assertFalse(result['network_access'])
        receipt=json.loads(self.receipt.read_bytes())
        self.assertEqual(receipt['schema'],'recap.benchmark-receipt.v1')
        for observations in receipt['operations'].values():
            self.assertEqual(len(observations['elapsed_seconds']),2)
            self.assertEqual(len(observations['python_peak_bytes']),2)
            self.assertTrue(all(value>=0 for value in observations['elapsed_seconds']))
            self.assertTrue(all(type(value) is int and value>=0 for value in observations['python_peak_bytes']))
        self.assertEqual(receipt['baseline'],dict(archive_bytes=(self.work/'read.sqlite').stat().st_size,
                                                 messages=4,conversations=2,title_history=3,review_history=1))
        self.assertEqual(set(receipt['runtime']),{'python','implementation','sqlite','system'})
        self.assertIn('examples/make_scale_fixture.py',receipt['code_identity']['files'])
        self.assertIn('benchmark.py',receipt['code_identity']['files'])
        self.assertNotIn(str(self.root),self.receipt.read_text())
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.fixture.iterdir()})
        connection=sqlite3.connect(self.work/'read.sqlite')
        try:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM title_history').fetchone()[0],3)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM title_review_history').fetchone()[0],1)
        finally:connection.close()
        for path in self.work.glob('measurement-*.sqlite'):
            connection=sqlite3.connect(path)
            try:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0],4)
                self.assertEqual(connection.execute('SELECT COUNT(DISTINCT conversation_id) FROM messages').fetchone()[0],2)
            finally:connection.close()
        self.assertFalse(bench.tracemalloc.is_tracing())
        self.assertNotIn('runtime',result);self.assertNotIn('elapsed_seconds',result)

    def test_history_setup_scales_with_selected_conversations(self):
        for n in (1,3):
            fixture=self.root/('fixture%d' % n)
            work=self.root/('work%d' % n)
            receipt=self.root/('receipt%d.json' % n)
            bench.generate_fixture(fixture,n,1,0)
            bench.run_benchmark(fixture,work,receipt)
            baseline=json.loads(receipt.read_bytes())['baseline']
            self.assertEqual(baseline['messages'],n)
            self.assertEqual(baseline['conversations'],n)
            self.assertEqual(baseline['title_history'],3*((n+1)//2))
            self.assertEqual(baseline['review_history'],(n+1)//2)

    def test_failure_preserves_new_scratch_and_stops_trace(self):
        self.generate()
        from recaplib.conversation_search import find
        with patch('recaplib.conversation_search.find',side_effect=ValueError('synthetic failure')),self.assertRaises(ValueError):
            bench.run_benchmark(self.fixture,self.work,self.receipt)
        self.assertTrue(self.work.is_dir());self.assertFalse(self.receipt.exists())
        self.assertFalse(bench.tracemalloc.is_tracing())

    def test_traced_failure_stops_tracing(self):
        self.generate()
        from recaplib.conversation_search import find
        def fail_when_traced(*args,**kwargs):
            if bench.tracemalloc.is_tracing():
                raise ValueError('synthetic traced failure')
            return find(*args,**kwargs)
        with patch('recaplib.conversation_search.find',fail_when_traced),self.assertRaises(ValueError):
            bench.run_benchmark(self.fixture,self.work,self.receipt)
        self.assertFalse(bench.tracemalloc.is_tracing())
        self.assertFalse(self.receipt.exists())

    def test_late_receipt_collision_preserved(self):
        self.generate()
        publish=bench._publish_new_file
        def collision(path,raw,prefix):
            if Path(path)==self.receipt:
                self.receipt.write_bytes(b'competing receipt')
            return publish(path,raw,prefix)
        with patch.object(bench,'_publish_new_file',collision),self.assertRaises(FileExistsError):
            bench.run_benchmark(self.fixture,self.work,self.receipt)
        self.assertEqual(self.receipt.read_bytes(),b'competing receipt')
        self.assertTrue(self.work.exists())

    def test_final_receipt_cleanup_failure_reports_published_remainder(self):
        self.generate()
        unlink=Path.unlink
        def fail(path,*args,**kwargs):
            if path.name.startswith('.recap-benchmark-'):
                raise OSError('synthetic cleanup failure')
            return unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail):
            result=bench.run_benchmark(self.fixture,self.work,self.receipt)
        self.assertTrue(self.receipt.exists())
        self.assertTrue(result['receipt_published'])
        self.assertFalse(result['staging_cleanup_complete'])
        self.assertTrue((self.receipt.parent/result['remaining_staging_file']).exists())
        self.assertFalse(bench.tracemalloc.is_tracing())

    def test_intermediate_publication_cleanup_failure_stops_with_preserved_files(self):
        unlink=Path.unlink
        for prefix in ('.recap-fixture-','.recap-input-'):
            with self.subTest(prefix=prefix):
                def fail(path,*args,**kwargs):
                    if path.name.startswith(prefix):raise OSError('synthetic cleanup failure')
                    return unlink(path,*args,**kwargs)
                if prefix=='.recap-fixture-':
                    with patch.object(Path,'unlink',fail),self.assertRaisesRegex(ValueError,'were published'):
                        bench.generate_fixture(self.root/'partial',1,1,0)
                    self.assertTrue((self.root/'partial'/'web.json').exists())
                else:
                    self.generate()
                    with patch.object(Path,'unlink',fail),self.assertRaisesRegex(ValueError,'were published'):
                        bench.run_benchmark(self.fixture,self.work,self.receipt)
                    self.assertTrue((self.work/'web.json').exists())
                    self.assertFalse(self.receipt.exists())

    def test_result_level_failure_is_not_recorded_as_normal_cost(self):
        self.generate()
        with patch('recaplib.recovery.rehearse_recovery',return_value={'status':'RECOVERY_REHEARSAL_FAILED'}), \
             self.assertRaisesRegex(ValueError,'functional checks'):
            bench.run_benchmark(self.fixture,self.work,self.receipt)
        self.assertFalse(self.receipt.exists())
        self.assertFalse(bench.tracemalloc.is_tracing())

    def test_documented_n50_commands(self):
        text=(ROOT/'docs/SCALING.md').read_text(encoding='utf-8')
        block=re.search(r'```sh\n(.*?)```',text,re.S).group(1)
        values=[]
        for line in block.strip().splitlines():
            if not line.strip() or line.startswith('#'):continue
            args=shlex.split(line)
            args=[str(self.root)+arg[len('OUTPUT'):] if arg.startswith('OUTPUT') else arg for arg in args]
            args[0]=sys.executable
            result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            value=json.loads(result.stdout);values.append(value)
            self.assertNotIn(str(self.root),result.stdout)
            self.assertNotIn('elapsed_seconds',result.stdout);self.assertNotIn('runtime',result.stdout)
        self.assertEqual(values[0]['conversations'],50)
        self.assertEqual(values[-1]['operations'],19)


if __name__=='__main__':
    unittest.main()
