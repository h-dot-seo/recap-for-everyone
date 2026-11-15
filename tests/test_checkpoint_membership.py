"""Opt-in saved identity membership, not authentication or complete provenance."""
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from recaplib import archive as a,import_checkpoint as cp

class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'db.sqlite';self.out=self.root/'cp.json'
        self.rows=[dict(conversation_id=c,message_id='m',role='user',timestamp='synthetic',title='original',text='private '+c) for c in ('a','b')]
        self.raw=('\n'.join(json.dumps(x) for x in self.rows)+'\n').encode()
        a.ingest_bytes(self.db,'source',self.raw,conversation='a')
    def declare(self):
        receipt=cp.declare_checkpoint(self.db,'source',self.out,checkpoint_version=2)
        return receipt,cp.load_checkpoint(self.out,'source')
    def sql(self,sql,args=()):
        with closing(sqlite3.connect(self.db)) as c,c:c.execute(sql,args)
    def test_same_artifact_addition_and_explicit_schema_family(self):
        before=self.db.read_bytes();receipt,saved=self.declare();self.assertEqual(before,self.db.read_bytes())
        self.assertEqual(receipt['schema'],'recap.import-checkpoint-declaration.v2')
        self.assertEqual(saved['schema'],'recap.import-checkpoint.v2');self.assertEqual(len(saved['identity_sha256s']),1)
        self.assertNotIn('private a',self.out.read_text(encoding='utf-8'))
        a.ingest_bytes(self.db,'source',self.raw,conversation='b');delta=self.root/'delta.json'
        before=self.db.read_bytes();result=cp.changed_since(self.db,'source',saved,delta_output=delta)
        self.assertEqual(result['schema'],'recap.import-changes.v2');self.assertEqual(result['checkpoint_schema'],saved['schema'])
        self.assertEqual(result['delta'],dict(new_conversations=1,has_new_identities=0,no_new_identities=1,accepted_after_cutoff_messages=1))
        document=json.loads(delta.read_bytes());self.assertEqual(document['schema'],'recap.import-changes-delta.v2')
        self.assertEqual(document['checkpoint_schema'],saved['schema']);self.assertEqual(document['samples']['new_conversations'],['b'])
        self.assertEqual(before,self.db.read_bytes())
    def test_default_v1_still_rejects_same_artifact_addition(self):
        cp.declare_checkpoint(self.db,'source',self.out)
        a.ingest_bytes(self.db,'source',self.raw,conversation='b')
        result=cp.changed_since(self.db,'source',self.out)
        self.assertEqual(result['schema'],'recap.import-changes.v1');self.assertEqual(result['status'],'CUTOFF_NOT_VERIFIED')
        self.assertNotIn('checkpoint_schema',result);self.assertIsNone(result['delta'])
    def test_old_fields_mutation_and_deletion_fail_closed(self):
        _,saved=self.declare();original=self.db.read_bytes()
        for field,value in [('text','changed'),('role','assistant'),('timestamp','changed'),('title','changed'),('source_line',99),('source_sha256','f'*64),('conversation_id','other'),('message_id','other')]:
            with self.subTest(field=field):
                self.db.write_bytes(original);self.sql('UPDATE messages SET '+field+'=?',(value,))
                out=self.root/'never.json';r=cp.changed_since(self.db,'source',saved,delta_output=out)
                self.assertEqual(r['status'],'CUTOFF_NOT_VERIFIED');self.assertIsNone(r['delta']);self.assertFalse(out.exists())
        self.db.write_bytes(original);self.sql('DELETE FROM messages');self.assertIsNone(cp.changed_since(self.db,'source',saved)['delta'])
    def test_rowid_change_and_local_history_are_not_identity(self):
        _,saved=self.declare();self.sql('UPDATE messages SET message_pk=message_pk+100')
        self.sql('CREATE TABLE unrelated_history(note TEXT)');self.sql("INSERT INTO unrelated_history VALUES ('outside scope')")
        self.assertEqual(cp.changed_since(self.db,'source',saved)['status'],'CUTOFF_VERIFIED')
    def test_strict_membership_validation(self):
        _,saved=self.declare()
        variants=[]
        for key,val in [('identity_sha256s',[saved['identity_sha256s'][0]]*2),('identity_sha256s',['F'*64]),('identity_sha256s',[True]),('identity_sha256s',[]),('identity_sha256s',['0'*64+'\n']),('accepted_messages',True),('membership_semantics','other'),('schema','recap.import-checkpoint.v3')]:
            d=copy.deepcopy(saved);d[key]=val;variants.append(d)
        d=copy.deepcopy(saved);d['extra']=None;variants.append(d)
        for value in variants:
            with self.subTest(value=value),self.assertRaises(ValueError):cp.validate_checkpoint(value,'source')
        for version in (True,False,None,0,3,2.0,'2'):
            with patch.object(cp,'readonly',side_effect=AssertionError('no DB')),self.assertRaises(ValueError):cp.declare_checkpoint(self.db,'source',self.root/'never',checkpoint_version=version)
    def test_hash_collision_is_not_silently_merged(self):
        a.ingest_bytes(self.db,'source',self.raw,conversation='b')
        with patch.object(cp,'_identity_sha256',return_value='0'*64),self.assertRaises(ValueError):self.declare()
        self.assertFalse(self.out.exists())
        self.sql("DELETE FROM messages WHERE conversation_id='b'")
        with patch.object(cp,'_identity_sha256',return_value='0'*64):_,saved=self.declare()
        a.ingest_bytes(self.db,'source',self.raw,conversation='b')
        with patch.object(cp,'_identity_sha256',return_value='0'*64):self.assertIsNone(cp.changed_since(self.db,'source',saved)['delta'])
    def test_empty_and_new_source_identity_namespace(self):
        receipt=cp.declare_checkpoint(self.db,'empty',self.out,checkpoint_version=2);saved=cp.load_checkpoint(self.out)
        self.assertEqual(saved['identity_sha256s'],[])
        a.ingest_bytes(self.db,'empty',self.raw,conversation='a')
        self.assertEqual(cp.changed_since(self.db,'empty',saved)['delta']['new_conversations'],1)
        with self.assertRaises(ValueError):cp.changed_since(self.db,'source',saved)
    def test_unicode_exact_no_normalization(self):
        tokens=[cp._identity_sha256('s',x,'m') for x in ('é','e\u0301','A','a',' a')]
        self.assertEqual(len(set(tokens)),5)
        self.assertEqual(tokens[0],hashlib.sha256(cp._canonical_line(['s','é','m'])).hexdigest())
    def test_budget_and_exclusive_outputs_preserve_archive(self):
        before=self.db.read_bytes()
        with patch.object(cp,'MAX_CHECKPOINT_BYTES',10),self.assertRaises(ValueError):self.declare()
        self.assertFalse(self.out.exists());self.assertEqual(before,self.db.read_bytes())
        _,saved=self.declare();raw=self.out.read_bytes()
        with self.assertRaises(FileExistsError):self.declare()
        self.assertEqual(raw,self.out.read_bytes())
        out=self.root/'delta.json';out.write_bytes(b'other')
        with self.assertRaises(FileExistsError):cp.changed_since(self.db,'source',saved,delta_output=out)
        self.assertEqual(out.read_bytes(),b'other');self.assertEqual(before,self.db.read_bytes())
    def test_late_delta_collision_and_connections_closed(self):
        _,saved=self.declare();real=cp.readonly;connections=[];publish=cp._publish_new_file
        def opened(*args):c=real(*args);connections.append(c);return c
        def race(path,raw,prefix):Path(path).write_bytes(b'other');return publish(path,raw,prefix)
        out=self.root/'delta.json'
        with patch.object(cp,'readonly',side_effect=opened),patch.object(cp,'_publish_new_file',side_effect=race),self.assertRaises(FileExistsError):cp.changed_since(self.db,'source',saved,delta_output=out)
        for c in connections:
            with self.assertRaises(sqlite3.ProgrammingError):c.execute('SELECT 1')
        self.assertEqual(out.read_bytes(),b'other');self.assertFalse(list(self.root.glob('.recap-*')))
    def test_published_guide_and_cli_schemas(self):
        import re,shlex,subprocess,sys
        root=Path(__file__).resolve().parents[1];out=self.root/'guide with spaces';out.mkdir()
        source=root/'examples/time-sample.jsonl';original=source.read_bytes()
        blocks=re.findall(r'```sh\n(.*?)```',(root/'docs/MEMBERSHIP_CHECKPOINT.md').read_text(encoding='utf-8'),re.S)
        self.assertEqual(len(blocks),1);results=[]
        for line in blocks[0].strip().splitlines():
            args=[x.replace('OUTPUT',str(out)) for x in shlex.split(line)];args[0]=sys.executable
            p=subprocess.run(args,cwd=root,capture_output=True,timeout=30)
            self.assertEqual(p.returncode,0,(args,p.stderr));results.append(json.loads(p.stdout))
        self.assertEqual(results[1]['schema'],'recap.import-checkpoint-declaration.v2')
        self.assertEqual(results[-1]['schema'],'recap.import-changes.v2')
        self.assertEqual(results[-1]['delta']['accepted_after_cutoff_messages'],2)
        self.assertEqual(source.read_bytes(),original)
    def test_exact_serialized_budget_and_unsorted_membership(self):
        a.ingest_bytes(self.db,'source',self.raw,conversation='b');_,saved=self.declare()
        raw=self.out.read_bytes()
        with patch.object(cp,'MAX_CHECKPOINT_BYTES',len(raw)):
            self.assertEqual(cp.load_checkpoint(self.out),saved)
            cp.declare_checkpoint(self.db,'source',self.root/'exact.json',checkpoint_version=2)
        with patch.object(cp,'MAX_CHECKPOINT_BYTES',len(raw)-1),self.assertRaises(ValueError):cp.load_checkpoint(self.out)
        bad=copy.deepcopy(saved);bad['identity_sha256s'].reverse()
        with self.assertRaises(ValueError):cp.validate_checkpoint(bad)
    def test_artifact_metadata_and_missing_identity_no_delta(self):
        _,saved=self.declare();self.sql('UPDATE artifacts SET record_count=record_count+1')
        self.assertIsNone(cp.changed_since(self.db,'source',saved)['delta'])
    def test_v2_parser_failure_precedes_database_and_stdout_failure_keeps_file(self):
        import sys,recap
        _,saved=self.declare();bad=self.root/'bad.json';bad.write_bytes(b'{"schema":"recap.import-checkpoint.v2","schema":null}')
        with patch.object(cp,'readonly',side_effect=AssertionError('no DB')),self.assertRaises(ValueError):cp.changed_since(self.db,'source',bad)
        out=self.root/'saved.json';before=self.db.read_bytes()
        args=['recap','--db',str(self.db),'changed-since','--source','source','--checkpoint',str(self.out),'--delta-output',str(out)]
        with patch.object(sys,'argv',args),patch('builtins.print',side_effect=BrokenPipeError('synthetic closed pipe')):
            with self.assertRaises(BrokenPipeError):recap.main()
        self.assertEqual(json.loads(out.read_bytes())['schema'],'recap.import-changes-delta.v2');self.assertEqual(before,self.db.read_bytes())
