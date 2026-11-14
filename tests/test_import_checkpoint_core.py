import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from recaplib.archive import ingest_bytes, readonly
from recaplib import import_checkpoint as checkpoint
from recaplib.recovery import _messages_digest


class ImportCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.path = self.root / 'cutoff.json'
        self.source = 'private-source'
        self.seed([('private-a', '1'), ('private-b', '1')])

    def seed(self, pairs, source=None):
        raw = ''.join(json.dumps(dict(conversation_id=c, message_id=m, role='user', text='private text', title='private title', timestamp='2026-01-01')) + '\n' for c,m in pairs).encode()
        ingest_bytes(self.db, source or self.source, raw)

    def declare(self, source=None):
        receipt = checkpoint.declare_checkpoint(self.db, source or self.source, self.path, '2026-11-14')
        return receipt, checkpoint.load_checkpoint(self.path, source or self.source)

    def execute(self, sql):
        conn = sqlite3.connect(self.db)
        try:
            conn.execute(sql)
            conn.commit()
        finally:
            conn.close()

    def test_deterministic_private_readonly_and_recovery_digest(self):
        before = self.db.read_bytes()
        receipt, saved = self.declare()
        second = self.root / 'second.json'
        self.assertEqual(receipt, checkpoint.declare_checkpoint(self.db, self.source, second, '2026-11-14'))
        self.assertEqual(self.path.read_bytes(), second.read_bytes())
        self.assertEqual(before, self.db.read_bytes())
        conn = readonly(self.db)
        try:
            self.assertEqual(saved['messages_sha256'], _messages_digest(conn))
        finally:
            conn.close()
        for value in (self.source, 'private-a', 'private text', 'private title', str(self.path)):
            self.assertNotIn(value, json.dumps(receipt))
        self.assertNotIn('private-a', self.path.read_text())
        self.assertEqual(receipt['checkpoint_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_partition_and_accepted_not_occurrences(self):
        _, saved = self.declare()
        self.seed([('private-a','1'), ('private-a','2'), ('private-new','1')])
        self.seed([('other','1')], 'other-source')
        result = checkpoint.changed_since(self.db, self.source, saved)
        self.assertEqual(result['status'], 'CUTOFF_VERIFIED')
        self.assertEqual(result['delta'], dict(new_conversations=1, has_new_identities=1, no_new_identities=1, accepted_after_cutoff_messages=2))
        self.assertNotIn('private', json.dumps(result))
        self.assertEqual(result, checkpoint.changed_since(self.db, self.source, self.path))

    def test_empty_source_is_not_existence_or_completeness(self):
        _, saved = self.declare('empty-source')
        self.assertEqual(saved['accepted_messages'], 0)
        self.assertEqual(saved['artifacts'], [])
        self.seed([('new','1')], 'empty-source')
        self.assertEqual(checkpoint.changed_since(self.db, 'empty-source', saved)['delta']['new_conversations'], 1)

    def test_changed_or_missing_artifacts_unverified_without_delta(self):
        _, saved = self.declare()
        self.execute('UPDATE artifacts SET record_count=record_count+1')
        self.assertEqual(checkpoint.changed_since(self.db,self.source,saved)['delta'], None)
        self.execute('DELETE FROM artifacts')
        self.assertEqual(checkpoint.changed_since(self.db,self.source,saved)['status'], 'CUTOFF_NOT_VERIFIED')

    def test_message_tamper_delete_and_original_title_fail(self):
        _, saved = self.declare()
        self.execute("UPDATE messages SET title='tampered'")
        self.assertIsNone(checkpoint.changed_since(self.db,self.source,saved)['delta'])
        self.execute('DELETE FROM messages')
        self.assertIsNone(checkpoint.changed_since(self.db,self.source,saved)['delta'])

    def test_local_history_excluded(self):
        from recaplib.session_workflow import titles
        _, saved = self.declare()
        titles(self.db,self.source,'private-a','new local title',0)
        self.assertEqual(checkpoint.changed_since(self.db,self.source,saved)['status'], 'CUTOFF_VERIFIED')

    def test_exact_strict_validation_value_free(self):
        _, saved = self.declare()
        mutations = [dict(source='secret'), dict(accepted_messages=True),dict(accepted_messages=-1),dict(messages_sha256='secret'), dict(boundary='secret'), dict(archive_mutation=0),dict(extra='secret'),dict(declared_at='secret')]
        for updates in mutations:
            with self.subTest(updates=updates), self.assertRaises(ValueError) as error:
                checkpoint.validate_checkpoint(dict(saved,**updates),self.source)
            self.assertNotIn('secret',str(error.exception))
        for key,value in [('bytes',True),('record_count',-1),('sha256','SECRET')]:
            bad=copy.deepcopy(saved); bad['artifacts'][0][key]=value
            with self.assertRaises(ValueError): checkpoint.validate_checkpoint(bad)
        bad=copy.deepcopy(saved); bad['artifacts']*=2
        with self.assertRaises(ValueError): checkpoint.validate_checkpoint(bad)
        detached=checkpoint.validate_checkpoint(saved); detached['artifacts'][0]['bytes']=0
        self.assertNotEqual(detached,saved)

    def test_reader_bom_crlf_malformed_size(self):
        _,saved=self.declare()
        self.path.write_bytes(b'\xef\xbb\xbf'+self.path.read_bytes().replace(b'\n',b'\r\n'))
        self.assertEqual(checkpoint.load_checkpoint(self.path),saved)
        for raw in (b'{"secret":NaN}',b'\xff',b'['*2000,b'{"schema":1,"schema":2}'):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError) as error: checkpoint.load_checkpoint(self.path)
            self.assertNotIn('secret',str(error.exception))
        with patch.object(checkpoint,'MAX_CHECKPOINT_BYTES',10), self.assertRaises(ValueError):
            checkpoint.validate_checkpoint(saved)

    def test_output_early_collision_limits_and_no_database_changes(self):
        self.path.write_text('existing')
        with patch.object(checkpoint,'readonly',side_effect=AssertionError('opened')), self.assertRaises(FileExistsError):
            checkpoint.declare_checkpoint(self.db,self.source,self.path)
        self.assertEqual(self.path.read_text(),'existing')
        self.path.unlink()
        before=self.db.read_bytes()
        with patch.object(checkpoint,'MAX_CHECKPOINT_BYTES',10), self.assertRaises(ValueError):
            checkpoint.declare_checkpoint(self.db,self.source,self.path)
        self.assertFalse(self.path.exists())
        self.assertEqual(before,self.db.read_bytes())
        self.assertEqual(list(self.root.glob('.recap-*')),[])

    def test_failed_query_closes_connection_and_no_output(self):
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute.side_effect = sqlite3.OperationalError('synthetic')
        with patch.object(checkpoint, 'readonly', return_value=conn), self.assertRaises(sqlite3.Error):
            checkpoint.declare_checkpoint(self.db, self.source, self.path)
        conn.close.assert_called_once()
        self.assertFalse(self.path.exists())
        _, saved = self.declare()
        conn.reset_mock()
        with patch.object(checkpoint, 'readonly', return_value=conn), self.assertRaises(sqlite3.Error):
            checkpoint.changed_since(self.db, self.source, saved)
        conn.close.assert_called_once()

    def test_late_collision_preserves_competing_file(self):
        publish = checkpoint._publish_new_file
        def race(output, raw, prefix):
            Path(output).write_text('competitor')
            return publish(output, raw, prefix)
        with patch.object(checkpoint, '_publish_new_file', race), self.assertRaises(FileExistsError):
            checkpoint.declare_checkpoint(self.db, self.source, self.path)
        self.assertEqual(self.path.read_text(), 'competitor')
        self.assertEqual(list(self.root.glob('.recap-*')), [])

    def test_one_snapshot_survives_concurrent_import(self):
        self.execute('PRAGMA journal_mode=WAL')
        _,saved=self.declare()
        original=checkpoint._artifact_rows
        def rows(connection,source):
            yield from original(connection,source)
            self.seed([('late','1')])
        with patch.object(checkpoint,'_artifact_rows',rows):
            result=checkpoint.changed_since(self.db,self.source,saved)
        self.assertEqual(result['delta']['new_conversations'],0)
        self.assertEqual(checkpoint.changed_since(self.db,self.source,saved)['delta']['new_conversations'],1)


if __name__ == '__main__':
    unittest.main()
