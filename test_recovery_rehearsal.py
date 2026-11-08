"""Synthetic recovery declaration and rehearsal: read-only checks, receipts and refusals."""
import hashlib
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import recovery
from recap import ingest
from recovery import declare_recovery, rehearse_recovery, render_text
from session_workflow import import_export, titles

ROOT = Path(__file__).resolve().parent
RECEIPT_FIELDS = {'schema', 'status', 'failed_checks', 'checks_run', 'manifest', 'restored', 'objects_directory',
                  'checks', 'restored_archive_written', 'archive_mutation', 'network_access',
                  'contains_message_text', 'clean_destination_verified', 'remote_backup_verified',
                  'decryption_keys_verified', 'future_restore_verified', 'scope', 'boundary'}
STDOUT_EXTRA = {'receipt_bytes', 'receipt_sha256', 'staging_cleanup_complete', 'remaining_staging_file'}
DECLARATION_FIELDS = {'schema', 'status', 'manifest_schema', 'manifest_bytes', 'manifest_sha256', 'declared_at',
                      'sources', 'artifacts', 'optional_artifacts', 'messages', 'conversations', 'messages_sha256',
                      'export_occurrences', 'title_history', 'fts_rows', 'staging_cleanup_complete',
                      'remaining_staging_file', 'archive_mutation', 'network_access', 'contains_message_text',
                      'backup_created', 'remote_copy_verified', 'scope', 'boundary'}
ROWS = (dict(conversation_id='synthetic-1', message_id='u1', role='user', timestamp='2026-01-01T00:00:00Z',
             title='Synthetic orchard', text='How should a synthetic orchard be organized?'),
        dict(conversation_id='synthetic-1', message_id='a1', role='assistant', timestamp='2026-01-01T00:01:00Z',
             title='Synthetic orchard', text='Synthetic sample answer 합성 과수원.'),
        dict(conversation_id='synthetic-2', message_id='u2', role='user', timestamp='2026-01-02T00:00:00Z',
             title='Second synthetic', text='Second synthetic request'))


def no_data_controls(text):
    """True when only the renderer's own newlines separate ASCII printable text."""
    return text.isascii() and all(character == '\n' or 32 <= ord(character) < 127 for character in text)


def symlink_or_skip(test, target, link):
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError):
        test.skipTest('symlink creation is not permitted on this host')


class RecoveryRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.objects = self.root / 'objects'; self.objects.mkdir()
        self.normalized = self.objects / 'normalized.jsonl'
        self.normalized.write_bytes(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in ROWS).encode('utf-8'))
        self.web = self.objects / 'web-export.json'
        self.web.write_bytes((ROOT / 'examples/web-export.json').read_bytes())
        ingest(self.db, 'demo', self.normalized)
        import_export(self.db, 'web', self.web, 'web')
        titles(self.db, 'demo', 'synthetic-1', 'Reviewed synthetic title', 0)
        self.manifest = self.root / 'manifest.json'
        self.declaration = declare_recovery(self.db, self.manifest, '2026-11-08')
        self.counter = 0

    def copy(self, name='restored.sqlite'):
        restored = self.root / name
        shutil.copyfile(self.db, restored)
        return restored

    def rehearse(self, restored, objects=None, manifest=None):
        self.counter += 1
        return rehearse_recovery(manifest or self.manifest, restored, self.root / f'receipt-{self.counter}.json',
                                 objects)

    def edit(self, restored, sql, *params):
        with closing(sqlite3.connect(restored)) as connection, connection:
            connection.execute(sql, params)

    def check(self, receipt, name):
        return next(check for check in receipt['checks'] if check['check'] == name)

    def test_declaration_manifest_and_passing_rehearsal_with_objects(self):
        self.assertEqual(set(self.declaration), DECLARATION_FIELDS)
        self.assertEqual(self.declaration['status'], 'DECLARED')
        raw = self.manifest.read_bytes()
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        self.assertEqual((self.declaration['manifest_bytes'], self.declaration['manifest_sha256']),
                         (len(raw), hashlib.sha256(raw).hexdigest()))
        manifest = json.loads(raw.decode('utf-8'))
        self.assertEqual(set(manifest), set(recovery.MANIFEST_FIELDS))
        self.assertEqual(manifest['schema'], 'recap.recovery-manifest.v1')
        self.assertEqual(manifest['declared_at'], '2026-11-08')
        self.assertEqual([source['source_id'] for source in manifest['sources']], ['demo', 'web'])
        demo, web = manifest['sources']
        self.assertEqual((demo['artifacts'], demo['messages'], demo['conversations'], demo['export_occurrences'],
                          demo['original_hashes']), (1, 3, 2, 0, []))
        original = hashlib.sha256(self.web.read_bytes()).hexdigest()
        self.assertEqual((web['artifacts'], web['messages'], web['conversations'], web['export_occurrences'],
                          web['original_hashes']), (1, 2, 1, 2, [original]))
        with closing(sqlite3.connect(self.db)) as connection:
            rows = [dict(zip(('source_id', 'sha256', 'bytes', 'record_count'), row)) for row in connection.execute(
                'SELECT source_id,sha256,bytes,record_count FROM artifacts ORDER BY source_id,sha256')]
        self.assertEqual(manifest['artifacts'], rows)
        self.assertEqual(rows[0]['sha256'], hashlib.sha256(self.normalized.read_bytes()).hexdigest())
        self.assertEqual(manifest['optional_artifacts'], [dict(source_id='web', sha256=rows[1]['sha256'])])
        self.assertEqual((manifest['messages'], manifest['conversations'], manifest['export_occurrences'],
                          manifest['fts_rows'], manifest['title_history']['count']), (5, 3, 2, 5, 1))
        self.assertTrue(re.fullmatch('[0-9a-f]{64}', manifest['messages_sha256']))
        self.assertNotIn('orchard', raw.decode('utf-8'))
        self.assertEqual(self.declaration['messages_sha256'], manifest['messages_sha256'])
        self.assertEqual((self.declaration['sources'], self.declaration['artifacts'],
                          self.declaration['optional_artifacts'], self.declaration['title_history']), (2, 2, 1, 1))
        receipt = self.rehearse(self.copy(), self.objects)
        self.assertEqual(set(receipt), RECEIPT_FIELDS | STDOUT_EXTRA)
        self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_PASSED')
        self.assertEqual(receipt['failed_checks'], [])
        self.assertEqual([check['check'] for check in receipt['checks']], list(recovery.CHECKS) + ['declared_objects'])
        self.assertTrue(all(check['status'] == 'PASS' for check in receipt['checks']))
        self.assertEqual(receipt['manifest']['sha256'], self.declaration['manifest_sha256'])
        self.assertEqual(receipt['restored']['path'], str(self.root / 'restored.sqlite'))
        restored_raw = (self.root / 'restored.sqlite').read_bytes()
        self.assertEqual((receipt['restored']['bytes'], receipt['restored']['sha256']),
                         (len(restored_raw), hashlib.sha256(restored_raw).hexdigest()))
        objects = self.check(receipt, 'declared_objects')
        self.assertEqual((objects['declared'], objects['required'], objects['present'], objects['missing_required'],
                          objects['missing_optional'], objects['refusals']), (3, 2, 2, 0, 1, []))
        statuses = {item['sha256']: (item['status'], item['required']) for item in objects['objects']}
        self.assertEqual(statuses[rows[0]['sha256']], ('PRESENT', True))
        self.assertEqual(statuses[original], ('PRESENT', True))
        self.assertEqual(statuses[rows[1]['sha256']], ('MISSING', False))
        sample = self.check(receipt, 'fts_match_sample')
        self.assertEqual((sample['sampled_message_pk'], sample['token_length'], sample['matched']), (1, 3, True))
        self.assertFalse(sample['contains_message_text'])
        saved = json.loads((self.root / 'receipt-1.json').read_bytes().decode('utf-8'))
        self.assertEqual(saved, {key: value for key, value in receipt.items() if key not in STDOUT_EXTRA})
        self.assertEqual(receipt['receipt_sha256'], hashlib.sha256((self.root / 'receipt-1.json').read_bytes()).hexdigest())
        self.assertEqual(self.rehearse(self.db)['status'], 'RECOVERY_REHEARSAL_PASSED')

    def test_tampered_message_row_fails_digest_only(self):
        restored = self.copy()
        self.edit(restored, "UPDATE messages SET role='assistant' WHERE message_id='u2'")
        receipt = self.rehearse(restored)
        self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_FAILED')
        self.assertEqual(receipt['failed_checks'], ['messages_digest'])
        digest = self.check(receipt, 'messages_digest')
        self.assertEqual(digest['declared'], self.declaration['messages_sha256'])
        self.assertNotEqual(digest['found'], digest['declared'])
        stale = self.copy('stale-index.sqlite')
        self.edit(stale, "UPDATE messages SET text='zzqq replaced synthetic body' WHERE message_pk=1")
        receipt = self.rehearse(stale)
        self.assertEqual(receipt['failed_checks'], ['messages_digest', 'fts_match_sample'])
        self.assertFalse(self.check(receipt, 'fts_match_sample')['matched'])
        removed = self.copy('removed-row.sqlite')
        self.edit(removed, "DELETE FROM messages WHERE message_id='a1'")
        receipt = self.rehearse(removed)
        self.assertIn('fts_rows', receipt['failed_checks'])
        self.assertEqual(self.check(receipt, 'fts_rows')['fts_rows'], 5)
        self.assertEqual(self.check(receipt, 'fts_rows')['messages'], 4)
        self.assertEqual(self.check(receipt, 'source_counts')['mismatched'][0]['found']['messages'], 2)

    def test_missing_or_extra_artifact_row_fails(self):
        restored = self.copy()
        self.edit(restored, "DELETE FROM artifacts WHERE source_id='demo'")
        receipt = self.rehearse(restored)
        self.assertEqual(receipt['failed_checks'], ['artifact_rows', 'source_counts'])
        rows = self.check(receipt, 'artifact_rows')
        self.assertEqual((rows['declared'], rows['found'], rows['missing'], rows['unexpected']), (2, 1, 1, 0))
        self.assertEqual(rows['missing_rows'][0]['source_id'], 'demo')
        self.assertEqual(rows['missing_rows'][0]['sha256'], hashlib.sha256(self.normalized.read_bytes()).hexdigest())
        self.assertEqual(self.check(receipt, 'source_counts')['mismatched'],
                         [dict(source_id='demo', declared=dict(artifacts=1, messages=3, conversations=2),
                               found=dict(artifacts=0, messages=3, conversations=2))])
        extra = self.copy('extra.sqlite')
        self.edit(extra, 'INSERT INTO artifacts VALUES(?,?,?,?)', 'undeclared', '0' * 64, 1, 1)
        receipt = self.rehearse(extra)
        self.assertEqual(self.check(receipt, 'artifact_rows')['unexpected_rows'],
                         [dict(source_id='undeclared', sha256='0' * 64, bytes=1, record_count=1)])
        self.assertEqual(self.check(receipt, 'source_counts')['undeclared_sources'], ['undeclared'])

    def test_changed_title_history_fails_count_or_digest(self):
        restored = self.copy()
        self.edit(restored, "UPDATE title_history SET title='Edited after declaration'")
        receipt = self.rehearse(restored)
        self.assertEqual(receipt['failed_checks'], ['title_history'])
        history = self.check(receipt, 'title_history')
        self.assertEqual((history['state'], history['declared']['count'], history['found']['count']), ('compared', 1, 1))
        self.assertNotEqual(history['declared']['sha256'], history['found']['sha256'])
        grown = self.copy('grown.sqlite')
        titles(grown, 'demo', 'synthetic-2', 'Another reviewed title', 0)
        receipt = self.rehearse(grown)
        self.assertEqual(receipt['failed_checks'], ['title_history'])
        self.assertEqual(self.check(receipt, 'title_history')['found']['count'], 2)
        # Title changes in the restored copy never alter message rows or the FTS index.
        self.assertEqual(self.check(receipt, 'messages_digest')['status'], 'PASS')

    def test_optional_ledgers_both_absent_pass_and_one_sided_fail(self):
        plain = self.root / 'plain.sqlite'
        ingest(plain, 'demo', self.normalized)
        manifest = self.root / 'plain-manifest.json'
        declaration = declare_recovery(plain, manifest)
        self.assertIsNone(declaration['declared_at'])
        self.assertEqual((declaration['export_occurrences'], declaration['title_history']), (None, None))
        document = json.loads(manifest.read_bytes().decode('utf-8'))
        self.assertIsNone(document['declared_at'])
        self.assertEqual((document['sources'][0]['export_occurrences'], document['sources'][0]['original_hashes']),
                         (None, None))
        receipt = self.rehearse(plain, manifest=manifest)
        self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_PASSED')
        for name in ('export_occurrences', 'title_history'):
            self.assertEqual(self.check(receipt, name)['state'], 'both absent')
        renamed = self.root / 'plain-renamed.sqlite'
        shutil.copyfile(plain, renamed)
        titles(renamed, 'demo', 'synthetic-1', 'Title added after declaration', 0)
        receipt = self.rehearse(renamed, manifest=manifest)
        self.assertEqual(receipt['failed_checks'], ['title_history'])
        self.assertEqual(self.check(receipt, 'title_history')['state'], 'table present but not declared')
        dropped = self.copy('dropped.sqlite')
        self.edit(dropped, 'DROP TABLE title_history')
        receipt = self.rehearse(dropped)
        self.assertEqual(receipt['failed_checks'], ['expected_tables', 'title_history'])
        self.assertEqual(self.check(receipt, 'expected_tables')['missing'], ['title_history'])
        self.assertEqual(self.check(receipt, 'title_history')['state'], 'declared but table missing')

    def test_objects_directory_reports_missing_required_and_refuses_bounds(self):
        restored = self.copy()
        self.web.unlink()
        receipt = self.rehearse(restored, self.objects)
        self.assertEqual(receipt['failed_checks'], ['declared_objects'])
        objects = self.check(receipt, 'declared_objects')
        self.assertEqual((objects['present'], objects['missing_required'], objects['missing_optional']), (1, 1, 1))
        original = hashlib.sha256((ROOT / 'examples/web-export.json').read_bytes()).hexdigest()
        self.assertEqual([item['status'] for item in objects['objects'] if item['sha256'] == original], ['MISSING'])
        self.assertEqual(objects['files_hashed'], 1)
        empty = self.root / 'empty-objects'; empty.mkdir()
        receipt = self.rehearse(restored, empty)
        self.assertEqual(self.check(receipt, 'declared_objects')['present'], 0)
        with patch.object(recovery, 'MAX_OBJECT_FILES', 0):
            receipt = self.rehearse(restored, self.objects)
        objects = self.check(receipt, 'declared_objects')
        self.assertEqual((objects['status'], objects['refusals'], objects['files_hashed']), ('FAIL', ['TOO_MANY_FILES'], 0))
        self.assertEqual({item['status'] for item in objects['objects']}, {'NOT_CHECKED'})
        with patch.object(recovery, 'MAX_OBJECT_BYTES', 10):
            receipt = self.rehearse(restored, self.objects)
        objects = self.check(receipt, 'declared_objects')
        self.assertEqual((objects['status'], objects['refusals'], objects['files_hashed']), ('FAIL', ['OVERSIZED_FILE'], 0))
        with self.assertRaisesRegex(ValueError, 'objects path'):
            self.rehearse(restored, self.root / 'missing-objects')
        self.assertFalse((self.root / f'receipt-{self.counter}.json').exists())

    def test_objects_directory_refuses_symlinks(self):
        symlink_or_skip(self, self.normalized, self.objects / 'alias.jsonl')
        receipt = self.rehearse(self.copy(), self.objects)
        objects = self.check(receipt, 'declared_objects')
        self.assertEqual((objects['status'], objects['refusals']), ('FAIL', ['SYMLINK_REFUSED']))
        self.assertEqual({item['status'] for item in objects['objects']}, {'NOT_CHECKED'})
        link = self.root / 'objects-link'
        symlink_or_skip(self, self.objects, link)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.rehearse(self.copy('second.sqlite'), link)
        archive_link = self.root / 'archive-link.sqlite'
        symlink_or_skip(self, self.db, archive_link)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            self.rehearse(archive_link)

    def test_objects_directory_records_unreadable_entries_instead_of_aborting(self):
        nested = self.objects / 'nested'; nested.mkdir()
        (nested / 'vanished.bin').write_bytes(b'synthetic object that disappears before hashing')
        real_hash = recovery._hash_file

        def flaky_hash(path):
            # Stand-ins for a locked or permission-denied object and for a file removed between walk and hash.
            if path.name == 'normalized.jsonl':
                raise PermissionError(13, 'Permission denied', str(path))
            if path.name == 'vanished.bin':
                raise FileNotFoundError(2, 'No such file or directory', str(path))
            return real_hash(path)

        restored = self.copy()
        with patch.object(recovery, '_hash_file', flaky_hash):
            receipt = self.rehearse(restored, self.objects)
        self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_FAILED')
        self.assertEqual(receipt['failed_checks'], ['declared_objects'])
        objects = self.check(receipt, 'declared_objects')
        self.assertEqual((objects['refusals'], objects['files_seen'], objects['files_hashed'],
                          objects['unreadable_count']), (['UNREADABLE_FILE'], 3, 1, 2))
        self.assertEqual(objects['unreadable'], [dict(path='nested/vanished.bin', error='FileNotFoundError'),
                                                 dict(path='normalized.jsonl', error='PermissionError')])
        # Only the relative path and the exception type are recorded, never the OS error text with its absolute path.
        self.assertNotIn(str(self.root), json.dumps(objects['unreadable']))
        statuses = {item['sha256']: item['status'] for item in objects['objects']}
        self.assertEqual(statuses[hashlib.sha256(self.normalized.read_bytes()).hexdigest()], 'MISSING')
        self.assertEqual(statuses[hashlib.sha256(self.web.read_bytes()).hexdigest()], 'PRESENT')
        self.assertEqual((objects['missing_required'], objects['missing_optional']), (1, 1))
        self.assertTrue((self.root / f'receipt-{self.counter}.json').is_file())

        def unlistable_walk(top, topdown=True, onerror=None, followlinks=False):
            onerror(PermissionError(13, 'Permission denied', os.path.join(str(top), 'locked')))
            return iter(())

        with patch.object(recovery.os, 'walk', unlistable_walk):
            receipt = self.rehearse(restored, self.objects)
        objects = self.check(receipt, 'declared_objects')
        self.assertEqual((objects['status'], objects['refusals'], objects['files_seen'], objects['files_hashed']),
                         ('FAIL', ['UNREADABLE_DIRECTORY'], 0, 0))
        self.assertEqual(objects['unreadable'], [dict(path='locked', error='PermissionError')])
        self.assertEqual({item['status'] for item in objects['objects']}, {'NOT_CHECKED'})
        self.assertEqual(receipt['failed_checks'], ['declared_objects'])
        # Object refusals never alter the archive verdicts: every other check still passed.
        self.assertTrue(all(check['status'] == 'PASS' for check in receipt['checks'][:-1]))

    def test_corrupt_and_non_sqlite_files_produce_failed_receipts_without_traceback(self):
        garbage = self.root / 'garbage.sqlite'
        garbage.write_bytes(b'SYNTHETIC NOT A DATABASE ' * 64)
        truncated = self.root / 'truncated.sqlite'
        truncated.write_bytes(self.db.read_bytes()[: self.db.stat().st_size // 2])
        empty = self.root / 'empty.sqlite'
        empty.write_bytes(b'')
        for index, path in enumerate((garbage, truncated, empty)):
            with self.subTest(path=path.name):
                output = self.root / f'cli-receipt-{index}.json'
                result = subprocess.run([sys.executable, 'recap.py', 'rehearse-recovery', str(self.manifest),
                                         '--restored-db', str(path), '--output', str(output)],
                                        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=30)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn('Traceback', result.stderr)
                self.assertEqual(result.stderr, '')
                receipt = json.loads(result.stdout)
                self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_FAILED')
                self.assertEqual(json.loads(output.read_bytes().decode('utf-8'))['status'], 'RECOVERY_REHEARSAL_FAILED')
                integrity = self.check(receipt, 'integrity_check')
                if path is empty:
                    self.assertEqual(integrity['status'], 'PASS')
                    self.assertEqual(receipt['failed_checks'][0], 'expected_tables')
                    self.assertEqual(self.check(receipt, 'expected_tables')['missing'],
                                     ['artifacts', 'messages', 'messages_fts', 'export_occurrences', 'title_history'])
                else:
                    # SQLite may raise on open or report rows; both must gate the remaining checks.
                    self.assertEqual(integrity['status'], 'FAIL')
                    self.assertIn(integrity['result'], ('OPEN_ERROR', 'NOT_OK'))
                    if integrity['result'] == 'OPEN_ERROR':
                        self.assertIn('DatabaseError', integrity['error'])
                    else:
                        self.assertGreater(integrity['message_count'], 0)
                    self.assertEqual(receipt['failed_checks'], list(recovery.CHECKS))
                    self.assertTrue(all(check['detail'] == recovery.NOT_RUN for check in receipt['checks'][1:]))
                self.assertEqual(receipt['restored']['bytes'], path.stat().st_size)
        wiped = self.copy('wiped-index.sqlite')
        self.edit(wiped, 'DELETE FROM messages_fts_data')
        self.edit(wiped, 'DELETE FROM messages_fts_docsize')
        receipt = self.rehearse(wiped)
        self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_FAILED')
        integrity = self.check(receipt, 'integrity_check')
        if integrity['status'] == 'FAIL':
            # SQLite 3.44+ lets PRAGMA integrity_check inspect FTS5 shadow tables. Depending on the
            # build it either reports rows ('malformed inverted index for FTS5 table ...',
            # 'fts5: corruption found ...') or raises while reading the damaged index (observed with
            # 3.45.1); both outcomes gate the remaining checks.
            self.assertIn(integrity['result'], ('NOT_OK', 'OPEN_ERROR'))
            if integrity['result'] == 'NOT_OK':
                self.assertTrue(any('fts5' in message.lower() for message in integrity['messages']))
            else:
                self.assertIn('Error', integrity['error'])
            self.assertEqual(receipt['failed_checks'], list(recovery.CHECKS))
        else:
            # Older bundled SQLite reports ok; the lost index surfaces in the FTS checks.
            self.assertIn('fts_rows', receipt['failed_checks'])
            self.assertIn('fts_match_sample', receipt['failed_checks'])
            self.assertEqual(self.check(receipt, 'fts_rows')['fts_rows'], 0)
            self.assertEqual(self.check(receipt, 'messages_digest')['status'], 'PASS')

    def test_exclusive_outputs_refuse_existing_paths_and_dangling_links(self):
        before = self.manifest.read_bytes()
        with self.assertRaises(FileExistsError):
            declare_recovery(self.db, self.manifest)
        self.assertEqual(self.manifest.read_bytes(), before)
        restored = self.copy()
        receipt = self.rehearse(restored)
        output = self.root / f'receipt-{self.counter}.json'
        saved = output.read_bytes()
        with self.assertRaises(FileExistsError):
            rehearse_recovery(self.manifest, restored, output)
        self.assertEqual(output.read_bytes(), saved)
        with self.assertRaises(FileExistsError):
            rehearse_recovery(self.manifest, restored, self.objects)
        with self.assertRaises(OSError):
            rehearse_recovery(self.manifest, restored, self.root / 'missing-directory' / 'receipt.json')
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if path.name.startswith('.recap')), [])
        self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_PASSED')

    def test_exclusive_outputs_refuse_dangling_symlinks(self):
        restored = self.copy()
        dangling = self.root / 'dangling.json'
        symlink_or_skip(self, self.root / 'never-created.json', dangling)
        with self.assertRaises(FileExistsError):
            rehearse_recovery(self.manifest, restored, dangling)
        with self.assertRaises(FileExistsError):
            declare_recovery(self.db, dangling)
        self.assertFalse((self.root / 'never-created.json').exists())
        self.assertTrue(dangling.is_symlink())
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if path.name.startswith('.recap')), [])

    def test_rehearsal_and_declaration_never_write_the_archive(self):
        restored = self.copy()
        before = restored.read_bytes()
        listing = sorted(path.name for path in self.root.iterdir())
        receipt = self.rehearse(restored, self.objects)
        self.assertEqual(restored.read_bytes(), before)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), sorted(listing + ['receipt-1.json']))
        self.assertFalse(receipt['restored_archive_written'])
        live = self.db.read_bytes()
        declare_recovery(self.db, self.root / 'second-manifest.json', '2026-11-09')
        self.assertEqual(self.db.read_bytes(), live)
        with closing(sqlite3.connect(restored)) as connection:
            self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0], 'delete')

    def test_cli_roundtrip_ascii_stdout_parity_and_exit_codes(self):
        environment = dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0')
        restored = self.copy()

        def call(script, *args, code=0):
            result = subprocess.run([sys.executable, script, *map(str, args)], cwd=ROOT, capture_output=True,
                                    env=environment, timeout=30)
            self.assertEqual(result.returncode, code, result.stderr)
            self.assertNotIn(b'Traceback', result.stderr)
            self.assertTrue(result.stdout.isascii())
            return result

        unified = call('recap.py', '--db', self.db, 'declare-recovery', '--output', self.root / 'cli-manifest.json',
                       '--declared-at', '2026-11-08')
        standalone = call('recovery.py', 'declare', '--db', self.db, '--output', self.root / 'cli-manifest-2.json',
                          '--declared-at', '2026-11-08')
        self.assertEqual(json.loads(unified.stdout), json.loads(standalone.stdout))
        self.assertEqual(json.loads(unified.stdout)['manifest_sha256'], self.declaration['manifest_sha256'])
        self.assertEqual((self.root / 'cli-manifest.json').read_bytes(), self.manifest.read_bytes())
        passing = call('recap.py', 'rehearse-recovery', self.manifest, '--restored-db', restored,
                       '--output', self.root / 'cli-pass.json', '--objects', self.objects)
        parity = call('recovery.py', 'rehearse', self.manifest, '--restored-db', restored,
                      '--output', self.root / 'cli-pass-2.json', '--objects', self.objects)
        self.assertEqual(json.loads(passing.stdout), json.loads(parity.stdout))
        self.assertEqual(json.loads(passing.stdout)['status'], 'RECOVERY_REHEARSAL_PASSED')
        self.assertEqual((self.root / 'cli-pass.json').read_bytes(), (self.root / 'cli-pass-2.json').read_bytes())
        self.assertEqual(passing.stderr, b'')
        self.edit(restored, "UPDATE messages SET timestamp='changed' WHERE message_id='u2'")
        failing = call('recap.py', 'rehearse-recovery', self.manifest, '--restored-db', restored,
                       '--output', self.root / 'cli-fail.json', code=1)
        self.assertEqual(json.loads(failing.stdout)['failed_checks'], ['messages_digest'])
        self.assertEqual(failing.stderr, b'')
        self.assertTrue((self.root / 'cli-fail.json').is_file())
        refused = call('recap.py', 'rehearse-recovery', self.manifest, '--restored-db', restored,
                       '--output', self.root / 'cli-fail.json', code=1)
        self.assertEqual(refused.stdout, b'')
        self.assertIn(b'already exists', refused.stderr)
        missing = call('recap.py', 'rehearse-recovery', self.manifest, '--restored-db', self.root / 'absent.sqlite',
                       '--output', self.root / 'never.json', code=1)
        self.assertEqual(missing.stdout, b'')
        self.assertFalse((self.root / 'never.json').exists())
        call('recap.py', '--db', self.db, 'rehearse-recovery', self.manifest, '--restored-db', restored,
             '--output', self.root / 'never.json', code=2)
        usage = call('recap.py', 'declare-recovery', '--output', self.root / 'never.json', code=2)
        self.assertIn(b'--db is required', usage.stderr)
        self.assertFalse((self.root / 'never.json').exists())
        helps = call('recap.py', '--help').stdout.decode('ascii')
        for command in ('declare-recovery', 'rehearse-recovery', 'inspect', 'import', 'review-titles', 'preview-title'):
            self.assertIn(command, helps)

    def test_text_output_quotes_control_and_format_characters_from_data(self):
        label = 'evil\x1b[31m\n‮\x7f label 합성'
        restored = self.copy()
        self.edit(restored, 'INSERT INTO artifacts VALUES(?,?,?,?)', label, 'f' * 64, 7, 1)
        environment = dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0')
        result = subprocess.run([sys.executable, 'recap.py', 'rehearse-recovery', str(self.manifest), '--restored-db',
                                 str(restored), '--output', str(self.root / 'text-receipt.json'), '--text'],
                                cwd=ROOT, capture_output=True, env=environment, timeout=30)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, b'')
        # The console text layer may add CR on Windows; the rendered text itself uses LF only.
        text = result.stdout.decode('ascii').replace('\r\n', '\n')
        self.assertTrue(no_data_controls(text))
        self.assertTrue(text.startswith('Recovery rehearsal receipt\n'))
        self.assertIn('status: "RECOVERY_REHEARSAL_FAILED"', text)
        self.assertIn('\\u001b[31m\\n\\u202e\\u007f label \\ud569\\uc131', text)
        self.assertIn('check artifact_rows: ["FAIL"', text)
        self.assertIn('check source_counts: ["FAIL"', text)
        receipt = json.loads((self.root / 'text-receipt.json').read_bytes().decode('utf-8'))
        self.assertEqual(self.check(receipt, 'source_counts')['undeclared_sources'], [label])
        rendered = render_text(receipt)
        self.assertTrue(no_data_controls(rendered))
        # One header, one line per top-level field except the expanded checks, one line per check.
        self.assertEqual(len(text.splitlines()), 1 + len(RECEIPT_FIELDS) - 1 + len(STDOUT_EXTRA) + len(recovery.CHECKS))
        declared = subprocess.run([sys.executable, 'recap.py', '--db', str(self.db), 'declare-recovery', '--output',
                                   str(self.root / 'text-manifest.json'), '--text'],
                                  cwd=ROOT, capture_output=True, env=environment, timeout=30)
        self.assertEqual(declared.returncode, 0, declared.stderr)
        summary = declared.stdout.decode('ascii').replace('\r\n', '\n')
        self.assertTrue(no_data_controls(summary))
        self.assertTrue(summary.startswith('Recovery manifest declaration\nschema: "recap.recovery-declaration.v1"\n'))
        self.assertIn('declared_at: null\n', summary)
        self.assertNotIn('demo', summary)
        for character in render_text(self.declaration):
            self.assertNotIn(unicodedata.category(character), ('Cf', 'Zl', 'Zp'))

    def test_manifest_validation_rejects_unknown_schema_and_malformed_documents(self):
        document = json.loads(self.manifest.read_bytes().decode('utf-8'))
        restored = self.copy()

        def rejected(mutate, pattern):
            value = json.loads(json.dumps(document))
            mutate(value)
            path = self.root / 'edited-manifest.json'
            if path.exists():
                path.unlink()
            path.write_bytes(json.dumps(value, ensure_ascii=False).encode('utf-8'))
            with self.assertRaisesRegex(ValueError, pattern):
                self.rehearse(restored, manifest=path)
            self.assertFalse((self.root / f'receipt-{self.counter}.json').exists())

        rejected(lambda v: v.update(schema='recap.recovery-manifest.v2'), 'unsupported recovery manifest schema')
        rejected(lambda v: v.pop('fts_rows'), 'exactly the declared fields')
        rejected(lambda v: v.update(unexpected=1), 'exactly the declared fields')
        rejected(lambda v: v.update(messages_sha256='XYZ'), 'malformed')
        rejected(lambda v: v.update(messages=True), 'malformed')
        rejected(lambda v: v.update(declared_at='2026-13-01'), 'declared_at')
        rejected(lambda v: v['artifacts'][0].pop('bytes'), 'artifact rows')
        rejected(lambda v: v['sources'][1]['original_hashes'].append('0' * 64), 'sorted distinct')
        rejected(lambda v: v['sources'].append(dict(v['sources'][0])), 'source entries')
        rejected(lambda v: v.update(optional_artifacts=[dict(source_id='demo', sha256='1' * 64)]), 'optional_artifacts')
        rejected(lambda v: v.update(title_history=dict(count=1)), 'title_history')
        rejected(lambda v: v.update(export_occurrences=None), 'without an occurrence ledger')
        bad = self.root / 'not-json.json'
        bad.write_bytes(b'\xff\xfe not utf-8')
        with self.assertRaisesRegex(ValueError, 'UTF-8 JSON'):
            self.rehearse(restored, manifest=bad)
        bad.write_bytes(b'[1, 2]')
        with self.assertRaisesRegex(ValueError, 'JSON object'):
            self.rehearse(restored, manifest=bad)
        with patch.object(recovery, 'MAX_MANIFEST_BYTES', 100):
            with self.assertRaisesRegex(ValueError, '64 MiB'):
                self.rehearse(restored)
        with self.assertRaises(OSError):
            self.rehearse(restored, manifest=self.root / 'absent-manifest.json')
        tolerant = self.root / 'bom-manifest.json'
        tolerant.write_bytes(b'\xef\xbb\xbf' + self.manifest.read_bytes())
        receipt = self.rehearse(restored, manifest=tolerant)
        self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_PASSED')
        self.assertEqual(receipt['manifest']['bytes'], self.manifest.stat().st_size + 3)

    def test_declared_at_is_validated_and_recorded_as_supplied(self):
        for value in ('2026/11/08', '20261108', '', '2026-11-08T00:00', '2026-00-10', '2026-11-32', 20261108):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'declared_at'):
                    declare_recovery(self.db, self.root / 'never-manifest.json', value)
                self.assertFalse((self.root / 'never-manifest.json').exists())
        declaration = declare_recovery(self.db, self.root / 'dated.json', '0001-01-31')
        self.assertEqual(declaration['declared_at'], '0001-01-31')
        self.assertEqual(json.loads((self.root / 'dated.json').read_bytes().decode('utf-8'))['declared_at'], '0001-01-31')
        unrelated = self.root / 'unrelated.sqlite'
        with closing(sqlite3.connect(unrelated)) as connection, connection:
            connection.execute('CREATE TABLE unrelated (value TEXT)')
        with self.assertRaisesRegex(ValueError, 'expected tables'):
            declare_recovery(unrelated, self.root / 'never-manifest.json')
        self.assertFalse((self.root / 'never-manifest.json').exists())
        # A non-SQLite path is a clean SQLite error at the CLI boundary, not a traceback.
        with self.assertRaises(sqlite3.Error):
            declare_recovery(self.root / 'dated.json', self.root / 'never-manifest.json')
        with self.assertRaises(sqlite3.Error):
            declare_recovery(self.root / 'absent.sqlite', self.root / 'never-manifest.json')
        self.assertFalse((self.root / 'absent.sqlite').exists())
        self.assertFalse((self.root / 'never-manifest.json').exists())

    def test_documented_rehearsal_commands_execute_exactly_as_written(self):
        document = (ROOT / 'docs/RECOVERY_REHEARSAL.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', document, re.S)
        self.assertEqual(len(blocks), 1)
        output = self.root / 'recovery output'
        output.mkdir()
        environment = dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0')
        outputs = []
        for line in blocks[0].strip().splitlines():
            tokens = shlex.split(line)
            self.assertEqual(tokens[:2], ['python', 'recap.py'])
            self.assertIn('OUTPUT', line)
            argv = [sys.executable] + [token.replace('OUTPUT', str(output)) for token in tokens[1:]]
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, env=environment, timeout=60)
            self.assertEqual(result.returncode, 0, line + '\n' + result.stderr.decode('utf-8'))
            self.assertEqual(result.stderr, b'')
            self.assertTrue(result.stdout.isascii())
            outputs.append((tokens, result.stdout.decode('ascii').replace('\r\n', '\n')))
        self.assertEqual([tokens[2] if tokens[2] != '--db' else tokens[4] for tokens, _ in outputs],
                         ['ingest', 'declare-recovery', 'rehearse-recovery', 'rehearse-recovery'])
        declaration = json.loads(outputs[1][1])
        self.assertEqual((declaration['sources'], declaration['artifacts'], declaration['messages'],
                          declaration['declared_at']), (1, 1, 2, '2026-11-08'))
        receipt = json.loads(outputs[2][1])
        self.assertEqual(receipt['status'], 'RECOVERY_REHEARSAL_PASSED')
        # The path is recorded exactly as supplied: the placeholder substitution, not a normalized form.
        self.assertEqual(receipt['restored']['path'], str(output) + '/archive.sqlite')
        self.assertEqual(receipt['objects_directory'], 'examples')
        objects = self.check(receipt, 'declared_objects')
        # Every regular file under examples/ is hashed, including any bytecode cache left by other tests.
        example_files = sum(1 for path in (ROOT / 'examples').rglob('*') if path.is_file())
        self.assertEqual((objects['declared'], objects['present'], objects['files_hashed']), (1, 1, example_files))
        self.assertGreaterEqual(example_files, 14)
        self.assertEqual(objects['objects'][0]['sha256'], hashlib.sha256((ROOT / 'examples/conversations.jsonl').read_bytes()).hexdigest())
        summary = outputs[3][1]
        self.assertTrue(summary.startswith('Recovery rehearsal receipt\n'))
        self.assertIn('status: "RECOVERY_REHEARSAL_PASSED"', summary)
        self.assertIn('objects_directory: null', summary)
        self.assertTrue(no_data_controls(summary))
        self.assertEqual(sorted(path.name for path in output.iterdir()),
                         ['archive.sqlite', 'recovery-manifest.json', 'recovery-receipt-summary.json', 'recovery-receipt.json'])
        saved = json.loads((output / 'recovery-receipt.json').read_bytes().decode('utf-8'))
        self.assertEqual(saved['status'], 'RECOVERY_REHEARSAL_PASSED')
        # Hashing the repository's example directory leaves no staging or receipt files behind.
        self.assertEqual([path.name for path in (ROOT / 'examples').rglob('*')
                          if path.name.startswith('.recap') or path.suffix == '.sqlite'], [])
        for section in ('## Acceptance criteria mapped to checks', '## What a FAILED receipt looks like',
                        '## Limits', '## Boundary', 'RECOVERY_REHEARSAL_FAILED', 'not a backup'):
            self.assertIn(section, document)


if __name__ == '__main__':
    unittest.main()
