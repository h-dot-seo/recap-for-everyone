"""Synthetic per-source counts: stored identities, not import/activity totals."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from recaplib.archive import ingest_bytes, SCHEMA
from recaplib.time_stats import stats_by_source
from recaplib.timestamps import RULE

ROOT = Path(__file__).resolve().parents[1]


class TimeStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'archive.sqlite'
        with closing(sqlite3.connect(self.db)) as c:
            c.executescript(SCHEMA)

    def load(self, source, times):
        data=''.join(json.dumps(dict(conversation_id=cid,message_id=str(i),role='user',
            timestamp=t,title='synthetic',text='invented'))+'\n' for i,(cid,t) in enumerate(times)).encode()
        ingest_bytes(self.db,source,data)
        return data

    def test_empty_archive(self):
        result=stats_by_source(self.db)
        self.assertEqual((result['messages'],result['artifacts'],result['sources']),(0,0,[]))
        self.assertEqual(result['timestamp_interpretation']['rule'],RULE)

    def test_counts_offsets_epoch_and_unparsed(self):
        self.load('z',[('same','2026-01-01T09:00:00+09:00'),('same','1767225600.123456789'),
                       ('other','unknown'),('other','2026-01-01T00:00:00')])
        result=stats_by_source(self.db); row=result['sources'][0]
        self.assertEqual((row['conversations'],row['messages']), (2,4))
        self.assertEqual((row['parsed_iso'],row['parsed_epoch_seconds'],row['unparsed']),(1,1,2))
        self.assertEqual(row['first_parsed_utc'],'2026-01-01T00:00:00.000000Z')
        self.assertEqual(row['last_parsed_utc'],'2026-01-01T00:00:00.123456Z')
        self.assertEqual(result['messages'],4)

    def test_binary_sources_and_case_sensitive_conversation_ids(self):
        for source in ['z','a','A','é']:
            self.load(source,[('id','unknown'),('ID','unknown')])
        rows=stats_by_source(self.db)['sources']
        self.assertEqual([r['source'] for r in rows],['A','a','z','é'])
        self.assertTrue(all(r['conversations']==2 and r['first_parsed_utc'] is None and r['last_parsed_utc'] is None for r in rows))

    def test_artifact_only_source_and_duplicate_import(self):
        self.load('empty',[])
        data=self.load('rows',[('c','0')]); ingest_bytes(self.db,'rows',data)
        result=stats_by_source(self.db)
        self.assertEqual((result['messages'],result['artifacts']),(1,2))
        row=result['sources'][0]
        self.assertEqual(row,dict(source='empty',conversations=0,messages=0,first_parsed_utc=None,
                                 last_parsed_utc=None,parsed_iso=0,parsed_epoch_seconds=0,unparsed=0))

    def test_numeric_policy_extremes_and_missing_message_source_artifact(self):
        self.load('numeric',[('c','20260101'),('c','9999-12-31T23:59:59.999999999Z')])
        # Legacy/incomplete archive inspection does not silently omit message sources.
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('DELETE FROM artifacts')
        result=stats_by_source(self.db);row=result['sources'][0]
        self.assertEqual(result['artifacts'],0)
        self.assertEqual(row['first_parsed_utc'],'1970-08-23T11:48:21.000000Z')
        self.assertEqual(row['last_parsed_utc'],'9999-12-31T23:59:59.999999Z')
        self.assertIn('date-looking',result['timestamp_interpretation']['numeric_policy'])

    def test_cli_default_unchanged_and_read_only(self):
        self.load('s',[('c','unknown')]);before=self.db.read_bytes()
        def cli(*flags):
            result=subprocess.run([sys.executable,str(ROOT/'recap.py'),'--db',str(self.db),'stats',*flags],capture_output=True,text=True,check=True)
            return json.loads(result.stdout)
        self.assertEqual(cli(),{'messages':1,'artifacts':1})
        self.assertEqual(cli('--by-source'),stats_by_source(self.db))
        self.assertEqual(before,self.db.read_bytes())

    def test_missing_database_is_not_created(self):
        missing=Path(self.temp.name)/'missing.sqlite'
        with self.assertRaises(sqlite3.OperationalError): stats_by_source(missing)
        self.assertFalse(missing.exists())

    def test_counts_and_rows_share_one_snapshot(self):
        from unittest.mock import patch
        from recaplib.archive import readonly
        self.load('s',[('c','0')])
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('PRAGMA journal_mode=WAL')
        reader=readonly(self.db)
        class Interleaved:
            def __getattr__(self,name): return getattr(reader,name)
            def execute(proxy,sql,*args):
                result=reader.execute(sql,*args)
                if sql=='SELECT COUNT(*) FROM messages':
                    with closing(sqlite3.connect(self.db)) as writer,writer:
                        writer.execute("INSERT INTO artifacts VALUES('later',?,0,0)",('a'*64,))
                return result
        with patch('recaplib.time_stats.readonly',return_value=Interleaved()):
            result=stats_by_source(self.db)
        self.assertEqual(result['artifacts'],1)
        self.assertEqual([r['source'] for r in result['sources']],['s'])
        self.assertEqual(stats_by_source(self.db)['artifacts'],2)
