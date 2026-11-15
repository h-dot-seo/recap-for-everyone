"""Synthetic two-pass file ingestion and unchanged byte-snapshot APIs."""
from codecs import BOM_UTF8
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib import archive as a
from recaplib.errors import SourceChanged
from tests.test_normalized_byte_ingest import row, encoded, tables


class StreamedIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'synthetic.jsonl';self.db=self.root/'stream.sqlite'

    def test_file_bytes_parity_physical_lines_bom_ignored_fields_and_duplicates(self):
        values=[row(text='한글\u2028synthetic 🌱',unused={'nonfinite':float('nan')}),row(message_id='next',title=''),row()]
        raws=[b'',BOM_UTF8,b'\r\n \r\t',encoded(values),BOM_UTF8+b'\r\n'+encoded(values).replace(b'\n',b'\r'),encoded(values).replace(b'\n',b'\r\n').rstrip(b'\r\n')]
        for i,raw in enumerate(raws):
            with self.subTest(i=i):
                # Distinct identities where values differ, repeated identical row otherwise.
                raw=raw.replace(b'"message_id": "u"',b'"message_id": "first"',1) if i>=3 else raw
                self.path.write_bytes(raw);db=self.root/('file'+str(i)+'.sqlite');other=self.root/('bytes'+str(i)+'.sqlite')
                actual=a.ingest(db,'synthetic',self.path);expected=a.ingest_bytes(other,'synthetic',raw)
                self.assertEqual(actual,expected);self.assertEqual(tables(db),tables(other))
                self.assertEqual(a.search(db,'orchard'),a.search(other,'orchard'))
                self.assertEqual(self.path.read_bytes(),raw)

    def test_invalid_all_input_rejects_before_database_open(self):
        bad=[b'\xff',b'{}\n',b'{"a":1,"a":2}\n',encoded([row(),row(text='different')]),encoded([row(role='bad')]),(json.dumps(row(unused='\ud800'))+'\n').encode('ascii')]
        for raw in bad:
            self.path.write_bytes(raw)
            with self.subTest(raw=raw[:20]),patch.object(sqlite3,'connect',side_effect=AssertionError('no database')):
                with self.assertRaises(ValueError):a.ingest(self.db,'synthetic',self.path)
            self.assertFalse(self.db.exists())

    def test_error_precedence_matches_snapshot_expected_unicode_then_rows(self):
        cases=[b'not json\n\xff',encoded([row(),row(text='conflict')])+b'\xff',b'not json\n',encoded([row(),row(text='conflict')])]
        for raw in cases:
            self.path.write_bytes(raw)
            for expected in (None,'0'*64,'BAD'):
                with self.subTest(raw=raw[:10],expected=expected):
                    try:a.ingest_bytes(self.db,'synthetic',raw,expected_sha256=expected)
                    except Exception as old:error=old
                    else:self.fail('bad snapshot unexpectedly accepted')
                    with patch.object(sqlite3,'connect',side_effect=AssertionError('no database')):
                        with self.assertRaises(type(error)) as caught:a.ingest(self.db,'synthetic',self.path,expected_sha256=expected)
                    if not isinstance(error,UnicodeDecodeError):self.assertEqual(str(caught.exception),str(error))
            self.assertFalse(self.db.exists())

    def test_one_open_handle_no_whole_file_read_or_private_staging(self):
        raw=encoded([row()]);self.path.write_bytes(raw);opener=Path.open;handles=[]
        def opened(path,*args,**kw):
            stream=opener(path,*args,**kw)
            if path==self.path:handles.append(stream)
            return stream
        with patch.object(Path,'open',opened),patch.object(Path,'read_bytes',side_effect=AssertionError('whole source copy')),patch('tempfile.mkstemp',side_effect=AssertionError('staging')),patch('tempfile.NamedTemporaryFile',side_effect=AssertionError('staging')):
            result=a.ingest(self.db,'synthetic',self.path)
        self.assertEqual(len(handles),1);self.assertTrue(handles[0].closed)
        self.assertEqual(result['source_sha256'],hashlib.sha256(raw).hexdigest())

    def _change_on_connect(self,changed):
        real=sqlite3.connect
        def connect(*args,**kwargs):
            self.path.write_bytes(changed)
            return real(*args,**kwargs)
        return patch.object(sqlite3,'connect',side_effect=connect)

    def test_second_pass_changed_valid_source_rolls_back_existing_rows_fts_artifacts(self):
        a.ingest_bytes(self.db,'synthetic',encoded([row()]))
        raw=encoded([row(message_id='new')]);self.path.write_bytes(raw);before=tables(self.db)
        with self._change_on_connect(encoded([row(message_id='different')])):
            with self.assertRaises(SourceChanged):a.ingest(self.db,'synthetic',self.path)
        self.assertEqual(tables(self.db),before)

    def test_second_pass_parse_failure_rolls_back_but_new_empty_schema_can_remain(self):
        self.path.write_bytes(encoded([row()]))
        with self._change_on_connect(b'not JSON'):
            with self.assertRaises(ValueError):a.ingest(self.db,'synthetic',self.path)
        self.assertTrue(self.db.exists())
        with closing(sqlite3.connect(self.db)) as c:
            for table in ('messages','artifacts','messages_fts'):
                self.assertEqual(c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_archive_conflict_preserves_existing_tables(self):
        a.ingest_bytes(self.db,'synthetic',encoded([row()]));before=tables(self.db)
        self.path.write_bytes(encoded([row(message_id='new'),row(text='changed')]))
        with self.assertRaisesRegex(ValueError,'conflicting message identity at line 2'):
            a.ingest(self.db,'synthetic',self.path)
        self.assertEqual(tables(self.db),before)

    def test_provenance_api_retains_snapshot_fallback(self):
        raw=encoded([row()]);self.path.write_bytes(raw);reader=Path.read_bytes;calls=[]
        def read(path):calls.append(path);return reader(path)
        with patch.object(Path,'read_bytes',read):result=a.ingest(self.db,'synthetic',self.path,provenance=[])
        other=self.root/'bytes.sqlite';expected=a.ingest_bytes(other,'synthetic',raw,provenance=[])
        self.assertEqual(calls,[self.path]);self.assertEqual(result,expected);self.assertEqual(tables(self.db),tables(other))

    def test_all_compared_payload_fields_conflict_and_ignored_fields_do_not(self):
        base=row()
        for field,value in [('role','assistant'),('timestamp','next'),('title','changed'),('text','changed')]:
            self.path.write_bytes(encoded([base,row(**{field:value})]))
            with self.subTest(field=field),patch.object(sqlite3,'connect',side_effect=AssertionError('no database')):
                with self.assertRaisesRegex(ValueError,'conflicting message identity at line 2'):
                    a.ingest(self.db,'synthetic',self.path)
        self.path.write_bytes(encoded([base,row(ignored='different')]))
        result=a.ingest(self.db,'synthetic',self.path)
        self.assertEqual((result['records'],result['inserted']),(2,1))

    def test_chunk_boundary_utf8_crlf_and_last_line(self):
        # Positions around decoder buffer boundaries; Unicode separators are content.
        for size in (8188,8191,8192,8193,16383):
            raw=BOM_UTF8+encoded([row(text='x'*size+'🌱\u2028한글')]).rstrip(b'\n')+b'\r\n\r'+encoded([row(message_id='next')]).rstrip(b'\n')
            self.path.write_bytes(raw);db=self.root/('chunk'+str(size)+'.sqlite');other=self.root/('reference'+str(size)+'.sqlite')
            self.assertEqual(a.ingest(db,'synthetic',self.path),a.ingest_bytes(other,'synthetic',raw))
            self.assertEqual(tables(db),tables(other))

    def test_change_and_restore_between_passes_is_not_observed(self):
        raw=encoded([row()]);self.path.write_bytes(raw);real=sqlite3.connect
        def connect(*args,**kwargs):
            self.path.write_bytes(b'transient unobserved change')
            self.path.write_bytes(raw)
            return real(*args,**kwargs)
        with patch.object(sqlite3,'connect',side_effect=connect):result=a.ingest(self.db,'synthetic',self.path)
        self.assertEqual(result['source_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['inserted'],1)

    def test_final_hash_failure_precedes_commit_and_closes_connection(self):
        raw=encoded([row()]);self.path.write_bytes(raw);real=sqlite3.connect;connections=[];sql=[]
        def connect(*args,**kwargs):
            self.path.write_bytes(encoded([row(message_id='changed')]))
            c=real(*args,**kwargs);c.set_trace_callback(sql.append);connections.append(c);return c
        with patch.object(sqlite3,'connect',side_effect=connect):
            with self.assertRaises(SourceChanged):a.ingest(self.db,'synthetic',self.path)
        index=sql.index('BEGIN IMMEDIATE')
        self.assertIn('ROLLBACK',sql[index:]);self.assertNotIn('COMMIT',sql[index:])
        with self.assertRaises(sqlite3.ProgrammingError):connections[0].execute('SELECT 1')

    def test_missing_path_io_error_precedes_bad_expected_hash(self):
        with self.assertRaises(FileNotFoundError):a.ingest(self.db,'synthetic',self.path,expected_sha256='BAD')
        self.assertFalse(self.db.exists())

    def test_published_streamed_ingest_guide(self):
        blocks=re.findall(r'```sh\n(.*?)```',Path('docs/STREAMED_INGEST.md').read_text(),re.S)
        self.assertEqual(len(blocks),1)
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line);args[0]=sys.executable
            result=subprocess.run([s.replace('OUTPUT',str(self.root)) for s in args],capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
