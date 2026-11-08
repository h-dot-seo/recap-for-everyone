"""Search explicit original-export provenance without mixing unrelated bodies."""
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from recap import ingest
from recaplib.session_workflow import import_export,titles
from recaplib.conversation_search import find
from tests.test_title_queue_workflow import synthetic_exports


class ExportScopedSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name);self.db=self.directory/'archive.sqlite'
        self.web,self.local=synthetic_exports(self.directory)
        import_export(self.db,'demo',self.web,'web');import_export(self.db,'demo',self.local,'local-codex')
        self.web_hash=hashlib.sha256(self.web.read_bytes()).hexdigest()
        self.local_hash=hashlib.sha256(self.local.read_bytes()).hexdigest()

    def test_twenty_four_conversations_separate_by_original_export(self):
        before=self.db.read_bytes()
        self.assertEqual(find(self.db,'synthetic')['total_matches'],23)
        web=find(self.db,'synthetic',export_sha256=self.web_hash)
        local=find(self.db,'synthetic',export_sha256=self.local_hash)
        self.assertEqual(web['total_matches'],12);self.assertEqual(local['total_matches'],11)
        self.assertTrue(all(row['conversation_id'].startswith('web-') for row in web['matches']))
        for item in web['matches']:
            for match in item['message_matches']:
                self.assertTrue(all(p['original_sha256']==self.web_hash for p in match['export_provenance']))
                self.assertNotEqual(match['source_sha256'],self.web_hash)
        self.assertEqual(before,self.db.read_bytes())

    def test_same_conversation_excludes_unlinked_body_but_uses_archive_title(self):
        first=self.directory/'first.json';second=self.directory/'second.json'
        for path,node,text,title in [(first,'a','Firstneedle','Archive title'),(second,'b','Secondneedle','Different export title')]:
            path.write_text(json.dumps([dict(id='split',title=title,mapping={node:dict(parent=None,message=dict(author=dict(role='user'),content=dict(parts=[text])))})]))
            import_export(self.db,'demo',path,'web')
        digest=hashlib.sha256(second.read_bytes()).hexdigest()
        self.assertEqual(find(self.db,'firstneedle',export_sha256=digest)['total_matches'],0)
        hit=find(self.db,'secondneedle',export_sha256=digest)['matches'][0]
        self.assertEqual(hit['message_count'],1);self.assertEqual(hit['display_title'],'Archive title')
        self.assertEqual(hit['original_title'],'Archive title')
        self.assertEqual(find(self.db,'archive',export_sha256=digest)['total_matches'],1)
        self.assertEqual(find(self.db,'firstneedle secondneedle',export_sha256=digest)['total_matches'],0)
        titles(self.db,'demo','split','Pastlabel',0)
        revision=titles(self.db,'demo','split')['revision'];titles(self.db,'demo','split','Currentlabel',revision)
        self.assertEqual(find(self.db,'pastlabel',export_sha256=digest)['total_matches'],0)
        self.assertEqual(find(self.db,'pastlabel',include_title_history=True,export_sha256=digest)['total_matches'],1)

    def test_occurrence_union_samples_and_legacy_only_compatibility(self):
        path=self.directory/'repeated.jsonl'
        record=dict(type='response_item',payload=dict(type='message',id='same',role='user',content=[dict(type='input_text',text='Repeatedneedle')]))
        path.write_text(json.dumps(dict(type='session_meta',payload=dict(id='repeat')))+'\n'+(json.dumps(record)+'\n')*5)
        import_export(self.db,'repeat',path,'local-codex');digest=hashlib.sha256(path.read_bytes()).hexdigest()
        hit=find(self.db,'repeatedneedle',export_sha256=digest)['matches'][0]['message_matches'][0]
        self.assertEqual(hit['export_provenance_count'],5);self.assertEqual(len(hit['export_provenance']),3)
        self.assertTrue(hit['export_provenance_truncated'])
        with closing(sqlite3.connect(self.db)) as c:c.execute("DELETE FROM export_provenance WHERE source='repeat'");c.commit()
        self.assertEqual(find(self.db,'repeatedneedle',export_sha256=digest)['total_matches'],1)
        import_export(self.db,'repeat',path,'local-codex')
        with closing(sqlite3.connect(self.db)) as c:c.execute('DROP TABLE export_occurrences');c.commit()
        self.assertEqual(find(self.db,'repeatedneedle',export_sha256=digest)['matches'][0]['message_matches'][0]['export_provenance_count'],1)

    def test_normalized_artifact_hash_is_not_silently_treated_as_export_hash(self):
        db=self.directory/'normalized.sqlite';path=self.directory/'normalized.jsonl'
        path.write_text(json.dumps(dict(conversation_id='raw',message_id='u',role='user',timestamp='synthetic',text='Normalizedneedle'))+'\n')
        ingest(db,'raw',path);digest=hashlib.sha256(path.read_bytes()).hexdigest()
        result=find(db,'normalizedneedle',export_sha256=digest)
        self.assertEqual(result['total_matches'],0);self.assertFalse(result['export_provenance_available'])
        self.assertEqual(find(db,'normalizedneedle')['total_matches'],1)

    def test_source_scope_unknown_hash_and_validation_before_db(self):
        from recaplib import conversation_search
        import_export(self.db,'other',self.web,'web')
        self.assertEqual(find(self.db,'synthetic',source='other',export_sha256=self.web_hash)['total_matches'],12)
        self.assertEqual(find(self.db,'synthetic',source='other',export_sha256=self.local_hash)['total_matches'],0)
        self.assertEqual(find(self.db,'synthetic',export_sha256='0'*64)['total_matches'],0)
        with patch.object(conversation_search,'readonly',side_effect=AssertionError('must validate first')):
            for value in ('bad','A'*64,True,[],0):
                with self.assertRaises(ValueError):find(self.db,'synthetic',export_sha256=value)

    def test_provenance_and_messages_share_snapshot_during_concurrent_change(self):
        from recaplib import conversation_search
        with closing(sqlite3.connect(self.db)) as c:c.execute('PRAGMA journal_mode=WAL')
        original=conversation_search.readonly;changed=[]
        def read_with_trace(path):
            connection=original(path)
            def trace(sql):
                if sql.startswith('SELECT * FROM messages') and not changed:
                    changed.append(True)
                    with closing(sqlite3.connect(self.db)) as writer:
                        for table in ('export_provenance','export_occurrences'):
                            writer.execute(f'DELETE FROM {table} WHERE original_hash=?',(self.web_hash,))
                        writer.commit()
            connection.set_trace_callback(trace);return connection
        with patch.object(conversation_search,'readonly',read_with_trace):result=find(self.db,'synthetic',export_sha256=self.web_hash)
        self.assertTrue(changed);self.assertEqual(result['total_matches'],12)
        self.assertTrue(result['matches'][0]['message_matches'][0]['export_provenance'])
        self.assertEqual(find(self.db,'synthetic',export_sha256=self.web_hash)['total_matches'],0)

    def test_cli_inspect_hash_then_scoped_search_after_title_change(self):
        def call(script,*args):
            result=subprocess.run([sys.executable,script,*map(str,args)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
        report=call('recap.py','inspect',self.web,'--format','web')
        digest=report['original_sha256'];self.assertEqual(digest,self.web_hash)
        current=call('recap.py','--db',self.db,'title','--source','demo','--conversation','web-05')
        call('recap.py','--db',self.db,'title','--source','demo','--conversation','web-05','--set','Exportlookup label','--expected-revision',current['revision'])
        before=self.db.read_bytes()
        result=call('recap.py','--db',self.db,'find','exportlookup','--source','demo','--export-sha256',digest)
        self.assertEqual(result,call('conversation_search.py','--db',self.db,'exportlookup','--source','demo','--export-sha256',digest))
        self.assertEqual(result['total_matches'],1)
        self.assertEqual(call('recap.py','--db',self.db,'find','exportlookup','--export-sha256',self.local_hash)['total_matches'],0)
        self.assertEqual(before,self.db.read_bytes())
