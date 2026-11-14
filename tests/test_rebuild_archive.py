"""Synthetic declared-object replay and exclusive publication contracts."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recaplib.archive import ingest_bytes
from recaplib import rebuild, recovery
from recaplib.session_workflow import import_export_bytes, titles

ROOT = Path(__file__).resolve().parents[1]


class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.objects = self.root / 'objects'
        self.objects.mkdir()
        self.live = self.root / 'original.sqlite'
        self.manifest = self.root / 'manifest.json'
        self.plan = self.root / 'plan.json'
        self.db = self.root / 'rebuilt.sqlite'
        self.output = self.root / 'receipt.json'

    def step(self, kind='normalized', name='conversations.jsonl', label=None, newline='lf', source='demo'):
        raw = (ROOT / 'examples' / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        (self.objects / digest).write_bytes(raw)
        if kind == 'normalized':
            ingest_bytes(self.live, source, raw)
        else:
            import_export_bytes(self.live, source, raw, label, kind, newline=newline)
        return dict(source=source, kind=kind, object_sha256=digest, label=label, conversation=None, newline=newline)

    def declare(self, steps):
        recovery.declare_recovery(self.live, self.manifest)
        self.plan.write_text(json.dumps(dict(schema=rebuild.PLAN_SCHEMA, steps=steps)), encoding='utf-8')

    def run_rebuild(self):
        return rebuild.rebuild_archive(self.manifest, self.plan, self.objects, self.db, self.output)

    def test_normalized_success_original_immutable_and_no_staging(self):
        self.declare([self.step()])
        before = self.live.read_bytes()
        result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.PASSED)
        self.assertEqual(before, self.live.read_bytes())
        self.assertFalse(os.path.samefile(self.live, self.db))
        self.assertTrue(result['new_database_created_exclusively'])
        self.assertFalse(result['live_archive_read'])
        self.assertEqual(result['clean_destination_verified'], 'NOT_ESTABLISHED')
        self.assertEqual(result['review_state'], 'NOT_DECLARED_NOT_RESTORED')
        self.assertTrue(result['staging_cleanup_complete'])
        self.assertFalse(list(self.root.glob('.recap-*')))
        self.assertEqual(len(result['implementation_sha256']), 7)
        self.assertTrue(all(len(v) == 64 for v in result['implementation_sha256'].values()))
        self.assertEqual(json.loads(self.output.read_bytes())['status'], rebuild.PASSED)

    def test_all_adapter_kinds_and_original_labels(self):
        steps = [self.step('web', 'web-export.json', None, 'crlf', 'web'),
                 self.step('local', 'local-session.jsonl', 'original-label.jsonl', 'lf', 'local'),
                 self.step('local-codex', 'rollback-session.jsonl', 'original-label.jsonl', 'crlf', 'codex')]
        self.declare(steps)
        result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.PASSED)
        self.assertEqual(len(result['steps']), 3)
        self.assertNotIn('coverage', result['steps'][0])

    def test_wrong_newline_or_label_never_publishes(self):
        self.declare([self.step('local', 'local-session.jsonl', 'original.jsonl')])
        plan = json.loads(self.plan.read_bytes())
        plan['steps'][0]['newline'] = 'crlf'
        self.plan.write_text(json.dumps(plan))
        result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.FAILED)
        self.assertIn('messages_digest', result['failed_checks'])
        self.assertIn('artifact_rows', result['failed_checks'])
        self.assertFalse(self.db.exists())
        self.assertTrue(result['staging_cleanup_complete'])
        self.output.unlink()
        plan['steps'][0].update(newline='lf', label='wrong.jsonl')
        self.plan.write_text(json.dumps(plan))
        self.assertEqual(self.run_rebuild()['status'], rebuild.FAILED)
        self.assertFalse(self.db.exists())

    def test_declared_title_history_explicitly_excluded_not_passed(self):
        self.step('web', 'web-export.json')
        titles(self.live, 'demo', 'synthetic-chat', 'Synthetic renamed title')
        raw = (ROOT / 'examples/web-export.json').read_bytes()
        self.declare([dict(source='demo', kind='web', object_sha256=hashlib.sha256(raw).hexdigest(),
                           label=None, conversation=None, newline='lf')])
        result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.PASSED)
        self.assertEqual(result['not_rebuildable_from_objects'], ['title_history'])
        self.assertEqual(result['title_history'], 'NOT_REBUILDABLE_FROM_OBJECTS')
        self.assertNotIn('title_history', [c['check'] for c in result['checks']])
        expected = next(c for c in result['checks'] if c['check'] == 'expected_tables')
        self.assertNotIn('title_history', expected['expected'])

    def test_missing_and_undeclared_objects_fail_with_receipt(self):
        step = self.step()
        self.declare([step])
        (self.objects / step['object_sha256']).unlink()
        result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.FAILED)
        self.assertIn('declared_objects', result['failed_checks'])
        self.assertFalse(self.db.exists())
        self.output.unlink()
        step['source'] = 'not-declared'
        self.plan.write_text(json.dumps(dict(schema=rebuild.PLAN_SCHEMA, steps=[step])))
        result = self.run_rebuild()
        self.assertEqual(result['failure']['phase'], 'PLAN_OBJECT_DECLARATION')
        self.assertFalse(self.db.exists())

    def test_changed_snapshot_detected_after_inventory(self):
        step = self.step()
        self.declare([step])
        original = rebuild._object_bytes
        def changed(path, digest):
            Path(path).write_bytes(b'changed synthetic object')
            return original(path, digest)
        with patch.object(rebuild, '_object_bytes', side_effect=changed):
            result = self.run_rebuild()
        self.assertEqual(result['failure']['phase'], 'REPLAY')
        self.assertFalse(self.db.exists())
        self.assertFalse(list(self.root.glob('.recap-*')))

    def test_destination_and_sidecar_conflicts_are_preserved(self):
        self.declare([self.step()])
        for path in [self.db, self.output] + [Path(str(self.db) + suffix) for suffix in rebuild.SIDECARS]:
            path.write_bytes(b'keep synthetic contents')
            with self.subTest(path=path), self.assertRaises(FileExistsError):
                self.run_rebuild()
            self.assertEqual(path.read_bytes(), b'keep synthetic contents')
            path.unlink()
        with self.assertRaises(ValueError):
            rebuild.rebuild_archive(self.manifest, self.plan, self.objects, self.db, str(self.db) + '-wal')
        self.assertFalse(self.db.exists())

    def test_dangling_symlink_and_object_symlink_refused(self):
        self.declare([self.step()])
        try:
            self.db.symlink_to(self.root / 'missing')
        except OSError:
            self.skipTest('symlink creation unavailable')
        with self.assertRaises(FileExistsError):
            self.run_rebuild()
        self.assertTrue(self.db.is_symlink())
        self.db.unlink()
        (self.objects / 'link').symlink_to(self.root / 'missing')
        result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.FAILED)
        self.assertIn('SYMLINK_REFUSED', result['checks'][0]['refusals'])

    def test_link_failure_cleans_private_staging_and_retains_receipt(self):
        self.declare([self.step()])
        link = os.link
        def fail_db(source, destination):
            if Path(destination) == self.db:
                raise OSError('synthetic link unavailable')
            return link(source, destination)
        with patch.object(os, 'link', side_effect=fail_db):
            result = self.run_rebuild()
        self.assertEqual(result['failure']['phase'], 'DATABASE_PUBLICATION')
        self.assertFalse(self.db.exists())
        self.assertFalse(list(self.root.glob('.recap-*')))

    def test_receipt_failure_after_db_link_preserves_db(self):
        self.declare([self.step()])
        with patch.object(recovery, '_publish_new_file', side_effect=OSError('synthetic receipt failure')):
            with self.assertRaisesRegex(OSError, 'database was preserved'):
                self.run_rebuild()
        self.assertTrue(self.db.is_file())
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.recap-*')))

    def test_limits_and_strict_plan_validation(self):
        self.declare([self.step()])
        original = self.plan.read_bytes()
        malformed = [b'{"schema":"recap.rebuild-plan.v1","schema":"duplicate","steps":[]}',
                     json.dumps(dict(schema=rebuild.PLAN_SCHEMA, steps=[], extra=True)).encode(),
                     original.replace(b'"normalized"', b'"unsupported"'),
                     original.replace(b'"label": null', b'"label": "ignored"'),
                     original.replace(b'"newline": "lf"', b'"newline": null')]
        for raw in malformed:
            self.plan.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.run_rebuild()
            self.assertFalse(self.db.exists())
            self.assertFalse(self.output.exists())
        self.plan.write_bytes(original)
        with patch.object(rebuild, 'MAX_PLAN_BYTES', 1), self.assertRaises(ValueError):
            self.run_rebuild()
        with patch.object(rebuild, 'MAX_STEPS', 0), self.assertRaises(ValueError):
            self.run_rebuild()
        with patch.object(recovery, 'MAX_OBJECT_BYTES', 1):
            self.assertEqual(self.run_rebuild()['status'], rebuild.FAILED)
        self.assertFalse(self.db.exists())

    def test_plan_bom_and_empty_plan_for_empty_archive(self):
        connection = sqlite3.connect(self.live)
        connection.executescript(rebuild.SCHEMA)
        connection.close()
        self.declare([])
        self.plan.write_bytes(b'\xef\xbb\xbf' + self.plan.read_bytes())
        self.assertEqual(self.run_rebuild()['status'], rebuild.PASSED)

    def test_duplicate_hash_paths_choose_sorted_first(self):
        self.declare([self.step()])
        raw = (ROOT / 'examples/conversations.jsonl').read_bytes()
        (self.objects / '000-first').write_bytes(raw)
        paths = {}
        _, manifest = recovery._read_manifest(self.manifest)
        passed, _ = recovery._objects_check(manifest, self.objects, str(self.objects), paths)
        self.assertTrue(passed)
        self.assertEqual(paths[hashlib.sha256(raw).hexdigest()].name, '000-first')

    def test_reverse_plan_changes_first_identity_provenance(self):
        raw = (ROOT / 'examples/conversations.jsonl').read_bytes()
        steps = []
        for value in [raw, raw + b'\n']:
            digest = hashlib.sha256(value).hexdigest()
            (self.objects / digest).write_bytes(value)
            ingest_bytes(self.live, 'demo', value)
            steps.append(dict(source='demo', kind='normalized', object_sha256=digest, label=None,
                              conversation=None, newline='lf'))
        self.declare(list(reversed(steps)))
        result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.FAILED)
        self.assertIn('messages_digest', result['failed_checks'])
        self.assertFalse(self.db.exists())

    def test_failure_details_do_not_echo_parser_text(self):
        self.declare([self.step()])
        with patch.object(rebuild, 'ingest_bytes', side_effect=ValueError('PRIVATE_SYNTHETIC_BODY')):
            result = self.run_rebuild()
        self.assertNotIn('PRIVATE_SYNTHETIC_BODY', json.dumps(result))
        self.assertEqual(result['failure']['exception_type'], 'ValueError')

    def test_cli_rejects_global_db(self):
        run = subprocess.run([sys.executable, 'recap.py', '--db', str(self.live), 'rebuild-archive',
                              'unused', '--plan', 'unused', '--objects', 'unused', '--new-db', str(self.db),
                              '--output', str(self.output)], cwd=ROOT, capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertFalse(self.db.exists())

    def test_late_sidecar_conflict_preserves_user_file(self):
        self.declare([self.step()])
        checks = recovery._archive_checks
        sidecar = Path(str(self.db) + '-wal')
        def late(*args, **kwargs):
            result = checks(*args, **kwargs)
            sidecar.write_bytes(b'keep late synthetic sidecar')
            return result
        with patch.object(recovery, '_archive_checks', side_effect=late):
            result = self.run_rebuild()
        self.assertEqual(result['failure']['phase'], 'DATABASE_PUBLICATION')
        self.assertEqual(sidecar.read_bytes(), b'keep late synthetic sidecar')
        self.assertFalse(self.db.exists())

    def test_object_file_limit_refusal(self):
        self.declare([self.step()])
        with patch.object(recovery, 'MAX_OBJECT_FILES', 0):
            result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.FAILED)
        self.assertIn('TOO_MANY_FILES', result['checks'][0]['refusals'])

    def test_documented_commands_execute(self):
        document = (ROOT / 'docs/AUTOMATED_REBUILD.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', document, re.S)
        self.assertEqual(len(blocks), 1)
        output = self.root / 'guide output'
        output.mkdir()
        before = None
        for index, line in enumerate(blocks[0].strip().splitlines()):
            tokens = shlex.split(line)
            argv = [sys.executable] + [token.replace('OUTPUT', str(output)) for token in tokens[1:]]
            if index == 2:
                before = (output / 'archive.sqlite').read_bytes()
            run = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=60,
                                 env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0'))
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(run.stdout.isascii())
        self.assertEqual((output / 'archive.sqlite').read_bytes(), before)
        self.assertIn(b'REBUILD_REHEARSAL_PASSED', run.stdout)
        self.assertEqual(json.loads((output / 'rebuild-receipt.json').read_bytes())['status'], rebuild.PASSED)

    def test_cleanup_failure_is_reported_without_removing_published_db(self):
        self.declare([self.step()])
        unlink = Path.unlink
        def fail_staging(path, *args, **kwargs):
            if path.name.startswith('.recap-rebuild-') and path.name.endswith('.sqlite'):
                raise OSError('synthetic cleanup failure')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_staging):
            result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.PASSED)
        self.assertFalse(result['staging_cleanup_complete'])
        self.assertEqual(len(result['remaining_staging_files']), 1)
        leftover = self.root / result['remaining_staging_files'][0]
        self.assertTrue(leftover.is_file())
        self.assertTrue(self.db.is_file())
        self.assertTrue(self.output.is_file())
        self.assertTrue(os.path.samefile(leftover, self.db))
        leftover.unlink()
        self.assertTrue(self.db.is_file())

    def test_late_database_conflict_is_not_removed(self):
        self.declare([self.step()])
        checks = recovery._archive_checks
        def late(*args, **kwargs):
            result = checks(*args, **kwargs)
            self.db.write_bytes(b'keep late synthetic database')
            return result
        with patch.object(recovery, '_archive_checks', side_effect=late):
            result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.FAILED)
        self.assertFalse(result['new_database_created_exclusively'])
        self.assertEqual(self.db.read_bytes(), b'keep late synthetic database')

    def test_surrogate_filesystem_name_receipt_is_valid_json(self):
        if os.name != 'posix':
            self.skipTest('POSIX surrogate-escaped filesystem path case')
        self.declare([self.step()])
        self.db = self.root / 'rebuilt-\udcff.sqlite'
        result = self.run_rebuild()
        self.assertEqual(result['status'], rebuild.PASSED)
        self.assertTrue(self.db.is_file())
        saved = self.output.read_bytes()
        self.assertTrue(saved.isascii())
        self.assertEqual(json.loads(saved)['new_database'], str(self.db))

    def test_receipt_encoding_failure_reports_published_database(self):
        self.declare([self.step()])
        with patch.object(rebuild, '_encode_receipt', side_effect=ValueError('synthetic encoding failure')):
            with self.assertRaisesRegex(OSError, 'database was preserved'):
                self.run_rebuild()
        self.assertTrue(self.db.is_file())
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.recap-*')))
