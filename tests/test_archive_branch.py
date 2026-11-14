"""Synthetic archived topology: exact source paths, never live UI reconstruction."""
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recaplib.conversation_view import conversation
from recaplib.session_workflow import import_export, import_export_bytes, normalize
from recaplib.web_branch import branch_view
from tests.test_web_branch import fixture


class ArchiveBranchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root / 'archive.sqlite'
        self.path = self.root / 'synthetic.json'; self.data = fixture(); self.write()

    def write(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')

    def ingest(self, **kwargs):
        return import_export(self.db, 'demo', self.path, 'web', **kwargs)

    def view(self, **kwargs):
        return conversation(self.db, 'demo', 'synthetic', branch=True, **kwargs)

    def topology(self):
        with closing(sqlite3.connect(self.db)) as c:
            return {table: c.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()
                    for table in ('export_nodes', 'export_conversations')}

    def assert_parity(self, node=None):
        expected = branch_view(self.path, 'synthetic', node)
        result = self.view(node=node)
        selected = result['selection']
        for key in ('node_ids', 'selected_nodes', 'selected_nodes_without_text',
                    'excluded_nodes', 'forks', 'continuations', 'selected_node_is_leaf'):
            self.assertEqual(selected[key], expected[key], key)
        self.assertEqual(selected['endpoint'], expected['selected_node'])
        self.assertEqual(selected['export_sha256'], expected['original_sha256'])
        self.assertEqual([m['message_id'] for m in result['messages']],
                         [m['message_id'] for m in expected['messages']])
        self.assertEqual([m['text'] for m in result['messages']],
                         [m['text'] for m in expected['messages']])
        self.assertEqual(result['message_count'], len(normalize(self.path, 'web')))
        return result

    def test_current_alternate_interior_root_and_textless_tip_parity(self):
        self.ingest(); original = self.db.read_bytes()
        for node in (None, 'old', 'question', 'root'):
            with self.subTest(node=node): self.assert_parity(node)
        self.assertEqual(self.db.read_bytes(), original)
        self.data[0]['mapping']['tip'] = dict(parent='active', message=None)
        self.data[0]['current_node'] = 'tip'; self.write()
        self.db = self.root/'tip.sqlite'; self.ingest()
        self.assertEqual(self.assert_parity()['selection']['selected_nodes_without_text'], 2)

    def test_mapping_order_survives_vacuum_without_lexical_sorting(self):
        mapping = self.data[0]['mapping']
        mapping['z-first'] = dict(parent='question', message=None)
        mapping['a-last'] = dict(parent='question', message=None)
        self.write(); self.ingest(); self.assert_parity('question')
        with closing(sqlite3.connect(self.db)) as c: c.execute('VACUUM')
        self.assert_parity('question')

    def test_invalid_and_absent_pointers_preserve_import_and_explicit_path(self):
        for i, value in enumerate((None, '', [], 5, 'missing')):
            with self.subTest(pointer=value):
                self.db = self.root/('pointer%d.sqlite'%i)
                self.data[0]['current_node'] = value; self.write(); self.ingest()
                with self.assertRaises(ValueError): self.view()
                self.assert_parity('old')
        del self.data[0]['current_node']; self.write(); self.db=self.root/'absent.sqlite'; self.ingest()
        with self.assertRaises(ValueError): self.view()
        self.assert_parity('old')

    def test_multiple_exports_require_exact_explicit_hash(self):
        self.ingest(); first = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.data[0]['current_node'] = 'old'; self.write(); self.ingest()
        second = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaises(ValueError): self.view()
        self.assertEqual(self.view(export_sha256=first)['selection']['endpoint'], 'active')
        self.assertEqual(self.view(export_sha256=second)['selection']['endpoint'], 'old')
        for invalid in ('0'*64, first.upper(), 'bad'):
            with self.assertRaises(ValueError): self.view(export_sha256=invalid)

    def test_legacy_readonly_then_same_original_reimport_fills_only_topology(self):
        self.ingest(); default = conversation(self.db, 'demo', 'synthetic')
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('DROP TABLE export_nodes'); c.execute('DROP TABLE export_conversations')
        legacy = self.db.read_bytes()
        self.assertEqual(conversation(self.db, 'demo', 'synthetic'), default)
        with self.assertRaises(ValueError): self.view()
        self.assertEqual(self.db.read_bytes(), legacy)
        self.assertEqual(self.ingest()['inserted'], 0)
        self.assertEqual(conversation(self.db, 'demo', 'synthetic'), default)
        self.assert_parity()
        before = self.topology(); self.ingest(); self.assertEqual(self.topology(), before)

    def test_selected_import_does_not_store_other_node_ids(self):
        other = copy.deepcopy(self.data[0]); other['id']='excluded'
        other['mapping']={'PRIVATE_EXCLUDED_NODE': dict(parent=None, message=dict(
            author=dict(role='user'), content=dict(parts=['Synthetic excluded content'])))}
        other['current_node']='PRIVATE_EXCLUDED_NODE'; self.data.append(other); self.write()
        self.ingest(conversation='synthetic')
        self.assertNotIn('PRIVATE_EXCLUDED_NODE', repr(self.topology()))
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute('SELECT DISTINCT conversation FROM export_nodes').fetchall(), [('synthetic',)])

    def test_one_source_read_no_normalized_rows_or_coverage_change(self):
        before = self.path.read_bytes(); expected_rows, expected_report = normalize(self.path, 'web', True)
        reader=Path.read_bytes; calls=[]
        def read(path):
            calls.append(path); return reader(path)
        with patch.object(Path,'read_bytes', read): result=self.ingest()
        self.assertEqual(calls,[self.path]); self.assertEqual(result['coverage'],expected_report)
        self.assertEqual(normalize(self.path,'web'),expected_rows); self.assertEqual(self.path.read_bytes(),before)
        replay=self.root/'replay.sqlite'
        import_export_bytes(replay,'demo',before,None,'web',newline='crlf' if os.linesep=='\r\n' else 'lf')
        saved=self.topology(); self.db=replay; self.assertEqual(self.topology(),saved)

    def test_duplicate_conversations_remain_importable_but_never_guessed(self):
        self.data.append(copy.deepcopy(self.data[0])); self.write(); self.ingest()
        for node in (None,'old'):
            with self.assertRaises(ValueError): self.view(node=node)

    def test_topology_insert_failure_rolls_back_all_import_rows(self):
        self.ingest()
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("CREATE TRIGGER reject_topology BEFORE INSERT ON export_nodes BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        before=self.db.read_bytes()
        with self.assertRaises(sqlite3.Error): import_export(self.db,'new',self.path,'web')
        self.assertEqual(self.db.read_bytes(),before)

    def test_long_path_uses_iterative_graph_walk(self):
        mapping={str(i):dict(parent=str(i-1) if i else None, message=None) for i in range(4000)}
        mapping['3999']['message']=dict(author=dict(role='tool'),content=dict(parts=['Synthetic tip']))
        self.data[0]['mapping']=mapping; self.data[0]['current_node']='3999'; self.write(); self.ingest()
        self.assertEqual(self.view()['selection']['selected_nodes'],4000)

    def test_both_cli_entrypoints_ascii_and_default_output_parity(self):
        self.data[0]['mapping']['active']['message']['content']['parts']=['합성 🌱']; self.write(); self.ingest()
        results=[]
        for prefix in (['recap.py','--db',str(self.db)],['conversation_view.py','--db',str(self.db)]):
            args=[sys.executable,*prefix,'show','--source','demo','--conversation','synthetic']
            plain=subprocess.run(args,capture_output=True,timeout=20)
            self.assertEqual(plain.returncode,0,plain.stderr)
            self.assertEqual(json.loads(plain.stdout),conversation(self.db,'demo','synthetic'))
            run=subprocess.run([*args,'--branch'],capture_output=True,timeout=20,env=dict(os.environ,PYTHONIOENCODING='ascii'))
            self.assertEqual(run.returncode,0,run.stderr); run.stdout.decode('ascii'); results.append(json.loads(run.stdout))
            for option in (['--message','active'],['--limit','1'],['--offset','1'],['--around-message','active']):
                bad=subprocess.run([*args,'--branch',*option],capture_output=True,timeout=20)
                self.assertNotEqual(bad.returncode,0); self.assertNotIn(b'Traceback',bad.stderr)
        self.assertEqual(results[0],results[1])

    def test_published_synthetic_guide_commands(self):
        import re
        import shlex
        blocks=re.findall(r'```sh\n(.*?)```',Path('docs/ARCHIVE_BRANCH.md').read_text(),re.S)
        self.assertEqual(len(blocks),1)
        output=self.root/'guide'; output.mkdir()
        results=[]
        for line in blocks[0].strip().splitlines():
            args=shlex.split(line); self.assertEqual(args.pop(0),'python')
            args=[part.replace('OUTPUT',str(output)) for part in args]
            result=subprocess.run([sys.executable,*args],capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr); results.append(json.loads(result.stdout))
        self.assertEqual(results[1]['selection']['node_ids'],['m1','m2'])
        self.assertEqual(results[1]['selection']['endpoint_basis'],'explicit node')

    def test_recovery_v1_does_not_claim_topology_preservation(self):
        from recaplib.recovery import declare_recovery, rehearse_recovery
        self.ingest(); manifest=self.root/'manifest.json'; receipt=self.root/'receipt.json'
        declare_recovery(self.db,manifest,declared_at='2026-11-14')
        original=json.loads(manifest.read_text())
        self.assertEqual(original['schema'],'recap.recovery-manifest.v1')
        restored=self.root/'restored.sqlite'; restored.write_bytes(self.db.read_bytes())
        with closing(sqlite3.connect(restored)) as c, c:
            c.execute('DROP TABLE export_nodes'); c.execute('DROP TABLE export_conversations')
        result=rehearse_recovery(manifest,restored,receipt)
        self.assertEqual(result['status'],'RECOVERY_REHEARSAL_PASSED')
        self.db=restored
        with self.assertRaises(ValueError): self.view()

    def test_corrupt_or_partial_topology_never_returns_a_guessed_path(self):
        self.ingest(); original=self.db.read_bytes()
        statements=("DELETE FROM export_nodes WHERE node='root'",
                    "UPDATE export_nodes SET parent='active' WHERE node='root'",
                    "UPDATE export_nodes SET ordinal=0 WHERE node='question'",
                    "UPDATE export_conversations SET mapping_nodes=mapping_nodes+1",
                    "UPDATE export_conversations SET current_node_state='ambiguous'",
                    "UPDATE export_conversations SET current_node='absent' WHERE current_node_state='valid'")
        for statement in statements:
            with self.subTest(statement=statement):
                self.db.write_bytes(original)
                with closing(sqlite3.connect(self.db)) as c, c: c.execute(statement)
                before=self.db.read_bytes()
                with self.assertRaises(ValueError): self.view()
                self.assertEqual(self.db.read_bytes(),before)

    def test_legacy_failure_rolls_back_new_topology_tables(self):
        self.ingest()
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('DROP TABLE export_nodes');c.execute('DROP TABLE export_conversations')
            c.execute("CREATE TRIGGER reject_message BEFORE INSERT ON messages BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        before=self.db.read_bytes()
        with self.assertRaises(sqlite3.Error): import_export(self.db,'new',self.path,'web')
        self.assertEqual(self.db.read_bytes(),before)

    def test_selected_export_text_membership_detects_missing_and_extra_occurrences(self):
        self.ingest(); original=self.db.read_bytes()
        mutations=("DELETE FROM {table} WHERE message='active'",
                   "UPDATE {table} SET parent='old' WHERE message='active'")
        for mutation in mutations:
            self.db.write_bytes(original)
            with closing(sqlite3.connect(self.db)) as c, c:
                for table in ('export_provenance','export_occurrences'): c.execute(mutation.format(table=table))
            with self.assertRaises(ValueError): self.view()
        self.db.write_bytes(original)
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("UPDATE export_nodes SET has_text=0 WHERE node='active'")
        with self.assertRaises(ValueError): self.view()

    def test_same_node_textless_in_other_export_is_not_false_missing(self):
        self.ingest(); first=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.data[0]['mapping']['active']['message']=None; self.write(); self.ingest()
        second=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertEqual([m['message_id'] for m in self.view(export_sha256=first)['messages']],['question','active'])
        result=self.view(export_sha256=second)
        self.assertEqual([m['message_id'] for m in result['messages']],['question'])
        self.assertEqual(result['selection']['selected_nodes_without_text'],2)

    def test_conflicting_existing_table_is_not_dropped_or_rewritten(self):
        from recaplib.archive import ingest
        ingest(self.db,'other',Path('examples/conversations.jsonl'))
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('CREATE TABLE export_nodes (synthetic_existing TEXT)')
            c.execute("INSERT INTO export_nodes VALUES('keep this synthetic row')")
        before=self.db.read_bytes()
        with self.assertRaises(sqlite3.Error): self.ingest()
        self.assertEqual(self.db.read_bytes(),before)
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute('SELECT * FROM export_nodes').fetchall(),[('keep this synthetic row',)])

    def test_selected_export_rejects_unexpected_locators_and_unknown_nodes(self):
        self.ingest(); original=self.db.read_bytes()
        digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        for message,locator,parent in (('active','mapping:WRONG','question'),
                                        ('UNKNOWN','mapping:UNKNOWN',None),
                                        ('root','mapping:root',None)):
            self.db.write_bytes(original)
            with closing(sqlite3.connect(self.db)) as c,c:
                c.execute('INSERT INTO export_occurrences VALUES(?,?,?,?,?,?)',
                          ('demo','synthetic',message,digest,locator,parent))
            with self.assertRaises(ValueError): self.view()
