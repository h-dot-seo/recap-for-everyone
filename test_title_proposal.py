import tempfile
import unittest
from pathlib import Path
from session_workflow import import_export, titles
from title_proposal import snapshot, preview, apply_preview


class ProposalTests(unittest.TestCase):
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
