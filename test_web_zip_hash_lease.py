"""Synthetic ZIP inventory pagination leases and reviewed-title workflow."""
import hashlib
import json
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from inspect_web_zip import inspect_web_zip
import prepare_web_export as preparation
from test_title_queue_workflow import synthetic_exports


class WebZipHashLeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='recap zip lease ')
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.path = self.directory / 'synthetic export.zip'
        self.names = ['conversations-001.json', 'conversations-002.json', 'conversations-003.json']
        self.write_archive(self.names)

    def write_archive(self, names):
        with zipfile.ZipFile(self.path, 'w') as archive:
            for name in names:
                archive.writestr(name, '[]')

    def call(self, *args, success=True):
        result = subprocess.run([sys.executable, 'recap.py', *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode == 0, success, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        if not success:
            self.assertEqual(result.stdout, '')
            return result.stderr
        return json.loads(result.stdout)

    def test_matching_pages_and_default_none_are_identical(self):
        first = inspect_web_zip(self.path, 1, 0)
        digest = first['archive_sha256']
        self.assertEqual(first, inspect_web_zip(self.path, 1, 0, None))
        self.assertEqual(first, inspect_web_zip(self.path, 1, 0, digest))
        names = [first['candidates'][0]['member']]
        offset = first['next_offset']
        while offset is not None:
            page = inspect_web_zip(self.path, 1, offset, digest)
            self.assertEqual(page['archive_sha256'], digest)
            names.extend(item['member'] for item in page['candidates'])
            offset = page['next_offset']
        self.assertEqual(names, self.names)
        self.assertEqual(inspect_web_zip(self.path, 1, 100, digest)['candidates'], [])

    def test_replacement_that_repeats_a_candidate_is_rejected(self):
        first = inspect_web_zip(self.path, 1)
        self.write_archive(['conversations-000.json', self.names[0], self.names[2]])
        unpinned = inspect_web_zip(self.path, 1, first['next_offset'])
        self.assertEqual(first['candidates'][0]['member'], unpinned['candidates'][0]['member'])
        self.assertEqual(first['total_candidates'], unpinned['total_candidates'])
        with patch.object(zipfile, 'ZipFile', side_effect=AssertionError('must reject before metadata')):
            for offset in (first['next_offset'], 100):
                with self.assertRaisesRegex(ValueError, '^ZIP archive changed after inspection; inspect and select again$'):
                    inspect_web_zip(self.path, 1, offset, first['archive_sha256'])

    def test_invalid_hashes_reject_before_file_read(self):
        values = (True, False, 0, 1, [], {}, b'a' * 64, '', 'a' * 63, 'a' * 65,
                  'A' * 64, 'g' * 64, ' ' + 'a' * 63, 'a' * 63 + '\n')
        with patch.object(preparation, 'archive_bytes', side_effect=AssertionError('must validate before read')):
            for value in values:
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError, '^expected archive hash must be a lowercase SHA-256 hex digest$'):
                        inspect_web_zip(self.path, expected_archive_sha256=value)

    def test_unrelated_member_comment_and_order_changes_invalidate_whole_snapshot(self):
        for mutation in ('unrelated', 'comment', 'reorder'):
            with self.subTest(mutation=mutation):
                self.write_archive(self.names)
                digest = inspect_web_zip(self.path)['archive_sha256']
                if mutation == 'reorder':
                    self.write_archive(list(reversed(self.names)))
                else:
                    with zipfile.ZipFile(self.path, 'a') as archive:
                        if mutation == 'comment':
                            archive.comment = b'synthetic changed comment'
                        else:
                            archive.writestr('unrelated.txt', 'synthetic metadata')
                with self.assertRaisesRegex(ValueError, 'changed after inspection'):
                    inspect_web_zip(self.path, expected_archive_sha256=digest)

    def test_hash_check_precedes_invalid_zip_metadata(self):
        self.path.write_bytes(b'synthetic not a zip')
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'invalid or unsupported ZIP archive metadata'):
            inspect_web_zip(self.path, expected_archive_sha256=digest)
        with patch.object(zipfile, 'ZipFile', side_effect=AssertionError('must reject before metadata')):
            with self.assertRaisesRegex(ValueError, 'changed after inspection'):
                inspect_web_zip(self.path, expected_archive_sha256='0' * 64)

    def test_one_immutable_read_and_no_decompression_database_or_writes(self):
        expected = inspect_web_zip(self.path)
        raw = self.path.read_bytes()
        original = preparation.archive_bytes
        calls = []
        def read_then_replace(path):
            calls.append(path)
            content = original(path)
            Path(path).write_bytes(b'synthetic changed after read')
            return content
        with patch.object(preparation, 'archive_bytes', side_effect=read_then_replace), \
             patch.object(zipfile.ZipFile, 'open', side_effect=AssertionError('no decompression')), \
             patch.object(sqlite3, 'connect', side_effect=AssertionError('no database')):
            actual = inspect_web_zip(self.path, expected_archive_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(actual, expected)
        self.assertEqual(calls, [self.path])
        self.assertEqual(list(self.directory.iterdir()), [self.path])
        self.assertFalse(actual['files_written'])

    def test_matching_lease_preserves_metadata_and_size_bounds(self):
        digest = inspect_web_zip(self.path)['archive_sha256']
        with patch.object(preparation, 'MAX_ARCHIVE_BYTES', 10):
            with self.assertRaisesRegex(ValueError, '64 MiB'):
                inspect_web_zip(self.path, expected_archive_sha256=digest)
        with patch.object(preparation, 'MAX_ENTRIES', 2):
            with self.assertRaisesRegex(ValueError, '1000-entry'):
                inspect_web_zip(self.path, expected_archive_sha256=digest)

    def test_cli_failures_emit_no_json_and_do_not_create_database(self):
        db = self.directory / 'never.sqlite'
        digest = inspect_web_zip(self.path)['archive_sha256']
        self.write_archive(list(reversed(self.names)))
        before = set(self.directory.iterdir())
        for expected, message in ((digest, 'changed after inspection'), ('invalid', 'lowercase SHA-256')):
            error = self.call('--db', db, 'inspect-web-zip', self.path, '--offset', 1,
                              '--expected-archive-sha256', expected, success=False)
            self.assertIn(message, error)
        self.assertFalse(db.exists())
        self.assertEqual(set(self.directory.iterdir()), before)

    def test_documented_pinned_pages_prepare_import_review_apply_and_find(self):
        web, local = synthetic_exports(self.directory)
        conversations = json.loads(web.read_text(encoding='utf-8'))
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr(self.names[1], json.dumps(conversations[6:]))
            archive.writestr(self.names[0], json.dumps(conversations[:6]))
        source_snapshots = {path: path.read_bytes() for path in (self.path, web, local)}
        db = self.directory / 'archive.sqlite'
        first_command = 'python recap.py inspect-web-zip ../private-data/export.zip --limit 1 --offset 0'
        second_command = ('python recap.py inspect-web-zip ../private-data/export.zip --limit 1 '
                          '--offset NEXT_OFFSET --expected-archive-sha256 ARCHIVE_SHA256')
        documentation = Path('docs/WEB_ZIP_INVENTORY.md').read_text(encoding='utf-8')
        self.assertIn(first_command, documentation)
        self.assertIn(second_command, documentation)
        def documented_call(command, substitutions):
            # Tokenize fixed documentation first, preserving paths with spaces on Windows.
            tokens = shlex.split(command)[2:]
            return self.call(*(substitutions.get(token, token) for token in tokens))
        substitutions = {'../private-data/export.zip': str(self.path)}
        first = documented_call(first_command, substitutions)
        substitutions.update(NEXT_OFFSET=str(first['next_offset']), ARCHIVE_SHA256=first['archive_sha256'])
        second = documented_call(second_command, substitutions)
        self.assertIsNone(second['next_offset'])
        self.assertFalse(db.exists())
        pinned_args = ('inspect-web-zip', self.path, '--limit', 1,
                       '--expected-archive-sha256', first['archive_sha256'])
        self.call('--db', db, *pinned_args)
        self.assertFalse(db.exists())
        sentinel = self.directory / 'opaque existing database.sqlite'
        sentinel.write_bytes(b'SYNTHETIC opaque non-SQLite sentinel')
        before_sentinel = sentinel.read_bytes()
        self.call('--db', sentinel, *pinned_args)
        self.assertEqual(sentinel.read_bytes(), before_sentinel)
        for index, page in enumerate((first, second)):
            self.assertEqual(page['archive_sha256'], first['archive_sha256'])
            output = self.directory / f'prepared part {index}.json'
            prepared = self.call('prepare-web-export', self.path, '--member', page['candidates'][0]['member'],
                                 '--output', output, '--expected-archive-sha256', first['archive_sha256'])
            self.assertEqual(prepared['archive_sha256'], first['archive_sha256'])
            self.call('--db', db, 'import', output, '--format', 'web', '--source', 'demo')
        self.call('--db', db, 'import', local, '--format', 'local-codex', '--source', 'demo')
        identity = ('--source', 'demo', '--conversation', 'web-05')
        evidence_before = self.call('--db', db, 'show', *identity)
        self.assertEqual(evidence_before['revision'], 0)
        queue_path = self.directory / 'saved queue.json'
        preview_path = self.directory / 'saved preview.json'
        def saved_document(receipt, path, kind):
            raw = path.read_bytes()
            self.assertEqual(receipt['document_kind'], kind)
            self.assertEqual(receipt['encoding'], 'UTF-8')
            self.assertEqual(receipt['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(receipt['bytes'], len(raw))
            self.assertTrue(receipt['staging_cleanup_complete'])
            return json.loads(raw.decode('utf-8'))
        receipt = self.call('--db', db, 'review-titles', '--source', 'demo', '--limit', 24,
                            '--output', queue_path)
        queue = saved_document(receipt, queue_path, 'queue')
        self.assertEqual(queue['total_conversations'], 24)
        self.assertEqual(self.call('--db', db, 'show', *identity)['revision'], 0)
        queue_bytes = queue_path.read_bytes()
        selected_title = 'Pinned synthetic archive project 합성'
        receipt = self.call('--db', db, 'preview-title', queue_path, '--conversation', 'web-05',
                            '--title', selected_title, '--output', preview_path)
        preview = saved_document(receipt, preview_path, 'preview')
        self.assertEqual(preview['expected_revision'], 0)
        self.assertEqual(preview['proposal']['title'], selected_title)
        self.assertIn('합성'.encode('utf-8'), preview_path.read_bytes())
        self.assertEqual(self.call('--db', db, 'show', *identity)['revision'], 0)
        applied = self.call('--db', db, 'apply-title', preview_path)
        self.assertGreater(applied['revision'], 0)
        self.assertEqual(applied['display_title'], selected_title)
        evidence_after = self.call('--db', db, 'show', *identity)
        self.assertEqual(evidence_after['revision'], applied['revision'])
        self.assertEqual(evidence_after['display_title'], selected_title)
        self.assertEqual(evidence_after['original_title'], evidence_before['original_title'])
        self.assertEqual(evidence_after['messages'], evidence_before['messages'])
        self.assertEqual(self.call('--db', db, 'find', 'Pinned synthetic archive')['total_matches'], 1)
        self.assertEqual(queue_path.read_bytes(), queue_bytes)
        for path, raw in source_snapshots.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(sentinel.read_bytes(), before_sentinel)
