"""Incremental transfer from a verified source snapshot into a second archive."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import shlex
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import recap
from recaplib import import_checkpoint, normalized_export
from recaplib.archive import ingest, ingest_bytes
from tests._cli import run_cli


ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'synthetic-private-source'


def record(conversation, message):
    return dict(conversation_id=conversation, message_id=message, role='user',
                timestamp='unknown', title='private original title',
                text='private synthetic text for ' + message + '\n한글')


def jsonl(*rows):
    return ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode()


class IncrementalExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='recap incremental ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.db = self.root / 'source.sqlite'
        self.cutoff = self.root / 'cutoff.json'
        self.output = self.root / 'additions.jsonl'

    def seed(self, *rows, conversation=None):
        return ingest_bytes(self.db, SOURCE, jsonl(*rows), conversation=conversation)

    def declare(self, version):
        return import_checkpoint.declare_checkpoint(self.db, SOURCE, self.cutoff, checkpoint_version=version)

    def export(self, conversation=None):
        return normalized_export.export_normalized(self.db, SOURCE, self.output, conversation,
                                                   since_checkpoint=self.cutoff)

    def test_both_cutoffs_preserve_new_message_order_bytes_and_portability(self):
        old = record('common-private', 'old-id')
        new = [record('z-private', 'new-3'), record('common-private', 'new-2'),
               record('a-private', 'new-1'), record('common-private', 'new-4')]
        self.seed(old)
        base = self.root / 'base.jsonl'
        original = normalized_export.export_normalized(self.db, SOURCE, base)
        self.assertEqual(original['schema'], 'recap.normalized-export-receipt.v1')
        self.assertNotIn('checkpoint_schema', original)
        self.assertNotIn('since_checkpoint_sha256', original)
        self.assertNotIn('through_checkpoint_sha256', original)
        v1 = self.root / 'artifact.json'
        import_checkpoint.declare_checkpoint(self.db, SOURCE, v1)
        self.declare(2)
        self.seed(old, *new)
        ingest_bytes(self.db, 'other-source', jsonl(record('z-private', 'excluded-id')))
        before = self.db.read_bytes()
        for version, cutoff in [(1, v1), (2, self.cutoff)]:
            with self.subTest(version=version):
                path = self.root / f'transfer-{version}.jsonl'
                saved = import_checkpoint.load_checkpoint(cutoff)
                receipt = normalized_export.export_normalized(self.db, SOURCE, path, since_checkpoint=saved)
                self.assertEqual(receipt['schema'], 'recap.normalized-export-receipt.v2')
                self.assertEqual(receipt['since_checkpoint_schema'], f'recap.import-checkpoint.v{version}')
                self.assertEqual(receipt['since_checkpoint_sha256'], hashlib.sha256(cutoff.read_bytes()).hexdigest())
                self.assertNotIn('through_checkpoint_sha256', receipt)
                self.assertEqual(receipt['status'], 'EXPORTED')
                self.assertTrue(receipt['published'])
                self.assertEqual((receipt['records'], receipt['conversations']), (4, 3))
                self.assertEqual(path.read_bytes(), jsonl(*new))
                self.assertEqual(receipt['sha256'], hashlib.sha256(jsonl(*new)).hexdigest())
                self.assertEqual(receipt['bytes'], len(jsonl(*new)))
                for private in (SOURCE, 'common-private', 'new-3', old['title'], 'private synthetic text', str(path)):
                    self.assertNotIn(private, json.dumps(receipt))
                moved = self.root / f'moved-{version}.sqlite'
                self.assertEqual(ingest(moved, 'moved', base)['inserted'], 1)
                self.assertEqual(ingest(moved, 'moved', path)['inserted'], 4)
                self.assertEqual(ingest(moved, 'moved', path)['inserted'], 0)
        self.assertEqual(self.db.read_bytes(), before)

    def test_each_cutoff_digest_matches_its_declaration_across_reformatting(self):
        self.seed(record('c', 'private-old'))
        start_hash = self.declare(2)['checkpoint_sha256']
        self.seed(record('c', 'private-new'))
        end = self.root / 'ending.json'
        end_hash = import_checkpoint.declare_checkpoint(self.db, SOURCE, end, checkpoint_version=2)['checkpoint_sha256']
        self.assertNotEqual(start_hash, end_hash)
        self.assertEqual(start_hash, hashlib.sha256(self.cutoff.read_bytes()).hexdigest())
        self.assertEqual(end_hash, hashlib.sha256(end.read_bytes()).hexdigest())

        # Reorder both the top-level fields and each nested artifact's fields.
        def reordered(path):
            return json.loads(json.dumps(json.loads(path.read_bytes()), sort_keys=True))

        start_dict = reordered(self.cutoff)
        end_dict = reordered(end)
        reformatted = b'\xef\xbb\xbf' + json.dumps(end_dict, separators=(',', ':')).encode() + b'\r\n'
        end.write_bytes(reformatted)
        self.assertNotEqual(hashlib.sha256(reformatted).hexdigest(), end_hash)
        for index, (lower, upper) in enumerate(((start_dict, end), (self.cutoff, end_dict))):
            output = self.root / f'interval-{index}.jsonl'
            result = normalized_export.export_normalized(self.db, SOURCE, output,
                                                        since_checkpoint=lower, through_checkpoint=upper)
            self.assertEqual(result['status'], 'EXPORTED')
            self.assertEqual((result['since_checkpoint_sha256'], result['through_checkpoint_sha256']),
                             (start_hash, end_hash))
            serialized = json.dumps(result)
            for private in [SOURCE, 'private-old', 'private-new', *end_dict['identity_sha256s']]:
                self.assertNotIn(private, serialized)

        baseline = normalized_export.export_normalized(self.db, SOURCE, self.output, through_checkpoint=end)
        self.assertEqual(baseline['through_checkpoint_sha256'], end_hash)
        self.assertNotIn('since_checkpoint_sha256', baseline)
        no_output = self.root / 'no-additions.jsonl'
        empty = normalized_export.export_normalized(self.db, SOURCE, no_output,
                                                   since_checkpoint=end, through_checkpoint=end_dict)
        self.assertEqual(empty['status'], 'NO_NEW_MESSAGES')
        self.assertEqual((empty['since_checkpoint_sha256'], empty['through_checkpoint_sha256']),
                         (end_hash, end_hash))
        self.assertFalse(no_output.exists())

    def test_same_artifact_v2_succeeds_and_v1_fails_before_staging(self):
        rows = [record('old', 'm'), record('new', 'm')]
        self.seed(*rows, conversation='old')
        self.declare(2)
        v1 = self.root / 'v1.json'
        import_checkpoint.declare_checkpoint(self.db, SOURCE, v1)
        self.seed(*rows, conversation='new')
        with patch.object(normalized_export, '_publish_new_chunks', side_effect=AssertionError('staged')):
            with self.assertRaisesRegex(ValueError, 'could not be verified'):
                normalized_export.export_normalized(self.db, SOURCE, self.output, since_checkpoint=v1)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.export('new')['records'], 1)
        self.assertEqual(self.output.read_bytes(), jsonl(rows[1]))

    def test_selected_message_occurrences_count_modern_legacy_union(self):
        old, addition, excluded = record('c', 'old'), record('c', 'new'), record('other', 'new')
        self.seed(old)
        self.declare(2)
        self.seed(addition, excluded)
        with closing(sqlite3.connect(self.db)) as connection, connection:
            for table in ('export_provenance', 'export_occurrences'):
                connection.execute(f'CREATE TABLE {table} (source,conversation,message,original_hash,locator,parent)')
                connection.executemany(f'INSERT INTO {table} VALUES(?,?,?,?,?,?)', [
                    (SOURCE, row['conversation_id'], row['message_id'], 'a' * 64, 'node:1', None)
                    for row in (old, addition, excluded)])
            connection.execute('INSERT INTO export_occurrences VALUES(?,?,?,?,?,?)',
                               (SOURCE, 'c', 'new', 'a' * 64, 'node:2', None))
        self.assertEqual(self.export('c')['omitted_export_occurrences'], 2)
        self.assertEqual(self.output.read_bytes(), jsonl(addition))

    def test_unselected_stale_rows_fail_closed(self):
        self.seed(record('excluded', 'm'), record('included', 'm'))
        self.declare(2)
        self.seed(record('included', 'new'))
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE messages SET text='changed' WHERE conversation_id='excluded'")
        before = self.db.read_bytes()
        with patch.object(normalized_export, '_publish_new_chunks', side_effect=AssertionError('staged')):
            result = run_cli(recap.main, ['--db', self.db, 'export-normalized', '--source', SOURCE,
                             '--conversation', 'included', '--since-checkpoint', self.cutoff, '--output', self.output])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('could not be verified', result.stderr)
        self.assertNotIn(SOURCE, result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.db.read_bytes(), before)

    def test_no_changes_selected_or_empty_and_unknown_conversation(self):
        self.seed(record('known', 'old'))
        self.declare(2)
        self.seed(record('different', 'addition'))
        empty = self.root / 'empty.json'
        import_checkpoint.declare_checkpoint(self.db, 'empty', empty)
        with patch.object(normalized_export, '_publish_new_chunks', side_effect=AssertionError('staged')):
            receipts = [self.export('known'), normalized_export.export_normalized(
                self.db, 'empty', self.output, since_checkpoint=empty)]
            for r in receipts:
                self.assertEqual((r['status'], r['published'], r['records'], r['conversations']),
                                 ('NO_NEW_MESSAGES', False, 0, 0))
                self.assertEqual(r['checkpoint_status'], 'CUTOFF_VERIFIED')
                self.assertNotIn('sha256', r)
            with self.assertRaisesRegex(ValueError, 'unknown or empty'):
                self.export('unknown')
        self.assertFalse(self.output.exists())

    def test_output_and_checkpoint_admission_precede_archive_open(self):
        self.seed(record('c', 'old'))
        self.declare(2)
        with patch.object(normalized_export, 'readonly', side_effect=AssertionError('opened SQLite')):
            with self.assertRaises(ValueError):
                normalized_export.export_normalized(self.db, 'other', self.output, since_checkpoint=self.cutoff)
            self.output.write_bytes(b'competing file')
            with self.assertRaises(FileExistsError):
                self.export()
            self.cutoff.write_bytes(b'{"schema":1,"schema":2}')
            with self.assertRaises(ValueError):
                normalized_export.export_normalized(self.db, SOURCE, self.root / 'unused', since_checkpoint=self.cutoff)
        self.assertEqual(self.output.read_bytes(), b'competing file')

    def test_concurrent_writer_after_verification_cannot_change_transfer(self):
        self.seed(record('c', 'old'))
        self.declare(2)
        new = record('c', 'new')
        self.seed(new)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')

        def verify_then_write(connection, checkpoint):
            verified = import_checkpoint.verify_cutoff(connection, checkpoint)
            self.seed(record('c', 'later'))
            return verified

        with patch.object(normalized_export, 'verify_cutoff', side_effect=verify_then_write):
            self.assertEqual(self.export()['records'], 1)
        self.assertEqual(self.output.read_bytes(), jsonl(new))
        self.assertEqual(import_checkpoint.changed_since(self.db, SOURCE, self.cutoff)
                         ['delta']['accepted_after_cutoff_messages'], 2)

    def test_published_guide_and_empty_repeat_cli(self):
        guide = (ROOT / 'docs/INCREMENTAL_EXPORT.md').read_text(encoding='utf-8')
        block, = re.findall(r'```sh\n(.*?)```', guide, re.S)
        results = []
        for line in block.strip().splitlines():
            args = [word.replace('OUTPUT', str(self.root)) for word in shlex.split(line)]
            self.assertEqual(args[:2], ['python', 'recap.py'])
            result = run_cli(recap.main, args[2:])
            self.assertEqual(result.returncode, 0, result.stderr)
            results.append(json.loads(result.stdout))
        self.assertEqual(results[-2]['status'], 'EXPORTED')
        self.assertEqual(results[-2]['through_checkpoint_schema'], 'recap.import-checkpoint.v2')
        self.assertEqual(results[-1]['inserted'], 2)
        remaining = self.root / 'remaining.jsonl'
        receipt = normalized_export.export_normalized(self.db, 'synthetic', remaining,
                                                      since_checkpoint=self.root / 'next.json')
        self.assertEqual(receipt['records'], 1)
        self.assertEqual(json.loads(remaining.read_bytes())['conversation_id'], 'offset')
        args = ['--db', self.db, 'export-normalized', '--source', 'synthetic', '--since-checkpoint',
                self.cutoff, '--conversation', 'epoch', '--output', self.root / 'unused']
        result = run_cli(recap.main, args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'NO_NEW_MESSAGES')
        self.assertFalse((self.root / 'unused').exists())

    def test_nested_mixed_versions_future_imports_and_repeatable_baseline(self):
        base, middle, later = [record('c', name) for name in ('base', 'middle', 'later')]
        self.seed(base)
        starts, ends = [], []
        for version in (1, 2):
            path = self.root / f'start{version}'
            import_checkpoint.declare_checkpoint(self.db, SOURCE, path, checkpoint_version=version)
            starts.append(path)
        self.seed(middle)
        for version in (1, 2):
            path = self.root / f'end{version}'
            import_checkpoint.declare_checkpoint(self.db, SOURCE, path, checkpoint_version=version)
            ends.append(path)
        self.seed(later)
        for start in starts:
            copy = self.root / ('base-' + start.name)
            normalized_export.export_normalized(self.db, SOURCE, copy, through_checkpoint=start)
            self.assertEqual(copy.read_bytes(), jsonl(base))
            for end in ends:
                with self.subTest(start=start.name, end=end.name):
                    copy = self.root / (start.name + '-' + end.name)
                    receipt = normalized_export.export_normalized(self.db, SOURCE, copy, 'c',
                                          since_checkpoint=start, through_checkpoint=end)
                    self.assertEqual(receipt['records'], 1)
                    self.assertEqual(copy.read_bytes(), jsonl(middle))
        equal = normalized_export.export_normalized(self.db, SOURCE, self.output,
                                                    since_checkpoint=ends[1], through_checkpoint=ends[1])
        self.assertFalse(equal['published'])
        self.assertFalse(self.output.exists())

    def test_non_nested_memberships_fail_even_outside_conversation(self):
        first, second = record('a', 'old'), record('b', 'new')
        self.seed(first, second, conversation='a')
        self.declare(2)
        self.seed(first, second, conversation='b')
        end = self.root / 'both.json'
        import_checkpoint.declare_checkpoint(self.db, SOURCE, end, checkpoint_version=2)
        with patch.object(normalized_export, '_publish_new_chunks', side_effect=AssertionError('staged')):
            with self.assertRaisesRegex(ValueError, 'contained in ending checkpoint'):
                normalized_export.export_normalized(self.db, SOURCE, self.output, 'a',
                                                    since_checkpoint=end, through_checkpoint=self.cutoff)
        self.assertFalse(self.output.exists())

    def test_duplicate_only_artifact_is_also_checked_for_interval_containment(self):
        row = record('c', 'm')
        self.seed(row)
        self.declare(2)
        ingest_bytes(self.db, SOURCE, jsonl(row) + b'\n')
        end = self.root / 'end.json'
        import_checkpoint.declare_checkpoint(self.db, SOURCE, end, checkpoint_version=2)
        saved = import_checkpoint.load_checkpoint(end)
        self.assertEqual(len(saved['artifacts']), 2)
        with self.assertRaisesRegex(ValueError, 'contained in ending checkpoint'):
            normalized_export.export_normalized(self.db, SOURCE, self.output, since_checkpoint=saved,
                                                through_checkpoint=self.cutoff)
        self.assertFalse(self.output.exists())
