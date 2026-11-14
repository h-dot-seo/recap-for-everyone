"""Synthetic title-write transaction and read-only query-plan compatibility."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from recaplib.archive import ingest_bytes
from recaplib import session_workflow as workflow, title_history, recovery

TABLE='CREATE TABLE title_history (id INTEGER PRIMARY KEY, source TEXT, conversation TEXT, previous TEXT, title TEXT, changed_at TEXT DEFAULT CURRENT_TIMESTAMP)'
INDEX='CREATE INDEX title_history_identity ON title_history(source,conversation,id)'


class TitleHistoryIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'archive.sqlite'
        self.source="synthetic' OR 1=1 --";self.conversation='한글/%_identity'
        raw=(json.dumps(dict(conversation_id=self.conversation,message_id='m',role='user',timestamp='synthetic',text='Fictional orchard',title='Original'))+'\n').encode()
        ingest_bytes(self.db,self.source,raw)

    def schema(self):
        with closing(sqlite3.connect(self.db)) as connection:
            return connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name').fetchall()

    def legacy(self):
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute(TABLE)
                connection.executemany('INSERT INTO title_history(id,source,conversation,previous,title,changed_at) VALUES(?,?,?,?,?,?)',[
                    (2,self.source,self.conversation,None,'Earlier',None),
                    (17,self.source,self.conversation,'Earlier',None,'synthetic'),
                    (18,'other',self.conversation,'x','Other',None),
                    (24,None,None,None,None,None)])

    def test_first_write_creates_exact_index_without_schema_version_change(self):
        before=self.schema()
        with closing(sqlite3.connect(self.db)) as connection:version=connection.execute('PRAGMA user_version').fetchone()
        value=workflow.titles(self.db,self.source,self.conversation,'Chosen',0)
        self.assertEqual(value['revision'],1)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('PRAGMA index_info(title_history_identity)').fetchall(),[(0,1,'source'),(1,2,'conversation'),(2,0,'id')])
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone(),version)
            self.assertEqual(connection.execute('SELECT count(*) FROM title_history').fetchone()[0],1)
        self.assertEqual({r[1] for r in self.schema()}-{r[1] for r in before},{'title_history','title_history_identity'})

    def test_legacy_reads_no_index_then_explicit_write_installs(self):
        self.legacy();before=self.db.read_bytes()
        self.assertIsNone(workflow.titles(self.db,self.source,self.conversation)['display_title'])
        self.assertIsNone(title_history.history(self.db,self.source,self.conversation)['display_title'])
        self.assertEqual(self.db.read_bytes(),before)
        self.assertNotIn('title_history_identity',{r[1] for r in self.schema()})
        result=workflow.titles(self.db,self.source,self.conversation,'Next',17)
        self.assertEqual(result['revision'],25)
        self.assertIn('title_history_identity',{r[1] for r in self.schema()})

    def test_nullable_partial_history_and_logical_digest_unchanged_by_index(self):
        self.legacy()
        def values():
            with closing(sqlite3.connect(self.db)) as connection:
                logical=recovery._title_history(connection,recovery._tables(connection))
            return workflow.titles(self.db,self.source,self.conversation),title_history.history(self.db,self.source,self.conversation,limit=1,offset=1),logical
        before=values()
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:connection.execute(INDEX)
        self.assertEqual(values(),before)

    def test_actual_reader_queries_use_identity_index(self):
        workflow.titles(self.db,self.source,self.conversation,'Chosen',0)
        queries=[];original=title_history.readonly
        def traced(db):
            connection=original(db);connection.set_trace_callback(queries.append);return connection
        with patch.object(title_history,'readonly',side_effect=traced):title_history.history(self.db,self.source,self.conversation)
        with patch.object(workflow,'readonly',side_effect=traced):workflow.titles(self.db,self.source,self.conversation)
        selected=[sql for sql in queries if 'FROM title_history WHERE' in sql]
        self.assertEqual(len(selected),4)
        with closing(sqlite3.connect(self.db)) as connection:
            for sql in selected:
                plan=connection.execute('EXPLAIN QUERY PLAN '+sql).fetchall()
                self.assertIn('title_history_identity',' '.join(row[3] for row in plan))

    def test_stale_or_unknown_guards_leave_database_bytes_unchanged(self):
        for legacy in (False,True):
            if legacy:self.legacy()
            before=self.db.read_bytes()
            with self.assertRaises(ValueError):workflow.titles(self.db,self.source,self.conversation,'Chosen',99)
            with self.assertRaises(ValueError):workflow.titles(self.db,self.source,'missing','Chosen',0)
            self.assertEqual(before,self.db.read_bytes())
            self.assertNotIn('title_history_identity',{r[1] for r in self.schema()})

    def test_index_or_insert_failure_rolls_back_and_closes(self):
        real=sqlite3.connect
        for denied in ('index','insert'):
            before=self.db.read_bytes();connections=[]
            class Tracked(sqlite3.Connection):
                closed=False
                def close(self):self.closed=True;super().close()
            def connect(*args,**kwargs):
                connection=real(*args,**kwargs,factory=Tracked);connections.append(connection)
                def authorize(action,arg1,arg2,db,trigger):
                    if denied=='index' and action==sqlite3.SQLITE_CREATE_INDEX:return sqlite3.SQLITE_DENY
                    if denied=='insert' and action==sqlite3.SQLITE_INSERT and arg1=='title_history':return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                connection.set_authorizer(authorize);return connection
            with patch.object(workflow.sqlite3,'connect',side_effect=connect),self.assertRaises(sqlite3.DatabaseError):
                workflow.titles(self.db,self.source,self.conversation,'Chosen',0)
            self.assertTrue(connections);self.assertTrue(all(c.closed for c in connections))
            self.assertEqual(before,self.db.read_bytes())
            self.assertNotIn('title_history',{r[1] for r in self.schema()})

    def test_legacy_insert_failure_rolls_back_new_index(self):
        self.legacy();before=self.db.read_bytes();real=sqlite3.connect
        def connect(*args,**kwargs):
            connection=real(*args,**kwargs)
            connection.set_authorizer(lambda action,a,b,db,trigger:
                sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_INSERT and a=='title_history' else sqlite3.SQLITE_OK)
            return connection
        with patch.object(workflow.sqlite3,'connect',side_effect=connect),self.assertRaises(sqlite3.DatabaseError):
            workflow.titles(self.db,self.source,self.conversation,'Next',17)
        self.assertEqual(before,self.db.read_bytes())
        self.assertNotIn('title_history_identity',{r[1] for r in self.schema()})

    def test_same_name_wrong_definition_or_other_table_is_not_replaced(self):
        for other_table in (False,True):
            with self.subTest(other_table=other_table):
                # Separate synthetic archive for each conflicting index definition.
                db=Path(self.temp.name)/('other'+str(other_table)+'.sqlite')
                db.write_bytes(self.db.read_bytes())
                with closing(sqlite3.connect(db)) as connection:
                    with connection:
                        connection.execute(TABLE)
                        sql='CREATE INDEX title_history_identity ON '+('messages(title)' if other_table else 'title_history(title)')
                        connection.execute(sql)
                workflow.titles(db,self.source,self.conversation,'Chosen',0)
                with closing(sqlite3.connect(db)) as connection:
                    self.assertEqual(connection.execute("SELECT sql FROM sqlite_master WHERE name='title_history_identity'").fetchone()[0],sql)
                    self.assertEqual(connection.execute('SELECT count(*) FROM title_history').fetchone()[0],1)


if __name__=='__main__':unittest.main()
