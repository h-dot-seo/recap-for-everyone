"""Source refusal budgets using tiny synthetic bytes, never a 2 GiB allocation."""
import io
import sqlite3
from contextlib import closing
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from recaplib import archive, input_files
from recaplib.replay_local import reconstruct
from tests import test_source_file_admission as fixtures
from tests import test_streamed_ingest as stream_fixtures


class SourceSizeAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.SourceFileAdmissionTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.path=self.f.root/'synthetic.jsonl';self.path.write_bytes(b'[]')

    def test_exact_integer_budget_without_large_allocation(self):
        self.assertEqual(input_files.MAX_EXPORT_BYTES,2*1024**3)
        self.assertIs(type(input_files.MAX_EXPORT_BYTES),int)
        input_files.check_source_size(2147483648)
        with self.assertRaises(ValueError):input_files.check_source_size(2147483649)

    def test_stat_oversize_all_paths_before_read_or_database(self):
        original=Path.stat
        def metadata(path,*args,**kwargs):
            if path==self.path:return SimpleNamespace(st_mode=stat.S_IFREG,st_size=2147483649)
            return original(path,*args,**kwargs)
        with patch.object(Path,'stat',metadata),patch.object(Path,'open',side_effect=AssertionError('no input open')),patch('sqlite3.connect',side_effect=AssertionError('no database')):
            for call in self.f.calls(self.path):
                with self.subTest(call=call),self.assertRaises(ValueError) as error:call()
                self.assertNotIn(str(self.path),str(error.exception))
            self.assertEqual(reconstruct(self.path),dict(supported=False,reason_code='SOURCE_ERROR',line=0))
        self.assertFalse(self.f.db.exists())

    def test_exact_stat_budget_admitted_without_read(self):
        with patch.object(Path,'stat',return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_size=2147483648)),patch.object(Path,'open',side_effect=AssertionError('stat only')):
            input_files.require_source_file(self.path)

    def test_growth_after_stat_snapshot_read_seams(self):
        # Default streaming ingest is tested separately: the others retain read_bytes.
        with patch.object(input_files,'MAX_EXPORT_BYTES',8),patch.object(Path,'read_bytes',return_value=b'x'*9) as read,patch('sqlite3.connect',side_effect=AssertionError('no database')):
            for call in self.f.calls(self.path)[1:]:
                read.reset_mock()
                with self.subTest(call=call),self.assertRaises(ValueError) as error:call()
                self.assertEqual(read.call_count,1)
                self.assertNotIn(str(self.path),str(error.exception))
            read.reset_mock();self.assertEqual(reconstruct(self.path),dict(supported=False,reason_code='SOURCE_ERROR',line=0));self.assertEqual(read.call_count,1)
        self.assertFalse(self.f.db.exists())

    def test_hashing_reader_cumulative_exact_then_excess(self):
        reader=archive._HashingReader(io.BytesIO(b'123456789'))
        with patch.object(input_files,'MAX_EXPORT_BYTES',8):
            self.assertEqual(reader.readinto(bytearray(3)),3)
            self.assertEqual(reader.readinto(bytearray(5)),5)
            self.assertEqual(reader.size,8)
            with self.assertRaises(ValueError):reader.readinto(bytearray(1))
        reader.close()

    def test_stream_growth_first_pass_has_no_database_and_closes(self):
        # Stat sees the real tiny file; the same opened descriptor supplies larger bytes.
        handle=io.BytesIO(b' '*9)
        with patch.object(input_files,'MAX_EXPORT_BYTES',8),patch.object(Path,'open',return_value=handle) as opened,patch('sqlite3.connect',side_effect=AssertionError('no database')):
            with self.assertRaises(ValueError):archive.ingest(self.f.db,'synthetic',self.path)
        self.assertEqual(opened.call_count,1);self.assertTrue(handle.closed);self.assertFalse(self.f.db.exists())

    def test_direct_byte_api_does_not_gain_file_budget(self):
        with patch.object(input_files,'MAX_EXPORT_BYTES',0),patch.object(Path,'stat',side_effect=AssertionError('byte API must not stat')):
            result=archive.ingest_bytes(self.f.db,'synthetic',b'\n')
        self.assertEqual(result['records'],0)

    def test_second_pass_growth_rolls_back_existing_and_new_archive(self):
        raw=stream_fixtures.encoded([stream_fixtures.row()])
        for existing in (False,True):
            with self.subTest(existing=existing):
                db=self.f.root/('existing.sqlite' if existing else 'new.sqlite')
                if existing:archive.ingest_bytes(db,'old',raw)
                before=stream_fixtures.tables(db) if existing else None
                self.path.write_bytes(raw);real=sqlite3.connect;connections=[]
                def connect(*args,**kwargs):
                    self.path.write_bytes(raw+b' ')
                    conn=real(*args,**kwargs);connections.append(conn);return conn
                with patch.object(input_files,'MAX_EXPORT_BYTES',len(raw)),patch.object(sqlite3,'connect',side_effect=connect):
                    with self.assertRaises(ValueError):archive.ingest(db,'synthetic',self.path)
                self.assertTrue(db.exists())
                for conn in connections:
                    with self.assertRaises(sqlite3.ProgrammingError):conn.execute('SELECT 1')
                if existing:self.assertEqual(stream_fixtures.tables(db),before)
                else:
                    with closing(sqlite3.connect(db)) as conn:
                        for table in ('messages','artifacts','messages_fts'):
                            self.assertEqual(conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_exact_small_file_budget_keeps_receipt_and_fts(self):
        raw=stream_fixtures.encoded([stream_fixtures.row(text='synthetic Unicode 한글')])
        self.path.write_bytes(raw)
        with patch.object(input_files,'MAX_EXPORT_BYTES',len(raw)):
            actual=archive.ingest(self.f.db,'synthetic',self.path)
        other=self.f.root/'expected.sqlite';expected=archive.ingest_bytes(other,'synthetic',raw)
        self.assertEqual(actual,expected);self.assertEqual(stream_fixtures.tables(self.f.db),stream_fixtures.tables(other))
