"""Synthetic unsigned source-view cutoff contracts, never review approval."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from recaplib.archive import ingest_bytes, readonly
from recaplib import review_checkpoint as checkpoint
from recaplib.recovery import _canonical_line
from recaplib.session_workflow import titles
from recaplib.title_proposal import content_fingerprint
from recaplib.title_review_state import review_state


class CheckpointCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.output = self.root / 'cutoff.json'
        self.source = 'private-synthetic-source'
        self.seed([('z-private', 'm1', 'Synthetic private body'), ('a-private', 'm1', '합성 body')])

    def seed(self, items, source=None):
        rows = [dict(conversation_id=c, message_id=m, role='user', text=t,
                     timestamp='2026-01-01', title='Synthetic title') for c, m, t in items]
        raw = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows).encode('utf-8')
        ingest_bytes(self.db, source or self.source, raw)

    def declare(self, path=None):
        receipt = checkpoint.declare_review_checkpoint(self.db, self.source, path or self.output, '2026-11-14')
        return receipt, checkpoint.load_checkpoint(path or self.output, self.source)

    def compare(self, saved):
        connection = readonly(self.db)
        try:
            connection.execute('BEGIN')
            return checkpoint.compare_snapshot(connection, self.source, saved)
        finally:
            connection.close()

    def test_exact_sorted_deterministic_declaration_private_receipt_and_database_unchanged(self):
        before = self.db.read_bytes()
        receipt, saved = self.declare()
        other = self.root / 'same.json'
        receipt2, saved2 = self.declare(other)
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual(self.output.read_bytes(), other.read_bytes())
        self.assertEqual(saved, saved2)
        self.assertEqual(receipt, receipt2)
        self.assertEqual([e['conversation'] for e in saved['entries']], ['a-private', 'z-private'])
        self.assertEqual(set(saved), checkpoint.FIELDS)
        self.assertEqual(saved['enumerated_conversations'], 2)
        self.assertEqual(saved['review_completion'], 'NOT_ESTABLISHED')
        encoded = json.dumps(receipt)
        for private in (self.source, 'a-private', 'z-private', 'Synthetic private body', str(self.output)):
            self.assertNotIn(private, encoded)
        self.assertEqual(receipt['checkpoint_sha256'], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(receipt['checkpoint_bytes'], len(self.output.read_bytes()))
        self.assertFalse(receipt['archive_mutation'])
        self.assertFalse(receipt['contains_message_text'])
        self.assertTrue(receipt['staging_cleanup_complete'])
        self.assertFalse(list(self.root.glob('.recap-*')))

    def test_digest_existing_content_contract_and_binary_unicode_order(self):
        self.seed([('😀', 'm1', 'Synthetic emoji'), ('가', 'm1', 'Synthetic Korean'), (' ', 'm1', 'Synthetic space ID')])
        _, saved = self.declare()
        self.assertEqual([e['conversation'] for e in saved['entries']], [' ', 'a-private', 'z-private', '가', '😀'])
        rows = [dict(message_id='m1', role='user', text='합성 body')]
        self.assertEqual(saved['entries'][1]['content_sha256'], content_fingerprint(rows))
        raw = b''.join(_canonical_line([e['conversation'], e['content_sha256'], e['title_revision']]) for e in saved['entries'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), saved['entries_sha256'])

    def test_comparison_new_both_changes_unchanged_and_missing(self):
        _, saved = self.declare()
        self.seed([('a-private', 'm2', 'Synthetic added'), ('new-private', 'm1', 'Synthetic new')])
        titles(self.db, self.source, 'a-private', 'Synthetic title', 0)
        before = self.db.read_bytes()
        changed, counts = self.compare(saved)
        self.assertEqual(changed, {'a-private', 'new-private'})
        self.assertEqual({k: counts[k] for k in ('new', 'changed_content', 'changed_title', 'unchanged', 'missing_from_archive')},
                         dict(new=1, changed_content=1, changed_title=1, unchanged=1, missing_from_archive=0))
        self.assertEqual(before, self.db.read_bytes())
        connection = sqlite3.connect(self.db)
        try:
            connection.execute('DELETE FROM messages WHERE conversation_id=?', ('z-private',))
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(self.compare(saved)[1]['missing_from_archive'], 1)

    def test_timestamp_provenance_and_review_state_do_not_change_content_fingerprint(self):
        _, saved = self.declare()
        connection = sqlite3.connect(self.db)
        try:
            connection.execute("UPDATE messages SET timestamp='different',source_line=99")
            connection.commit()
        finally:
            connection.close()
        lease = review_state(self.db, self.source, 'a-private')
        review_state(self.db, self.source, 'a-private', 'skipped', lease['state_revision'],
                     lease['expected_title_revision'], lease['expected_content_sha256'])
        changed, counts = self.compare(saved)
        self.assertEqual(changed, set())
        self.assertEqual(counts['unchanged'], 2)

    def test_source_scope_empty_cutoff_and_no_archive_uuid_inference(self):
        self.seed([('other-private', 'm', 'Synthetic other')], source='other-source')
        _, saved = self.declare()
        self.assertEqual(saved['enumerated_conversations'], 2)
        empty_path = self.root / 'empty.json'
        receipt = checkpoint.declare_review_checkpoint(self.db, 'no-stored-messages', empty_path)
        empty = checkpoint.load_checkpoint(empty_path, 'no-stored-messages')
        self.assertEqual(receipt['enumerated_conversations'], 0)
        self.assertEqual(empty['entries'], [])
        self.assertEqual(empty['entries_sha256'], hashlib.sha256(b'').hexdigest())
        with self.assertRaisesRegex(ValueError, 'invalid review checkpoint'):
            checkpoint.validate_checkpoint(saved, 'other-source')

    def test_single_read_snapshot_across_paged_enumeration(self):
        self.seed([(f'page-{i:03}', 'm', 'Synthetic page') for i in range(101)])
        c = sqlite3.connect(self.db)
        c.execute('PRAGMA journal_mode=WAL')
        c.close()
        original = checkpoint._inventory
        calls = []
        def concurrent(connection, source, **kwargs):
            page = original(connection, source, **kwargs)
            calls.append(connection)
            if len(calls) == 1:
                self.seed([('late-private', 'm', 'Synthetic late')])
            return page
        with patch.object(checkpoint, '_inventory', side_effect=concurrent):
            _, saved = self.declare()
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(all(c is calls[0] for c in calls))
        self.assertEqual(saved['enumerated_conversations'], 103)
        self.assertNotIn('late-private', [e['conversation'] for e in saved['entries']])
        self.assertEqual(self.compare(saved)[1]['new'], 1)

    def test_input_bom_crlf_and_exact_reader_bound(self):
        _, saved = self.declare()
        raw = b'\xef\xbb\xbf' + self.output.read_bytes().replace(b'\n', b'\r\n')
        self.output.write_bytes(raw)
        self.assertEqual(checkpoint.load_checkpoint(self.output, self.source), saved)
        # Input and re-encoded output are both bounded; exact input size succeeds.
        with patch.object(checkpoint, 'MAX_CHECKPOINT_BYTES', len(raw)):
            self.assertEqual(checkpoint.load_checkpoint(self.output, self.source), saved)
        with patch.object(checkpoint, 'MAX_CHECKPOINT_BYTES', len(raw)-1):
            with self.assertRaisesRegex(ValueError, 'within 64 MiB'):
                checkpoint.load_checkpoint(self.output, self.source)

    def test_early_collision_symlink_missing_parent_and_limit_do_not_read_or_publish(self):
        self.output.write_text('keep', encoding='utf-8')
        with patch.object(checkpoint, 'readonly', side_effect=AssertionError('must not open')):
            with self.assertRaises(FileExistsError):
                self.declare()
        self.assertEqual(self.output.read_text(), 'keep')
        with self.assertRaises(FileNotFoundError):
            checkpoint.declare_review_checkpoint(self.db, self.source, self.root/'absent'/'cutoff.json')
        self.output.unlink()
        with patch.object(checkpoint, 'MAX_CHECKPOINT_BYTES', 10):
            with self.assertRaisesRegex(ValueError, 'exceeds the 64 MiB'):
                self.declare()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.recap-*')))
        try:
            self.output.symlink_to(self.root/'missing')
        except OSError:
            return
        with self.assertRaises(FileExistsError):
            self.declare()
        self.assertTrue(self.output.is_symlink())
        self.assertFalse((self.root/'missing').exists())

    def test_late_output_collision_preserves_competing_file(self):
        original = checkpoint._publish_new_file
        def collide(output, raw, prefix):
            Path(output).write_bytes(b'competing bytes')
            return original(output, raw, prefix)
        before = self.db.read_bytes()
        with patch.object(checkpoint, '_publish_new_file', side_effect=collide):
            with self.assertRaises(FileExistsError):
                self.declare()
        self.assertEqual(self.output.read_bytes(), b'competing bytes')
        self.assertEqual(before, self.db.read_bytes())
        self.assertFalse(list(self.root.glob('.recap-*')))

    def test_exact_schema_hash_sort_revision_boundary_and_date_rejections(self):
        _, saved = self.declare()
        cases = []
        def changed(fn):
            value = copy.deepcopy(saved); fn(value); cases.append(value)
        changed(lambda x: x.update(extra='private-secret'))
        changed(lambda x: x.pop('boundary'))
        changed(lambda x: x.update(schema='unknown'))
        changed(lambda x: x.update(declared_at='2026-13-01'))
        changed(lambda x: x.update(archive_mutation=0))
        changed(lambda x: x.update(review_completion='COMPLETE'))
        changed(lambda x: x.update(boundary='private-secret'))
        changed(lambda x: x.update(entries_sha256='0'*64))
        changed(lambda x: x.update(enumerated_conversations=True))
        changed(lambda x: x['entries'].reverse())
        changed(lambda x: x['entries'].append(copy.deepcopy(x['entries'][0])))
        changed(lambda x: x['entries'][0].update(title_revision=True))
        changed(lambda x: x['entries'][0].update(title_revision=-1))
        changed(lambda x: x['entries'][0].update(content_sha256='A'*64))
        changed(lambda x: x['entries'][0].update(conversation=''))
        changed(lambda x: x['entries'][0].update(state_revision=1))
        for value in cases:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, '^invalid review checkpoint:') as error:
                checkpoint.validate_checkpoint(value, self.source)
            self.assertNotIn('private-secret', str(error.exception))
        detached = checkpoint.validate_checkpoint(saved)
        detached['entries'].clear()
        self.assertEqual(len(saved['entries']), 2)

    def test_invalid_encoded_inputs_and_read_growth_are_bounded_and_value_free(self):
        invalid = [b'{"private-secret":', b'{"x":1,"x":2}', b'\xff', b'\xef\xbb\xbf\xef\xbb\xbf{}',
                   b'[NaN]', b'[1e999]', b'['*10000 + b']'*10000]
        for raw in invalid:
            self.output.write_bytes(raw)
            with self.subTest(raw=raw[:20]), self.assertRaisesRegex(ValueError, '^review checkpoint must be') as error:
                checkpoint.load_checkpoint(self.output, self.source)
            self.assertNotIn('private-secret', str(error.exception))
        self.output.write_bytes(b'{}')
        class Growing(io.BytesIO):
            def read(self, size=-1):
                self.seen = size
                return super().read(size)
        stream = Growing(b'x'*101)
        with patch.object(checkpoint, 'MAX_CHECKPOINT_BYTES', 100), patch.object(Path, 'open', return_value=stream):
            with self.assertRaises(ValueError):
                checkpoint.load_checkpoint(self.output, self.source)
        self.assertEqual(stream.seen, 101)

    def test_invalid_source_and_date_fail_before_database_access(self):
        for source in (None, '', ' ', 1, '\ud800'):
            with patch.object(checkpoint, 'readonly', side_effect=AssertionError('must not open')):
                with self.assertRaises(ValueError):
                    checkpoint.declare_review_checkpoint(self.db, source, self.output)
        with patch.object(checkpoint, 'readonly', side_effect=AssertionError('must not open')):
            with self.assertRaises(ValueError):
                checkpoint.declare_review_checkpoint(self.db, self.source, self.output, 'private-secret')
