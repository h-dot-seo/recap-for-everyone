import tempfile
import json
import subprocess
import sys
import unittest
from pathlib import Path
from session_workflow import import_export, titles
from title_proposal import snapshot, preview, apply_preview


class ProposalTests(unittest.TestCase):
    def test_invalid_review_revision_cannot_bypass_stale_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'test.sqlite'
            import_export(db, 'demo', 'examples/web-export.json', 'web')
            _, digest = snapshot(db, 'demo', 'synthetic-chat')
            proposal = dict(source='demo', conversation='synthetic-chat', content_sha256=digest,
                            title='Old synthetic suggestion', provider='synthetic-mock', evidence_message_ids=['m1'])
            reviewed = preview(db, proposal)
            changed = titles(db, 'demo', 'synthetic-chat', 'Newer reviewed title', 0)
            before = db.read_bytes()
            for revision in (None, True, False, '0', 0.0, -1):
                with self.subTest(revision=revision), self.assertRaises(ValueError):
                    apply_preview(db, dict(reviewed, expected_revision=revision))
            with self.assertRaises(ValueError):
                apply_preview(db, {'proposal': proposal})
            with self.assertRaises(ValueError):
                apply_preview(db, None)
            self.assertEqual(titles(db, 'demo', 'synthetic-chat')['revision'], changed['revision'])
            self.assertEqual(db.read_bytes(), before)

    def test_null_revision_and_missing_db_are_clean_cli_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'missing.sqlite'
            path = Path(tmp) / 'reviewed.json'
            path.write_text(json.dumps({'expected_revision': None, 'proposal': {}}), encoding='utf-8')
            commands = [('apply', str(path)), ('snapshot', '--source', 'demo', '--conversation', 'synthetic')]
            for args in commands:
                result = subprocess.run([sys.executable, 'title_proposal.py', '--db', str(db), *args],
                                        capture_output=True, text=True, timeout=20)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('Traceback', result.stderr)
                self.assertFalse(db.exists())

    def test_review_apply_and_stale_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=str(Path(tmp)/'test.sqlite')
            import_export(db,'demo','examples/web-export.json','web')
            _,digest=snapshot(db,'demo','synthetic-chat')
            p=dict(source='demo',conversation='synthetic-chat',content_sha256=digest,
                   title='Orchard experiment design',provider='synthetic-mock',evidence_message_ids=['m1'])
            reviewed=preview(db,p)
            self.assertEqual(titles(db,'demo','synthetic-chat')['revision'],0)
            self.assertEqual(reviewed,preview(db,p))
            self.assertEqual(apply_preview(db,reviewed)['display_title'],p['title'])
            with self.assertRaises(ValueError): apply_preview(db,reviewed)
            p['evidence_message_ids']=['m2']
            with self.assertRaises(ValueError): preview(db,p)
            p['evidence_message_ids']=['m1']; p['content_sha256']='wrong'
            with self.assertRaises(ValueError): preview(db,p)

    def test_fingerprint_checked_under_write_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=str(Path(tmp)/'test.sqlite')
            import_export(db,'demo','examples/web-export.json','web')
            with self.assertRaises(ValueError):
                titles(db,'demo','synthetic-chat','new',0,'incorrect')
            self.assertEqual(titles(db,'demo','synthetic-chat')['revision'],0)
