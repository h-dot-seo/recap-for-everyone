import json
import tempfile
import unittest
from pathlib import Path
from recap import ingest, readonly, search
from recaplib.local_parser import parse_artifact, LocalImportError


class RecapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'test.sqlite'
        self.input = self.root / 'input.jsonl'
        self.row = dict(conversation_id='demo', message_id='one', role='user',
                        timestamp='2026-01-01T00:00:00Z', text='Synthetic orchard question')

    def write(self, rows):
        self.input.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')

    def test_repeat_and_provenance(self):
        self.write([self.row])
        receipt = ingest(self.db, 'demo', self.input)
        self.assertEqual(ingest(self.db, 'demo', self.input)['inserted'], 0)
        hit = search(self.db, 'orchard')[0]
        self.assertEqual(hit['source_sha256'], receipt['source_sha256'])
        self.assertEqual(hit['source_line'], 1)
        self.assertEqual(search(self.db, 'no-match'), [])

    def test_conflict_rolls_back_batch(self):
        self.write([self.row]); ingest(self.db, 'demo', self.input)
        self.write([{**self.row, 'message_id':'two'}, {**self.row, 'text':'conflict'}])
        with self.assertRaises(ValueError):
            ingest(self.db, 'demo', self.input)
        c = readonly(self.db)
        self.assertEqual(c.execute('SELECT count(*) FROM messages').fetchone()[0], 1)
        self.assertEqual(c.execute('SELECT count(*) FROM artifacts').fetchone()[0], 1)
        with self.assertRaises(Exception):
            c.execute('DELETE FROM messages')
        c.close()

    def test_invalid_input_no_import(self):
        self.write([{**self.row, 'role':'invalid'}])
        with self.assertRaises(ValueError):
            ingest(self.db, 'demo', self.input)
        self.assertFalse(self.db.exists())

    def test_normalized_session_parser_preserves_locator(self):
        content = 'Synthetic text with a Unicode separator\u2028inside a JSON string'
        self.write([{'type':'session_meta','payload':{'id':'synthetic-session'}},
                    {'type':'response_item','timestamp':'2026-01-01T00:00:00Z',
                     'payload':{'type':'message','role':'user','id':'synthetic-message',
                                'content':[{'text':content}]}}])
        result = parse_artifact(self.input, 'sessions/demo.jsonl')
        self.assertEqual(result.messages[0].text, content)
        self.assertEqual(result.messages[0].line_number, 2)
        self.assertEqual(result.sessions[0].session_id, 'synthetic-session')

    def test_parser_requires_session_identity(self):
        self.write([{'type':'response_item','payload':{'type':'message','role':'user',
                                                     'content':[{'text':'Synthetic'}]}}])
        with self.assertRaises(LocalImportError):
            parse_artifact(self.input, 'sessions/demo.jsonl')


if __name__ == '__main__':
    unittest.main()
