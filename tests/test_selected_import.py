"""Explicit conversation selection never indexes unrelated synthetic text."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from recaplib.conversation_view import conversation, conversations
from recaplib.session_workflow import import_export, inspect_export, normalize
from recaplib.branch_title import suggest_branch
from recaplib.title_proposal import preview, apply_preview
from recaplib.title_plan import make_plan, check_plan


class SelectedImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'export.json'; self.db = Path(self.tmp.name)/'archive.sqlite'
        self.records = json.loads(Path('examples/web-export.json').read_text())
        other = json.loads(json.dumps(self.records[0])); other['id'] = 'other-chat'; other['title'] = 'Unselected title'
        other['mapping']['m1']['message']['content']['parts'] = ['UNSELECTED SYNTHETIC BODY']
        self.records.append(other); self.write()

    def write(self): self.path.write_text(json.dumps(self.records), encoding='utf-8')

    def test_selected_inspect_import_and_title_end_to_end(self):
        raw = self.path.read_bytes()
        report = inspect_export(self.path, 'web', 'synthetic-chat')
        self.assertEqual(report['extracted_messages'], 4)
        self.assertEqual(report['selection']['selected_messages'], 2)
        self.assertEqual(report['selection']['excluded_messages'], 2)
        self.assertNotIn('UNSELECTED', json.dumps(report)); self.assertFalse(self.db.exists())
        receipt = import_export(self.db, 'web', self.path, 'web', 'synthetic-chat')
        self.assertEqual(receipt['inserted'], 2)
        rows = conversations(self.db)['conversations']; self.assertEqual(len(rows), 1)
        archive = conversation(self.db, 'web', 'synthetic-chat')
        self.assertNotIn('UNSELECTED', json.dumps(archive))
        for message in archive['messages']:
            self.assertEqual(message['export_provenance'][0]['original_sha256'], hashlib.sha256(raw).hexdigest())
        proposal = suggest_branch(self.db, 'web', 'synthetic-chat', self.path, 'm2')
        apply_preview(self.db, preview(self.db, proposal))
        plan = make_plan(self.db, 'web', 'synthetic-chat', self.path, 'web')
        self.assertTrue(check_plan(self.db, self.path, plan)['valid'])
        self.assertEqual(self.path.read_bytes(), raw)

    def test_unknown_empty_ambiguous_or_invalid_unselected_input_no_db_write(self):
        for selected in ('missing', ''):
            with self.assertRaises(ValueError): import_export(self.db, 'web', self.path, 'web', selected)
            self.assertFalse(self.db.exists())
        self.records[1]['mapping'] = {}; self.write()
        with self.assertRaisesRegex(ValueError, 'no extracted messages'):
            import_export(self.db, 'web', self.path, 'web', 'other-chat')
        self.records.append(self.records[0]); self.write()
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            import_export(self.db, 'web', self.path, 'web', 'synthetic-chat')
        self.records.pop(); self.records[1]['mapping'] = {'bad': {'parent':'missing'}}; self.write()
        with self.assertRaisesRegex(ValueError, 'parent'):
            import_export(self.db, 'web', self.path, 'web', 'synthetic-chat')
        self.assertFalse(self.db.exists())

    def test_selected_rows_keep_all_branches_and_read_file_once(self):
        extra = json.loads(json.dumps(self.records[0]['mapping']['m2']))
        extra['message']['content']['parts'] = ['Alternate synthetic answer']
        self.records[0]['mapping']['alternate'] = extra; self.write()
        reader = Path.read_bytes; calls = []
        def track(path):
            if path == self.path: calls.append(path)
            return reader(path)
        with patch.object(Path, 'read_bytes', track):
            rows, report = normalize(self.path, 'web', True, 'synthetic-chat')
        self.assertEqual(len(calls), 1); self.assertEqual(len(rows), 3)
        self.assertEqual(report['selection']['selected_messages'], 3)
        self.assertTrue(any('all branches' in x for x in report['warnings']))

    def test_default_import_and_later_selected_import_are_compatible(self):
        first = import_export(self.db, 'web', self.path, 'web', 'synthetic-chat')
        self.assertEqual(first['inserted'], 2)
        second = import_export(self.db, 'web', self.path, 'web', 'other-chat')
        self.assertEqual(second['inserted'], 2)
        self.assertEqual(len(conversations(self.db)['conversations']), 2)
        repeat = import_export(self.db, 'web', self.path, 'web')
        self.assertEqual(repeat['inserted'], 0); self.assertNotIn('selection', repeat['coverage'])
        before = self.db.read_bytes()
        with self.assertRaises(ValueError): import_export(self.db, 'web', self.path, 'web', 'missing')
        self.assertEqual(before, self.db.read_bytes())

    def test_local_profiles_select_session_without_remapping_line_ids(self):
        records = [dict(type='session_meta',payload=dict(id='one')),
                   dict(type='response_item',payload=dict(type='message',role='user',content=[dict(type='input_text',text='One synthetic topic')])),
                   dict(type='session_meta',payload=dict(id='two')),
                   dict(type='response_item',payload=dict(type='message',role='user',content=[dict(type='input_text',text='Two synthetic topic')]))]
        self.path.write_text(''.join(json.dumps(r)+'\n' for r in records))
        for kind in ('local', 'local-codex'):
            rows, report = normalize(self.path, kind, True, 'two')
            self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['origin_locator'], 'line:4')
            self.assertEqual(rows[0]['message_id'], 'export.json:4')
            self.assertEqual(report['selection']['excluded_messages'], 1)
            import_export(self.db, kind, self.path, kind, 'two')
            self.assertEqual(len(conversations(self.db, kind)['conversations']), 1)

    def test_both_cli_inspection_and_import_equivalence(self):
        def call(script, *args):
            result = subprocess.run([sys.executable, script, *map(str,args)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode,0,result.stderr); return json.loads(result.stdout)
        args = ('inspect', self.path, '--format','web','--conversation','synthetic-chat')
        self.assertEqual(call('recap.py', *args),call('session_workflow.py',*args))
        receipt = call('recap.py','--db',self.db,'import',self.path,'--format','web','--source','web','--conversation','synthetic-chat')
        self.assertEqual(receipt['inserted'],2)
        repeat = call('session_workflow.py','--db',self.db,'import',self.path,'--format','web','--source','web','--conversation','synthetic-chat')
        self.assertEqual(repeat['inserted'],0); self.assertEqual(receipt['coverage'],repeat['coverage'])
        proposal = call('recap.py','--db',self.db,'suggest-branch-title',self.path,'--source','web','--conversation','synthetic-chat','--node','m2')
        saved = Path(self.tmp.name)/'review.json'; saved.write_text(json.dumps(proposal))
        reviewed = call('recap.py','--db',self.db,'preview-title',saved); saved.write_text(json.dumps(reviewed))
        call('recap.py','--db',self.db,'apply-title',saved)
        self.assertEqual(call('recap.py','--db',self.db,'find','UNSELECTED')['total_matches'],0)
        self.assertEqual(call('recap.py','--db',self.db,'list')['total'],1)

    def test_unicode_selection_ascii_stdout(self):
        self.records[0]['id'] = '합성 대화'; self.write()
        for script in ('recap.py', 'session_workflow.py'):
            result = subprocess.run([sys.executable,script,'inspect',str(self.path),'--format','web','--conversation','합성 대화'],
                                    capture_output=True,text=True,env=dict(os.environ,PYTHONIOENCODING='ascii'),timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['selection']['conversation'],'합성 대화')
