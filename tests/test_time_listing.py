"""Deterministic time interpretation and opt-in read-only inventory."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from recaplib.archive import ingest_bytes, readonly
from recaplib.conversation_view import conversations
from recaplib.session_workflow import titles
from recaplib.timestamps import RULE, date_bound, parse_timestamp, utc_text

ROOT = Path(__file__).resolve().parents[1]


class TimestampRuleTests(unittest.TestCase):
    def test_epoch_zero_fraction_and_date_looking_value(self):
        self.assertEqual(parse_timestamp('0'), (0, 'parsed_epoch_seconds'))
        self.assertEqual(parse_timestamp('1.123456789'), (1123456, 'parsed_epoch_seconds'))
        self.assertEqual(utc_text(parse_timestamp('20260101')[0]), '1970-08-23T11:48:21.000000Z')
        self.assertEqual(parse_timestamp('99999999999.999999999')[1], 'parsed_epoch_seconds')

    def test_iso_offsets_calendar_and_truncation(self):
        self.assertEqual(parse_timestamp('1970-01-01T09:00:00+09:00'), (0, 'parsed_iso'))
        self.assertEqual(parse_timestamp('1969-12-31T23:00:00-01:00'), (0, 'parsed_iso'))
        self.assertEqual(parse_timestamp('1970-01-01T00:00:00.123456789Z'), (123456, 'parsed_iso'))
        self.assertEqual(parse_timestamp('1969-12-31T23:59:59.999999999Z'), (-1, 'parsed_iso'))
        self.assertEqual(utc_text(parse_timestamp('2000-02-29T23:59:59Z')[0]), '2000-02-29T23:59:59.000000Z')

    def test_unparsed_grammar_not_guessed(self):
        values = [None, 1, True, '', 'unknown', '-1', '+1', '1e3', '.1', '1.', '123456789012',
                  '1.1234567890', ' 1', '1 ', '２０２６', '2026-01-01',
                  '2026-01-01T00:00:00', '20260101T000000Z', '2026-01-01t00:00:00z',
                  '2026-02-30T00:00:00Z', '1900-02-29T00:00:00Z', '0000-01-01T00:00:00Z',
                  '2026-01-01T24:00:00Z', '2026-01-01T00:60:00Z', '2026-01-01T00:00:60Z',
                  '2026-01-01T00:00:00+24:00', '2026-01-01T00:00:00+01:60',
                  '2026-01-01T00:00:00+0000', '2026-01-01T00:00:00.1234567890Z']
        for value in values:
            with self.subTest(value=value): self.assertEqual(parse_timestamp(value), (None, 'unparsed'))

    def test_utc_calendar_extremes(self):
        for value in ('0001-01-01T00:00:00Z', '9999-12-31T23:59:59.999999Z'):
            self.assertEqual(utc_text(parse_timestamp(value)[0]), value.replace('00:00:00Z','00:00:00.000000Z'))
        for value in ('0001-01-01T00:00:00+00:01', '9999-12-31T23:59:59-00:01'):
            self.assertEqual(parse_timestamp(value), (None, 'unparsed'))

    def test_date_bounds_strict_and_inclusive_end(self):
        self.assertEqual(date_bound('1970-01-01'), 0)
        self.assertEqual(date_bound('1970-01-01', end=True), 86400000000)
        self.assertGreater(date_bound('9999-12-31', end=True), parse_timestamp('9999-12-31T23:59:59Z')[0])
        for value in ('2026-2-01', '2026-02-30', '0000-01-01', ' 2026-01-01', True, 0):
            with self.subTest(value=value), self.assertRaises(ValueError): date_bound(value)


class TimeListingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name); self.db = self.home/'archive.sqlite'
        rows = [('a', '2026-01-01T00:00:00Z'), ('a', '2026-03-01T00:00:00Z'),
                ('b', '2026-02-01T00:00:00Z'), ('b', 'unknown'),
                ('c', '2026-02-01T09:00:00+09:00'), ('d', 'unknown'),
                ('e', '2026-01-31T23:59:59.999999999Z')]
        self.load('source', rows)

    def load(self, source, rows):
        content = [dict(conversation_id=c, message_id=str(i), role='user', timestamp=t,
                        title='original '+c, text='synthetic '+str(i)) for i,(c,t) in enumerate(rows)]
        ingest_bytes(self.db, source, ('\n'.join(json.dumps(r) for r in content)+'\n').encode())

    def ids(self, result):
        return [row['conversation'] for row in result['conversations']]

    def test_default_output_and_order_unchanged(self):
        result=conversations(self.db)
        self.assertEqual(self.ids(result), ['a','b','c','d','e'])
        self.assertEqual(set(result), {'conversations','total','limit','offset','scope'})
        self.assertEqual(set(result['conversations'][0]), {'source','conversation','original_title','display_title','revision','message_count'})

    def test_recent_oldest_ties_and_unknown_last(self):
        self.assertEqual(self.ids(conversations(self.db, order='recent')), ['a','b','c','e','d'])
        self.assertEqual(self.ids(conversations(self.db, order='oldest')), ['a','e','b','c','d'])
        result=conversations(self.db, order='recent')
        self.assertEqual(result['unordered_conversations'], 1)
        self.assertEqual(result['conversations'][-1]['first_parsed_utc'], None)
        self.assertEqual(result['timestamp_interpretation']['rule'], RULE)
        self.assertEqual(result['timestamp_interpretation']['parsed_iso'], 5)
        self.assertEqual(result['timestamp_interpretation']['unparsed'], 2)

    def test_window_is_conversation_level_extrema_include_all_messages(self):
        result=conversations(self.db, from_date='2026-01-01', until_date='2026-01-01')
        self.assertEqual(self.ids(result), ['a'])
        self.assertEqual(result['conversations'][0]['message_count'],2)
        self.assertEqual(result['conversations'][0]['last_parsed_utc'],'2026-03-01T00:00:00.000000Z')
        self.assertEqual(result['excluded_unparsed_conversations'],1)
        self.assertEqual(result['unordered_conversations'],0)
        self.assertEqual(result['order'],'binary')

    def test_inclusive_day_end_and_offset_equivalence(self):
        self.assertEqual(self.ids(conversations(self.db, from_date='2026-02-01', until_date='2026-02-01')), ['b','c'])
        self.assertEqual(self.ids(conversations(self.db, from_date='2026-01-31', until_date='2026-01-31')), ['e'])
        self.assertEqual(self.ids(conversations(self.db, until_date='2026-01-01')), ['a'])
        self.assertEqual(self.ids(conversations(self.db, from_date='2026-03-01')), ['a'])

    def test_pagination_counts_and_binary_source_ties(self):
        self.load('A', [('z','2026-02-01T00:00:00Z')])
        result=conversations(self.db, order='recent', limit=2, offset=1)
        self.assertEqual([(r['source'],r['conversation']) for r in result['conversations']], [('A','z'),('source','b')])
        self.assertEqual(result['total'],6)
        self.assertEqual(result['unordered_conversations'],1)
        self.assertEqual(conversations(self.db, order='recent',offset=100)['conversations'],[])
        scoped=conversations(self.db,source='A',order='recent')
        self.assertEqual(scoped['total'],1)
        self.assertEqual(scoped['timestamp_interpretation']['parsed_iso'],1)

    def test_invalid_options_precede_database_access(self):
        missing=self.home/'absent.sqlite'
        for args in (dict(order='binary'),dict(order=True),dict(from_date='2026-02-30'),
                     dict(until_date='2026-1-01'),dict(from_date='2026-02-01',until_date='2026-01-31')):
            with self.subTest(args=args), patch('recaplib.conversation_view.readonly') as read:
                with self.assertRaises(ValueError): conversations(missing,**args)
                read.assert_not_called()
        self.assertFalse(missing.exists())

    def test_read_only_and_original_timestamp_bytes(self):
        before=self.db.read_bytes()
        with closing(sqlite3.connect(self.db)) as conn:
            stored=conn.execute('SELECT timestamp,source_sha256,source_line FROM messages ORDER BY message_pk').fetchall()
        conversations(self.db,order='recent',from_date='2026-01-01')
        self.assertEqual(self.db.read_bytes(),before)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute('SELECT timestamp,source_sha256,source_line FROM messages ORDER BY message_pk').fetchall(),stored)

    def test_titles_only_looked_up_for_page(self):
        titles(self.db,'source','b','local title',0)
        queries=[]
        def traced(db):
            conn=readonly(db);conn.set_trace_callback(queries.append);return conn
        with patch('recaplib.conversation_view.readonly',traced):
            result=conversations(self.db,order='recent',limit=1,offset=1)
        self.assertEqual(result['conversations'][0]['display_title'],'local title')
        self.assertEqual(sum(q.startswith('SELECT title FROM messages') for q in queries),1)
        self.assertEqual(sum(q.startswith('SELECT title,id FROM title_history') for q in queries),1)

    def test_empty_source_and_empty_archive(self):
        result=conversations(self.db,source='absent',order='recent')
        self.assertEqual(result['total'],0);self.assertEqual(result['unordered_conversations'],0)
        self.assertEqual(result['timestamp_interpretation']['unparsed'],0)
        empty=self.home/'empty.sqlite';ingest_bytes(empty,'empty',b'')
        self.assertEqual(conversations(empty,from_date='2026-01-01')['total'],0)

    def test_epoch_and_iso_order_share_one_scale(self):
        self.load('epochs',[('x','0'),('y','20260101'),('z','1970-01-01T00:00:00.000001Z')])
        result=conversations(self.db,source='epochs',order='oldest')
        self.assertEqual(self.ids(result),['x','z','y'])
        self.assertEqual(result['timestamp_interpretation']['parsed_epoch_seconds'],2)

    def test_cli_parity(self):
        common=['--db',str(self.db),'list','--order','recent','--from','2026-01-01','--until','2026-02-01','--limit','2','--offset','1']
        values=[]
        for script in ('recap.py','conversation_view.py'):
            result=subprocess.run([sys.executable,str(ROOT/script),*common],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);values.append(json.loads(result.stdout))
        self.assertEqual(*values)

    def test_guide_executes_with_native_paths_after_tokenization(self):
        checkout=self.home/'checkout with spaces';shutil.copytree(ROOT,checkout,ignore=shutil.ignore_patterns('.git','__pycache__'))
        output=self.home/'output with spaces'
        blocks=re.findall(r'```sh\n(.*?)```',(checkout/'docs/BROWSE_BY_TIME.md').read_text(),re.S)
        self.assertEqual(len(blocks),1);lines=blocks[0].strip().splitlines();self.assertEqual(len(lines),5)
        sample=checkout/'examples/time-sample.jsonl';before=sample.read_bytes();results=[]
        for line in lines:
            self.assertNotIn('>',line)
            args=shlex.split(line)
            args=[str(output) if t=='OUTPUT' else str(output/t[7:]) if t.startswith('OUTPUT/') else t for t in args]
            if args[0]=='mkdir':Path(args[1]).mkdir();continue
            result=subprocess.run([sys.executable,*args[1:]],cwd=checkout,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);results.append(json.loads(result.stdout))
        self.assertEqual(results[1]['order'],'recent');self.assertEqual(results[2]['from_date'],'2026-01-01')
        self.assertEqual(self.ids(results[1]),['later','epoch','offset','digit-date','unparsed'])
        self.assertEqual(self.ids(results[2]),['epoch','later'])
        self.assertEqual(self.ids(results[3]),['offset','epoch'])
        self.assertEqual(results[3]['order'],'oldest');self.assertEqual(sample.read_bytes(),before)

    def test_snapshot_survives_concurrent_append_before_title_lookup(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
        appended=[]
        def traced(db):
            conn=readonly(db)
            def trace(sql):
                if sql.startswith('SELECT title FROM messages') and not appended:
                    appended.append(True)
                    self.load('source',[('new','2030-01-01T00:00:00Z')])
            conn.set_trace_callback(trace)
            return conn
        with patch('recaplib.conversation_view.readonly',traced):
            result=conversations(self.db,order='recent')
        self.assertEqual(appended,[True])
        self.assertEqual(result['total'],5)
        self.assertEqual(self.ids(result),['a','b','c','e','d'])
        self.assertEqual(conversations(self.db,order='recent')['total'],6)

    def test_year_boundary_windows(self):
        self.load('extremes',[('first','0001-01-01T00:00:00Z'),('last','9999-12-31T23:59:59.999999Z')])
        self.assertEqual(self.ids(conversations(self.db,source='extremes',from_date='9999-12-31',until_date='9999-12-31')),['last'])
        self.assertEqual(self.ids(conversations(self.db,source='extremes',until_date='0001-01-01')),['first'])
