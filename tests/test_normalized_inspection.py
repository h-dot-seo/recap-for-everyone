"""Synthetic normalized inspection, admission diagnostics and hash leases."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recap import validate_normalized
from recaplib.archive import ingest, ingest_bytes
from recaplib.import_check import check_import
from recaplib.session_workflow import inspect_export, import_export, normalize
from recaplib.export_inventory import list_export
from recaplib.title_plan import make_plan, check_plan, SCHEMA as PLAN_SCHEMA

ROOT = Path(__file__).resolve().parents[1]


class NormalizedInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.path = self.home / 'input.jsonl'
        self.db = self.home / 'archive.sqlite'

    def row(self, **values):
        result = dict(conversation_id='private-fictional-chat', message_id='private-fictional-message',
                      role='user', timestamp='fictional time', text='private synthetic orchard')
        result.update(values)
        return result

    def write(self, *rows, prefix=b'', separator=b'\n'):
        raw = prefix + separator.join(json.dumps(row).encode() for row in rows) + separator
        self.path.write_bytes(raw)
        return raw

    def run_cli(self, script, *args):
        return subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                              cwd=self.home, capture_output=True, text=True)

    def test_report_is_text_free_and_preserves_silent_acceptances(self):
        raw = self.write(self.row(text=' \t', origin_sha256='ignored', unused=float('nan')),
                         self.row(message_id='second', title='private title'),
                         prefix=b'\xef\xbb\xbf\r\n', separator=b'\r\n')
        records, report = validate_normalized(raw)
        self.assertEqual([item[2] for item in records], [2, 3])
        self.assertEqual(report['records'], 2)
        self.assertEqual(report['unique_identities'], 2)
        self.assertEqual(report['conversations'], 1)
        self.assertEqual(report['role_counts'], {'user': 2})
        self.assertEqual(report['records_with_ignored_members'], 1)
        self.assertEqual(report['whitespace_only_text_records'], 1)
        self.assertEqual(report['records_without_title'], 1)
        self.assertEqual(report['conversations_with_multiple_titles'], 1)
        self.assertTrue(report['utf8_bom_present'])
        self.assertEqual(report['original_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertNotIn('private', json.dumps(report))
        self.assertFalse(report['contains_message_text'])

    def test_inspect_reports_repeats_without_admitting_them(self):
        self.write(self.row(), self.row(), self.row(text='different'), self.row())
        result = inspect_export(self.path, 'normalized')
        self.assertEqual(result['repeated_input'], {'identical': 2, 'conflicting': 1})
        self.assertEqual(result['mode'], 'inspection only; no database access')
        self.assertFalse(self.db.exists())
        with self.assertRaisesRegex(ValueError, 'conflicting message identity at line 3'):
            ingest(self.db, 'fictional', self.path)
        self.assertFalse(self.db.exists())

    def test_empty_inputs_report_artifact_warning(self):
        for raw in (b'', b'\r\n \r', b'\xef\xbb\xbf'):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                result = inspect_export(self.path, 'normalized')
                self.assertEqual(result['records'], 0)
                self.assertEqual(result['conversations'], 0)
                self.assertTrue(result['warnings'])
                self.assertEqual('utf8_bom_present' in result, raw.startswith(b'\xef\xbb\xbf'))

    def test_structural_validation_matches_ingest(self):
        invalid = [b'[]', b'{"a":1,"a":2}', b'{', b'\xff',
                   json.dumps(self.row(title=None)).encode(),
                   json.dumps(self.row(role='unsupported')).encode(),
                   json.dumps(self.row(timestamp=0)).encode(),
                   json.dumps(self.row(text='')).encode(),
                   json.dumps(self.row(unused='\ud800')).encode()]
        for raw in invalid:
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                with self.assertRaises(ValueError) as inspection:
                    inspect_export(self.path, 'normalized')
                with self.assertRaises(ValueError) as ingestion:
                    ingest(self.db, 'fictional', self.path)
                self.assertEqual(str(inspection.exception), str(ingestion.exception))
                self.assertFalse(self.db.exists())

    def test_ingest_keeps_early_conflict_error_order(self):
        raw = self.write(self.row(), self.row(text='different')) + b'bad JSON\n'
        with self.assertRaisesRegex(ValueError, 'conflicting message identity at line 2'):
            ingest_bytes(self.db, 'fictional', raw)
        self.assertFalse(self.db.exists())

    def test_validator_requires_immutable_bytes(self):
        for raw in ('', bytearray(), None):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'immutable bytes'):
                validate_normalized(raw)

    def test_check_counts_archive_and_input_conflicts_without_mutation(self):
        ingest_bytes(self.db, 'fictional', self.write(self.row()))
        before = self.db.read_bytes()
        self.write(self.row(title='different'), self.row(title='different'),
                   self.row(text='different'), self.row(message_id='new'), prefix=b'\n\n')
        result = check_import(self.db, 'fictional', self.path, 'normalized', limit=1)
        self.assertEqual(result['archive_comparison'], {'new': 1, 'identical': 0, 'conflicting': 1})
        self.assertEqual(result['repeated_input'], {'identical': 1, 'conflicting': 1})
        self.assertEqual(result['total_conflicts'], 2)
        self.assertEqual(result['omitted_conflicts'], 1)
        self.assertEqual(result['conflict_samples'][0]['record'], 1)
        self.assertNotIn('private-fictional', json.dumps(result))
        self.assertEqual(self.db.read_bytes(), before)

    def test_check_requires_existing_archive_even_for_empty_file(self):
        self.path.write_bytes(b'')
        with self.assertRaises(sqlite3.Error):
            check_import(self.db, 'fictional', self.path, 'normalized')
        self.assertFalse(self.db.exists())

    def test_check_identical_and_other_source_remain_separate(self):
        self.write(self.row())
        ingest(self.db, 'fictional', self.path)
        self.assertEqual(check_import(self.db, 'fictional', self.path, 'normalized')['archive_comparison']['identical'], 1)
        self.assertEqual(check_import(self.db, 'another', self.path, 'normalized')['archive_comparison']['new'], 1)

    def test_normalized_selection_rejected_before_read_or_database(self):
        for conversation in ('private-fictional-chat', '', False):
            with self.subTest(conversation=conversation):
                with self.assertRaisesRegex(ValueError, 'does not support conversation'):
                    inspect_export(self.path, 'normalized', conversation)
                with self.assertRaisesRegex(ValueError, 'does not support conversation'):
                    check_import(self.db, 'fictional', self.path, 'normalized', conversation)
        self.assertFalse(self.db.exists())

    def test_shared_adapter_dispatcher_remains_closed(self):
        self.write(self.row())
        for call in (lambda: normalize(self.path, 'normalized'),
                     lambda: import_export(self.db, 'fictional', self.path, 'normalized'),
                     lambda: list_export(self.path, 'normalized'),
                     lambda: make_plan(self.db, 'fictional', 'private-fictional-chat', self.path, 'normalized')):
            with self.assertRaises(ValueError):
                call()
        self.assertFalse(self.db.exists())

    def test_hash_guard_success_retains_receipt_and_bytes(self):
        raw = self.write(self.row(), prefix=b'\xef\xbb\xbf\n', separator=b'\r\n')
        digest = hashlib.sha256(raw).hexdigest()
        report = inspect_export(self.path, 'normalized', expected_export_sha256=digest)
        self.assertEqual(report['expected_export_sha256'], digest)
        result = ingest(self.db, 'fictional', self.path, expected_sha256=digest)
        self.assertEqual(result, dict(source_sha256=digest, records=1, inserted=1, utf8_bom_present=True))
        self.assertEqual(check_import(self.db, 'fictional', self.path, 'normalized', expected_export_sha256=digest)['status'], 'NO_CONFLICTS')

    def test_hash_guard_rejects_mismatch_before_db_or_validation(self):
        self.path.write_bytes(b'bad JSON')
        for call in (lambda: ingest(self.db, 'fictional', self.path, expected_sha256='0'*64),
                     lambda: ingest_bytes(self.db, 'fictional', b'bad JSON', expected_sha256='0'*64),
                     lambda: inspect_export(self.path, 'normalized', expected_export_sha256='0'*64),
                     lambda: check_import(self.db, 'fictional', self.path, 'normalized', expected_export_sha256='0'*64)):
            with self.assertRaisesRegex(ValueError, 'changed after inspection'):
                call()
        self.assertFalse(self.db.exists())

    def test_hash_guard_mismatch_does_not_touch_existing_archive(self):
        self.write(self.row())
        ingest(self.db, 'fictional', self.path)
        before = self.db.read_bytes()
        with self.assertRaises(ValueError):
            ingest(self.db, 'fictional', self.path, expected_sha256='0'*64)
        self.assertEqual(self.db.read_bytes(), before)

    def test_hash_guard_rejects_malformed_hashes(self):
        raw = self.write(self.row())
        for digest in ('', 'A'*64, 'g'*64, '0'*63, False, 12):
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, 'lowercase SHA-256'):
                ingest_bytes(self.db, 'fictional', raw, expected_sha256=digest)
        self.assertFalse(self.db.exists())

    def test_single_read_for_each_path(self):
        raw = self.write(self.row())
        digest = hashlib.sha256(raw).hexdigest()
        for call in (lambda: inspect_export(self.path, 'normalized', expected_export_sha256=digest),
                     lambda: ingest(self.db, 'fictional', self.path, expected_sha256=digest),
                     lambda: check_import(self.db, 'fictional', self.path, 'normalized', expected_export_sha256=digest)):
            with patch.object(Path, 'read_bytes', return_value=raw) as read:
                call()
                self.assertEqual(read.call_count, 1)

    def test_cli_inspection_parity(self):
        self.write(self.row(), self.row(text='different'))
        first = self.run_cli('recap.py', 'inspect', self.path, '--format', 'normalized')
        second = self.run_cli('session_workflow.py', 'inspect', self.path, '--format', 'normalized')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))

    def test_cli_check_parity_and_conflict_exit(self):
        self.write(self.row())
        ingest(self.db, 'fictional', self.path)
        self.write(self.row(text='different'))
        common = [self.path, '--format', 'normalized', '--source', 'fictional']
        first = self.run_cli('recap.py', '--db', self.db, 'check-import', *common)
        second = self.run_cli('import_check.py', '--db', self.db, *common)
        self.assertEqual(first.returncode, 1, first.stderr)
        self.assertEqual(second.returncode, 1, second.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(second.stdout))

    def test_cli_ingest_guard(self):
        raw = self.write(self.row())
        args = ['--db', self.db, 'ingest', self.path, '--source', 'fictional', '--expected-sha256']
        failed = self.run_cli('recap.py', *args, '0'*64)
        self.assertEqual(failed.returncode, 1)
        self.assertFalse(self.db.exists())
        passed = self.run_cli('recap.py', *args, hashlib.sha256(raw).hexdigest())
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(json.loads(passed.stdout)['inserted'], 1)

    def test_cli_rejects_selection_and_other_format_paths(self):
        self.write(self.row())
        for args in (['inspect', self.path, '--format', 'normalized', '--conversation', 'fictional'],
                     ['--db', self.db, 'import', self.path, '--format', 'normalized', '--source', 'fictional'],
                     ['list-export', self.path, '--format', 'normalized']):
            result = self.run_cli('recap.py', *args)
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.db.exists())

    def test_omitted_title_and_ignored_members_compare_identically(self):
        self.write(self.row())
        ingest(self.db, 'fictional', self.path)
        self.write(self.row(title='', ignored='not stored'), self.row(origin_locator='not provenance'))
        result = check_import(self.db, 'fictional', self.path, 'normalized')
        self.assertEqual(result['status'], 'NO_CONFLICTS')
        self.assertEqual(result['archive_comparison']['identical'], 1)
        self.assertEqual(result['repeated_input'], {'identical': 1, 'conflicting': 0})

    def test_edited_title_plan_does_not_enable_normalized_format(self):
        self.write(self.row())
        plan = dict(schema=PLAN_SCHEMA, source='fictional', conversation='private-fictional-chat', format='normalized')
        with self.assertRaisesRegex(ValueError, 'unsupported format'):
            check_plan(self.db, self.path, plan)
        self.assertFalse(self.db.exists())
