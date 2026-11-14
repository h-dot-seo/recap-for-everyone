"""Synthetic private metadata cards, never publication citations."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from recaplib import message_provenance as cards
from recaplib.archive import ingest_bytes
from recaplib.conversation_view import conversation
from recaplib.session_workflow import titles


class MessageProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'archive.sqlite'
        self.output = self.root / 'private-card.json'
        self.source, self.conversation, self.message = 'PRIVATE_SOURCE', '대화 PRIVATE_CONVERSATION', '😀PRIVATE_MESSAGE'
        self.text, self.title = 'PRIVATE_BODY 한국어 😀', 'PRIVATE_TITLE'
        raw = (json.dumps(dict(conversation_id=self.conversation, message_id=self.message, role='user',
                              timestamp='2026-11-14', text=self.text, title=self.title), ensure_ascii=False) + '\n').encode()
        ingest_bytes(self.db, self.source, raw)

    def sql(self, statement, params=()):
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(statement, params)
            connection.commit()
        finally:
            connection.close()

    def export(self, output=None):
        receipt = cards.export_provenance(self.db,self.source,self.conversation,self.message,output or self.output,'2026-11-14')
        return receipt, cards.load_card(output or self.output)

    def ledger(self, table='export_occurrences', locator='line:1', parent=None):
        self.sql('CREATE TABLE IF NOT EXISTS ' + table + ' (source TEXT,conversation TEXT,message TEXT,original_hash TEXT,locator TEXT,parent TEXT)')
        self.sql('INSERT INTO '+table+' VALUES(?,?,?,?,?,?)',(self.source,self.conversation,self.message,'a'*64,locator,parent))

    def test_show_parity_deterministic_private_receipt_readonly(self):
        self.ledger(); self.ledger('export_provenance')
        before = self.db.read_bytes()
        receipt, card = self.export()
        second=self.root/'second.json'; other,_=self.export(second)
        self.assertEqual(receipt,other)
        self.assertEqual(self.output.read_bytes(),second.read_bytes())
        self.assertEqual(before,self.db.read_bytes())
        shown=conversation(self.db,self.source,self.conversation,message_id=self.message)['messages'][0]
        for key in ('role','timestamp','source_sha256','source_line','export_provenance'):
            self.assertEqual(card[key],shown[key])
        self.assertEqual(len(card['export_provenance']),1)
        self.assertEqual(card['text_sha256'],hashlib.sha256(self.text.encode()).hexdigest())
        self.assertEqual(card['text_utf8_bytes'],len(self.text.encode()))
        self.assertEqual(cards.check_provenance(self.db,card)['status'],'PASS')
        for value in (self.source,self.conversation,self.message,self.text,self.title,str(self.output)):
            self.assertNotIn(value,json.dumps(receipt,ensure_ascii=False))
            self.assertNotIn(value,json.dumps(cards.check_provenance(self.db,card),ensure_ascii=False))
        for value in (self.text,self.title): self.assertNotIn(value,json.dumps(card,ensure_ascii=False))
        self.assertEqual(set(card),cards.FIELDS)
        self.assertEqual(cards.check_provenance(self.db,self.output)['status'],'PASS')

    def test_plain_and_legacy_only_union_new_occurrence_stales(self):
        _,plain=self.export()
        self.assertEqual(plain['export_provenance'],[])
        self.ledger('export_provenance')
        self.assertEqual(cards.check_provenance(self.db,plain)['status'],'STALE')
        _,legacy=self.export(self.root/'legacy.json')
        self.assertEqual(len(legacy['export_provenance']),1)
        self.ledger()  # backfilled duplicate does not change the union
        self.assertEqual(cards.check_provenance(self.db,legacy)['status'],'PASS')
        self.ledger(locator='line:2',parent='parent')
        self.assertEqual(cards.check_provenance(self.db,legacy)['status'],'STALE')

    def test_blob_anchor_metadata_is_stale_and_not_exportable(self):
        self.ledger()
        _, card = self.export()
        self.sql('UPDATE export_occurrences SET locator=?', (sqlite3.Binary(b'PRIVATE_BLOB'),))
        before = self.db.read_bytes()
        self.assertEqual(cards.check_provenance(self.db, card)['status'], 'STALE')
        output = self.root/'invalid-anchor.json'
        with self.assertRaisesRegex(ValueError, 'metadata is not serializable'):
            self.export(output)
        self.assertFalse(output.exists())
        self.assertEqual(before, self.db.read_bytes())

    def test_title_only_not_stale_and_message_changes_stale(self):
        _,card=self.export()
        titles(self.db,self.source,self.conversation,'local override',0)
        self.assertEqual(cards.check_provenance(self.db,card)['status'],'PASS')
        self.sql('UPDATE messages SET title=?',('different original title',))
        self.assertEqual(cards.check_provenance(self.db,card)['status'],'PASS')
        for field,value in (('text','different'),('role','assistant'),('timestamp','different'),('source_line',2),('source_sha256','b'*64)):
            with self.subTest(field=field):
                connection=sqlite3.connect(self.db)
                try:
                    original=connection.execute('SELECT '+field+' FROM messages').fetchone()[0]
                finally: connection.close()
                self.sql('UPDATE messages SET '+field+'=?',(value,))
                self.assertEqual(cards.check_provenance(self.db,card)['status'],'STALE')
                self.sql('UPDATE messages SET '+field+'=?',(original,))
        self.sql('DELETE FROM messages')
        self.assertEqual(cards.check_provenance(self.db,card)['status'],'STALE')

    def test_invalid_current_text_is_stale_not_an_exportable_card(self):
        _,card=self.export()
        self.sql('UPDATE messages SET text=?',(sqlite3.Binary(b'bad bytes'),))
        self.assertEqual(cards.check_provenance(self.db,card)['status'],'STALE')
        with self.assertRaises(ValueError):self.export(self.root/'bad.json')
        self.assertFalse((self.root/'bad.json').exists())

    def test_unknown_exact_tuple_and_unicode_validation(self):
        for args in ((self.source,self.conversation,'missing'),('other',self.conversation,self.message)):
            with self.assertRaisesRegex(ValueError,'unknown message tuple'):
                cards.export_provenance(self.db,*args,self.output)
        self.assertFalse(self.output.exists())
        for bad in ('', '\ud800', None, True):
            with patch.object(cards,'readonly',side_effect=AssertionError('opened')), self.assertRaises(ValueError):
                cards.export_provenance(self.db,bad,self.conversation,self.message,self.output)

    def test_strict_fields_types_hashes_dates_order_and_boundaries(self):
        self.ledger(); _,card=self.export()
        for updates in (dict(extra='PRIVATE'),dict(source=''),dict(message_id='\ud800'),dict(role='unknown'),dict(source_line=True),dict(text_utf8_bytes=-1),dict(text_sha256='PRIVATE'),dict(declared_at='PRIVATE'),dict(contains_title=0),dict(authorship_verified=True),dict(boundary='PRIVATE')):
            with self.subTest(updates=updates), self.assertRaises(ValueError) as error:
                cards.validate_card(dict(card,**updates))
            self.assertNotIn('PRIVATE',str(error.exception))
        for key,value in (('original_sha256','invalid'),('locator',1),('parent_id',False)):
            bad=copy.deepcopy(card);bad['export_provenance'][0][key]=value
            with self.assertRaises(ValueError):cards.validate_card(bad)
        bad=copy.deepcopy(card);bad['export_provenance']*=2
        with self.assertRaises(ValueError):cards.validate_card(bad)
        detached=cards.validate_card(card);detached['export_provenance'].clear()
        self.assertTrue(card['export_provenance'])

    def test_card_tampering_is_stale_not_authority(self):
        _,card=self.export()
        for updates in (dict(text_sha256='a'*64),dict(text_utf8_bytes=0),dict(source='other-source'),dict(conversation='other'),dict(message_id='other')):
            self.assertEqual(cards.check_provenance(self.db,dict(card,**updates))['status'],'STALE')
        # The supplied date is copied for comparison, not evidence of a wall clock.
        self.assertEqual(cards.check_provenance(self.db,dict(card,declared_at='2020-01-01'))['status'],'PASS')

    def test_reader_bom_crlf_strict_size_and_no_value_echo(self):
        _,card=self.export()
        self.output.write_bytes(b'\xef\xbb\xbf'+self.output.read_bytes().replace(b'\n',b'\r\n'))
        self.assertEqual(cards.load_card(self.output),card)
        for raw in (b'\xffPRIVATE',b'{"PRIVATE":NaN}',b'['*2000,b'{"x":1,"x":2}'):
            self.output.write_bytes(raw)
            with self.assertRaises(ValueError) as error:cards.load_card(self.output)
            self.assertNotIn('PRIVATE',str(error.exception))
        self.output.write_bytes(b'x'*20)
        with patch.object(cards,'MAX_CARD_BYTES',10),self.assertRaises(ValueError):cards.load_card(self.output)

    def test_early_and_late_collision_size_cleanup(self):
        self.output.write_bytes(b'keep')
        with patch.object(cards,'readonly',side_effect=AssertionError('opened')),self.assertRaises(FileExistsError):self.export()
        self.assertEqual(self.output.read_bytes(),b'keep');self.output.unlink()
        with patch.object(cards,'MAX_CARD_BYTES',10),self.assertRaises(ValueError):self.export()
        self.assertFalse(self.output.exists())
        publication=cards._publish_new_file
        def race(path,raw,prefix):
            Path(path).write_bytes(b'race')
            return publication(path,raw,prefix)
        with patch.object(cards,'_publish_new_file',race),self.assertRaises(FileExistsError):self.export()
        self.assertEqual(self.output.read_bytes(),b'race')
        self.assertFalse(list(self.root.glob('.recap-*')))

    def test_snapshot_and_connection_closure(self):
        self.ledger(); self.sql('PRAGMA journal_mode=WAL')
        helper=cards.message_provenance_rows
        def concurrent(connection,*args,**kwargs):
            self.ledger(locator='line:2')
            return helper(connection,*args,**kwargs)
        with patch.object(cards,'message_provenance_rows',concurrent):
            _,card=self.export()
        self.assertEqual(len(card['export_provenance']),1)
        self.assertEqual(cards.check_provenance(self.db,card)['status'],'STALE')
        connection=MagicMock();connection.execute.side_effect=sqlite3.Error('synthetic')
        with patch.object(cards,'readonly',return_value=connection),self.assertRaises(sqlite3.Error):
            cards.check_provenance(self.db,card)
        connection.close.assert_called_once()
        connection.reset_mock()
        with patch.object(cards,'readonly',return_value=connection),self.assertRaises(sqlite3.Error):
            cards.export_provenance(self.db,self.source,self.conversation,self.message,self.root/'other.json')
        connection.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
