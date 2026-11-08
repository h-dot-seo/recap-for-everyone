"""Synthetic branch-to-archive matching and checked title application."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from recaplib.branch_title import suggest_branch
from recaplib.session_workflow import import_export, titles
from recaplib.title_proposal import preview, apply_preview, snapshot


def fixture():
    def message(parent, text):
        return dict(parent=parent, message=dict(author=dict(role='user'), create_time=1,
                                               content=dict(parts=[text])))
    return [dict(id='synthetic', title='Original', current_node='active', mapping={
        'old': message('root', 'Abandoned peach plan'),
        'active': message('root', 'Selected orchard plan'), 'root': dict(parent=None)})]


class BranchTitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'web.json'; self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.data = fixture(); self.write(); import_export(self.db, 'web', self.path, 'web')

    def write(self):
        self.path.write_text(json.dumps(self.data), encoding='utf-8')

    def suggest(self, node=None):
        return suggest_branch(self.db, 'web', 'synthetic', self.path, node)

    def test_active_and_alternate_proposals_match_whole_archive_snapshot(self):
        before = self.db.read_bytes(); original = self.path.read_bytes()
        active = self.suggest(); alternate = self.suggest('old')
        self.assertEqual(active['title'], 'Selected orchard plan')
        self.assertEqual(alternate['title'], 'Abandoned peach plan')
        self.assertEqual(active['evidence_message_ids'], ['active'])
        self.assertEqual(active['content_sha256'], snapshot(self.db, 'web', 'synthetic')[1])
        self.assertEqual(active['content_sha256'], alternate['content_sha256'])
        self.assertEqual(active['branch_context']['node_ids'], ['root', 'active'])
        self.assertEqual(self.db.read_bytes(), before); self.assertEqual(self.path.read_bytes(), original)

    def test_same_content_from_unimported_export_bytes_is_rejected(self):
        self.path.write_text(json.dumps(self.data, indent=2))
        with self.assertRaisesRegex(ValueError, 'provenance'): self.suggest()
        import_export(self.db, 'web', self.path, 'web')
        self.assertEqual(self.suggest()['title'], 'Selected orchard plan')

    def test_wrong_content_timestamp_parent_and_missing_text_rejected(self):
        for mutation in ('role', 'text', 'timestamp', 'parent', 'missing'):
            with self.subTest(mutation=mutation), closing(sqlite3.connect(self.db)) as c:
                c.execute('BEGIN')
                if mutation == 'role': c.execute("UPDATE messages SET role='assistant' WHERE message_id='active'")
                elif mutation == 'text': c.execute("UPDATE messages SET text='different' WHERE message_id='active'")
                elif mutation == 'timestamp': c.execute("UPDATE messages SET timestamp='different' WHERE message_id='active'")
                elif mutation == 'parent':
                    c.execute("UPDATE export_provenance SET parent='different' WHERE message='active'")
                    c.execute("UPDATE export_occurrences SET parent='different' WHERE message='active'")
                else: c.execute("DELETE FROM messages WHERE message_id='active'")
                c.commit()
                with self.assertRaises(ValueError): self.suggest()
            # Rebuild only this synthetic fixture for the next independent mutation.
            self.db.unlink(); import_export(self.db, 'web', self.path, 'web')

    def test_legacy_provenance_works_and_provenance_free_archive_is_rejected(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('DROP TABLE export_occurrences'); c.commit()
        self.assertEqual(self.suggest()['title'], 'Selected orchard plan')
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('DROP TABLE export_provenance'); c.commit()
        with self.assertRaisesRegex(ValueError, 'provenance'): self.suggest()

    def test_title_revision_and_off_branch_content_changes_reject_stale_apply(self):
        reviewed = preview(self.db, self.suggest())
        changed = titles(self.db, 'web', 'synthetic', 'Reviewed other', expected_revision=0)
        with self.assertRaises(ValueError): apply_preview(self.db, reviewed)
        reviewed = preview(self.db, self.suggest())
        self.data[0]['mapping']['new-old'] = dict(parent='old', message=dict(author=dict(role='assistant'),
                                                      content=dict(parts=['New alternate continuation'])))
        self.write(); import_export(self.db, 'web', self.path, 'web')
        with self.assertRaisesRegex(ValueError, 'snapshot'): apply_preview(self.db, reviewed)
        self.assertEqual(titles(self.db, 'web', 'synthetic')['revision'], changed['revision'])

    def test_root_without_user_evidence_and_missing_db_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no usable user'): self.suggest('root')
        missing = Path(self.tmp.name) / 'missing.sqlite'
        with self.assertRaises(sqlite3.Error): suggest_branch(missing, 'web', 'synthetic', self.path)
        self.assertFalse(missing.exists())

    def test_cli_generate_review_apply_find_and_restore(self):
        def call(script, *args, success=True):
            r = subprocess.run([sys.executable, script, *map(str, args)], capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode == 0, success, r.stderr); self.assertNotIn('Traceback', r.stderr)
            return json.loads(r.stdout) if success else r.stderr
        identity = ('--source', 'web', '--conversation', 'synthetic')
        proposal = call('recap.py', '--db', self.db, 'suggest-branch-title', self.path, *identity)
        self.assertEqual(proposal, call('branch_title.py', '--db', self.db, *identity, self.path))
        path = Path(self.tmp.name) / 'proposal.json'; path.write_text(json.dumps(proposal))
        reviewed = call('title_proposal.py', '--db', self.db, 'preview', path)
        path.write_text(json.dumps(reviewed)); changed = call('title_proposal.py', '--db', self.db, 'apply', path)
        call('title_proposal.py', '--db', self.db, 'apply', path, success=False)
        self.assertEqual(call('recap.py', '--db', self.db, 'find', 'selected orchard')['total_matches'], 1)
        shown = call('recap.py', '--db', self.db, 'show', *identity)
        self.assertEqual(len(shown['messages']), 2)
        call('recap.py', '--db', self.db, 'title', *identity, '--set', 'Original', '--expected-revision', changed['revision'])
