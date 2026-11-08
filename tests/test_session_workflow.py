import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from recaplib.session_workflow import import_export, normalize, titles
from recap import search

class WorkflowTests(unittest.TestCase):
    def test_both_sources_titles_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp)/'test.sqlite')
            self.assertEqual(import_export(db,'web','examples/web-export.json','web')['inserted'],2)
            self.assertEqual(import_export(db,'web','examples/web-export.json','web')['inserted'],0)
            self.assertEqual(import_export(db,'local','examples/local-session.jsonl','local')['inserted'],1)
            self.assertEqual(len(search(db,'orchard')),2)
            preview=titles(db,'web','synthetic-chat')
            self.assertIn('orchard',preview['suggested_title'])
            titles(db,'web','synthetic-chat','Orchard experiment plan')
            self.assertEqual(titles(db,'web','synthetic-chat')['display_title'],'Orchard experiment plan')
            titles(db,'web','synthetic-chat',preview['original_title'])
            self.assertEqual(titles(db,'web','synthetic-chat')['display_title'],'New chat')
            with closing(sqlite3.connect(db)) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM export_provenance').fetchone()[0],3)
                self.assertEqual(c.execute("SELECT parent FROM export_provenance WHERE message='m2'").fetchone()[0],'m1')
            with self.assertRaises(ValueError): titles(db,'web','missing','new')
            with self.assertRaises(ValueError): titles(db,'web','synthetic-chat',' ')

    def test_unsupported_format(self):
        with self.assertRaises(ValueError): normalize('examples/web-export.json','unknown')

    def test_stale_preview_and_atomic_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp)/'test.sqlite')
            import_export(db,'web','examples/web-export.json','web')
            preview = titles(db,'web','synthetic-chat')
            changed = titles(db,'web','synthetic-chat','Reviewed plan',preview['revision'])
            with self.assertRaises(ValueError):
                titles(db,'web','synthetic-chat','Stale plan',preview['revision'])
            self.assertEqual(titles(db,'web','synthetic-chat')['revision'],changed['revision'])
            with closing(sqlite3.connect(db)) as c, c:
                c.execute("CREATE TRIGGER reject_provenance BEFORE INSERT ON export_provenance BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                import_export(db,'other','examples/web-export.json','web')
            with closing(sqlite3.connect(db)) as c:
                self.assertEqual(c.execute("SELECT count(*) FROM messages WHERE source_id='other'").fetchone()[0],0)
                self.assertEqual(c.execute("SELECT count(*) FROM artifacts WHERE source_id='other'").fetchone()[0],0)
