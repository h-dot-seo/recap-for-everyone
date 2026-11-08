"""Synthetic metadata-only manual plans, with no remote execution path."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from session_workflow import import_export, titles
from title_plan import make_plan, check_plan


class TitlePlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.path = Path(self.tmp.name) / 'web.json'
        self.path.write_bytes(Path('examples/web-export.json').read_bytes())
        import_export(self.db, 'web', self.path, 'web')

    def renamed(self, title='Reviewed fruit title'):
        current = titles(self.db, 'web', 'synthetic-chat')
        return titles(self.db, 'web', 'synthetic-chat', title, current['revision'])

    def plan(self):
        return make_plan(self.db, 'web', 'synthetic-chat', self.path, 'web')

    def test_requires_explicit_local_title_then_metadata_only_readonly_plan(self):
        with self.assertRaisesRegex(ValueError, 'local display title'): self.plan()
        self.renamed(); before = self.db.read_bytes(); raw = self.path.read_bytes()
        plan = self.plan()
        self.assertEqual(plan['action'], 'manual_rename')
        self.assertEqual(plan['execution_status'], 'NOT_EXECUTED')
        self.assertFalse(plan['includes_message_records']); self.assertFalse(plan['remote_mutation'])
        self.assertNotIn('Design a synthetic orchard experiment', json.dumps(plan))
        self.assertNotIn('messages', plan)
        self.assertTrue(check_plan(self.db, self.path, plan)['valid'])
        self.assertEqual(self.db.read_bytes(), before); self.assertEqual(self.path.read_bytes(), raw)

    def test_revision_change_even_same_title_rejects_stale_plan(self):
        self.renamed(); plan = self.plan(); self.renamed()
        with self.assertRaisesRegex(ValueError, 'stale'): check_plan(self.db, self.path, plan)

    def test_export_byte_change_rejected_even_after_reimport(self):
        self.renamed(); plan = self.plan()
        self.path.write_bytes(self.path.read_bytes() + b'\n')
        with self.assertRaises(ValueError): check_plan(self.db, self.path, plan)
        import_export(self.db, 'web', self.path, 'web')
        with self.assertRaisesRegex(ValueError, 'stale'): check_plan(self.db, self.path, plan)

    def test_content_addition_invalidates_old_plan(self):
        self.renamed(); plan = self.plan(); data = json.loads(self.path.read_text())
        data[0]['mapping']['extra'] = dict(parent='m1', message=dict(author=dict(role='user'), content=dict(parts=['New synthetic text'])))
        self.path.write_text(json.dumps(data)); import_export(self.db, 'web', self.path, 'web')
        with self.assertRaises(ValueError): check_plan(self.db, self.path, plan)

    def test_tampered_fields_types_and_extra_fields_rejected(self):
        self.renamed(); plan = self.plan()
        for field, value in [('proposed_title', 'Changed'), ('remote_mutation', 0),
                             ('expected_revision', True), ('expected_revision', float(plan['expected_revision'])),
                             ('extra', 'hidden')]:
            with self.subTest(field=field, value=value):
                bad = dict(plan); bad[field] = value
                with self.assertRaises(ValueError): check_plan(self.db, self.path, bad)
        for bad in (None, [], {}, {'schema': 'future'}):
            with self.assertRaises(ValueError): check_plan(self.db, self.path, bad)

    def test_restored_title_is_no_change_against_archive_original_only(self):
        self.renamed('New chat'); plan = self.plan()
        self.assertEqual(plan['action'], 'no_change')
        self.assertEqual(plan['proposed_title'], plan['original_title'])

    def test_local_session_plan_and_cli_equivalence(self):
        path = Path(self.tmp.name) / 'local.jsonl'; path.write_bytes(Path('examples/local-session.jsonl').read_bytes())
        import_export(self.db, 'local', path, 'local')
        titles(self.db, 'local', 'synthetic-local', 'Reviewed local plan', 0)
        def call(script, *args, success=True):
            r = subprocess.run([sys.executable, script, *map(str, args)], capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode == 0, success, r.stderr); self.assertNotIn('Traceback', r.stderr)
            return json.loads(r.stdout) if success else r.stderr
        identity = ('--source', 'local', '--conversation', 'synthetic-local', '--format', 'local')
        plan = call('recap.py', '--db', self.db, 'export-title-plan', path, *identity)
        self.assertEqual(plan, call('title_plan.py', '--db', self.db, 'export', path, *identity))
        saved = Path(self.tmp.name) / 'plan.json'; saved.write_text(json.dumps(plan))
        self.assertEqual(call('recap.py', '--db', self.db, 'check-title-plan', path, saved),
                         call('title_plan.py', '--db', self.db, 'check', path, saved))
        saved.write_text('{"schema":"one","schema":"two"}')
        call('recap.py', '--db', self.db, 'check-title-plan', path, saved, success=False)
