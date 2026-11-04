"""Synthetic archive-aware diagnostics without changing import admission rules."""
import copy
import hashlib
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from import_check import check_import
from recap import readonly
from session_workflow import import_export, titles


class ImportCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.path = self.root / 'synthetic.json'
        self.db = self.root / 'archive.sqlite'
        self.records = [dict(id='PRIVATE_CONVERSATION', title='PRIVATE_TITLE', mapping={
            'PRIVATE_NODE_'+str(i): dict(parent=None, message=dict(author=dict(role='user'),
                create_time=i, content=dict(parts=['PRIVATE_BODY_'+str(i)]))) for i in range(2)})]
        self.write(); import_export(self.db, 'demo', self.path, 'web')

    def write(self):
        self.path.write_text(json.dumps(self.records), encoding='utf-8')

    def check(self, **kwargs):
        return check_import(self.db, kwargs.pop('source', 'demo'), self.path, kwargs.pop('kind', 'web'), **kwargs)

    def test_identical_and_other_source_new_counts_without_writes(self):
        before = self.db.read_bytes(), self.path.read_bytes()
        result = self.check()
        self.assertEqual(result['archive_comparison'], dict(new=0, identical=2, conflicting=0))
        self.assertEqual(result['status'], 'NO_CONFLICTS')
        self.assertEqual(result['records'], 2); self.assertEqual(result['unique_identities'], 2)
        self.assertEqual(result['total_conflicts'], 0)
        self.assertEqual(self.check(source='other')['archive_comparison'], dict(new=2, identical=0, conflicting=0))
        self.assertEqual(before, (self.db.read_bytes(), self.path.read_bytes()))

    def test_title_only_conflicts_remain_blocking_and_values_are_not_emitted(self):
        self.records[0]['title'] = 'PRIVATE_CHANGED_TITLE'; self.write()
        before = self.db.read_bytes(); result = self.check(limit=1)
        self.assertEqual(result['status'], 'CONFLICTS')
        self.assertEqual(result['conflict_classifications']['title_only'], 2)
        self.assertEqual(result['conflict_samples'], [dict(record=1, comparison='archive',
            classification='title_only', changed_fields=['title'])])
        self.assertEqual(result['omitted_conflicts'], 1)
        self.assertNotIn('PRIVATE_', json.dumps(result))
        with self.assertRaisesRegex(ValueError, 'conflicting message identity'):
            import_export(self.db, 'demo', self.path, 'web')
        self.assertEqual(self.db.read_bytes(), before)

    def test_classifications_cover_text_role_timestamp_and_mixtures(self):
        original = copy.deepcopy(self.records)
        cases = [('text', ['text'], 'text_changed'), ('role', ['role'], 'metadata_changed'),
                 ('time', ['timestamp'], 'metadata_changed'),
                 ('mixed', ['role', 'timestamp', 'title', 'text'], 'text_changed')]
        for case, fields, category in cases:
            with self.subTest(case=case):
                self.records = copy.deepcopy(original); message = self.records[0]['mapping']['PRIVATE_NODE_0']['message']
                if case in ('text', 'mixed'): message['content']['parts'] = ['PRIVATE_CHANGED_BODY']
                if case in ('role', 'mixed'): message['author']['role'] = 'tool'
                if case in ('time', 'mixed'): message['create_time'] = 999
                if case == 'mixed': self.records[0]['title'] = 'PRIVATE_CHANGED_TITLE'
                self.write(); sample = self.check()['conflict_samples'][0]
                self.assertEqual(sample['changed_fields'], fields)
                self.assertEqual(sample['classification'], category)

    def test_input_repetitions_are_separate_from_unique_archive_counts(self):
        first = copy.deepcopy(self.records[0]); first['mapping'].pop('PRIVATE_NODE_1')
        repeated = copy.deepcopy(first); contradictory = copy.deepcopy(first)
        contradictory['mapping']['PRIVATE_NODE_0']['message']['content']['parts'] = ['PRIVATE_CONTRADICTION']
        self.records = [first, repeated, contradictory]; self.write()
        result = self.check(source='new-source')
        self.assertEqual(result['records'], 3); self.assertEqual(result['unique_identities'], 1)
        self.assertEqual(result['archive_comparison'], dict(new=1, identical=0, conflicting=0))
        self.assertEqual(result['repeated_input'], dict(identical=1, conflicting=1))
        self.assertEqual(result['conflict_samples'], [dict(record=3, first_record=1, comparison='input',
            classification='text_changed', changed_fields=['text'])])

    def test_first_archive_conflict_and_input_conflict_count_separately(self):
        first = copy.deepcopy(self.records[0]); first['mapping'].pop('PRIVATE_NODE_1')
        changed = copy.deepcopy(first); changed['title'] = 'PRIVATE_CHANGED_TITLE'
        self.records = [changed, first]; self.write()
        result = self.check()
        self.assertEqual(result['archive_comparison']['conflicting'], 1)
        self.assertEqual(result['repeated_input']['conflicting'], 1)
        self.assertEqual(result['total_conflicts'], 2)
        self.assertEqual([s['comparison'] for s in result['conflict_samples']], ['archive', 'input'])

    def test_new_rows_before_conflict_do_not_get_imported(self):
        new = copy.deepcopy(self.records[0]); new['id'] = 'PRIVATE_NEW'
        self.records.insert(0, new); self.records[1]['title'] = 'PRIVATE_CHANGED_TITLE'; self.write()
        before = self.db.read_bytes(); result = self.check()
        self.assertEqual(result['archive_comparison'], dict(new=2, identical=0, conflicting=2))
        self.assertEqual(result['conflict_samples'][0]['record'], 3)
        self.assertEqual(self.db.read_bytes(), before)

    def test_display_overrides_and_all_archive_tables_remain_unchanged(self):
        titles(self.db, 'demo', 'PRIVATE_CONVERSATION', 'PRIVATE_OVERRIDE', 0)
        with closing(sqlite3.connect(self.db)) as connection:
            before_sql = list(connection.iterdump())
        before = self.db.read_bytes(); self.assertEqual(self.check()['status'], 'NO_CONFLICTS')
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(list(connection.iterdump()), before_sql)
        self.assertEqual(self.db.read_bytes(), before)

    def test_local_profiles_count_raw_repeated_occurrences(self):
        records = [dict(type='session_meta', payload=dict(id='synthetic')),
            dict(type='response_item', payload=dict(type='message', id='u', role='user',
                content=[dict(type='input_text', text='Synthetic question')]))]
        records.append(copy.deepcopy(records[1]))
        self.path.write_bytes(('\r'.join(json.dumps(r) for r in records)+'\r').encode())
        for kind in ('local', 'local-codex'):
            import_export(self.db, kind, self.path, kind)
            result = self.check(source=kind, kind=kind)
            self.assertEqual(result['archive_comparison']['identical'], 1)
            self.assertEqual(result['repeated_input']['identical'], 1)

    def test_selected_scope_hash_and_normalized_record_numbers(self):
        extra = copy.deepcopy(self.records[0]); extra['id'] = 'unselected'
        self.records.insert(0, extra); self.records[1]['title'] = 'PRIVATE_CHANGED_TITLE'; self.write()
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        result = self.check(conversation='PRIVATE_CONVERSATION', expected_export_sha256=digest)
        self.assertEqual(result['records'], 2); self.assertEqual(result['conflict_samples'][0]['record'], 1)
        self.assertEqual(result['coverage']['selection']['excluded_messages'], 2)
        self.assertEqual(result['coverage']['expected_export_sha256'], digest)
        self.path.write_bytes(self.path.read_bytes()+b' ')
        with patch('import_check.readonly', side_effect=AssertionError('no DB before hash validation')):
            with self.assertRaisesRegex(ValueError, 'changed after inspection'):
                self.check(conversation='PRIVATE_CONVERSATION', expected_export_sha256=digest)
            with self.assertRaises(ValueError): self.check(conversation='missing')

    def test_invalid_options_before_read_and_missing_database_not_created(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('no source read')):
            for limit in (0, 1001, -1, True, 1.0, None):
                with self.assertRaises(ValueError): self.check(limit=limit)
            for source in ('', ' ', None, 1):
                with self.assertRaises(ValueError): self.check(source=source)
        missing = self.root / 'missing.sqlite'
        with self.assertRaises(sqlite3.Error): check_import(missing, 'demo', self.path, 'web')
        self.assertFalse(missing.exists())
        malformed = self.root / 'not-an-archive.sqlite'; malformed.write_bytes(b'not a database')
        before = malformed.read_bytes()
        with self.assertRaises(sqlite3.Error): check_import(malformed, 'demo', self.path, 'web')
        self.assertEqual(malformed.read_bytes(), before)

    def test_source_read_once_and_empty_input_validates_archive_schema(self):
        reader = Path.read_bytes; calls = []
        def tracked(path):
            if path == self.path: calls.append(path)
            return reader(path)
        with patch.object(Path, 'read_bytes', tracked): self.check()
        self.assertEqual(len(calls), 1)
        self.records = []; self.write()
        result = self.check(); self.assertEqual(result['records'], 0)
        self.assertEqual(result['status'], 'NO_CONFLICTS')
        empty = self.root / 'empty.sqlite'
        with closing(sqlite3.connect(empty)): pass
        with self.assertRaises(sqlite3.Error): check_import(empty, 'demo', self.path, 'web')

    def test_wal_snapshot_keeps_all_identity_comparisons_consistent(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        changed, reads = [], []
        def traced(db):
            connection = readonly(db)
            def trace(sql):
                if sql.startswith('SELECT role,timestamp,title,text FROM messages WHERE'):
                    reads.append(sql)
                    if len(reads) == 2:
                        with closing(sqlite3.connect(self.db)) as writer, writer:
                            writer.execute("UPDATE messages SET text='PRIVATE_CHANGED_BODY'")
                        changed.append(True)
            connection.set_trace_callback(trace)
            return connection
        with patch('import_check.readonly', traced): result = self.check()
        self.assertEqual(changed, [True]); self.assertEqual(result['archive_comparison']['identical'], 2)
        self.assertEqual(self.check()['conflict_classifications']['text_changed'], 2)

    def test_clear_report_cannot_override_a_later_archive_change(self):
        self.assertFalse(self.check()['conflicts_found'])
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE messages SET title='PRIVATE_LATER_TITLE'")
        before = self.db.read_bytes()
        with self.assertRaisesRegex(ValueError, 'conflicting message identity'):
            import_export(self.db, 'demo', self.path, 'web')
        self.assertEqual(self.db.read_bytes(), before)

    def test_both_cli_json_parity_exit_status_and_no_mutation(self):
        for conflicts in (False, True):
            if conflicts: self.records[0]['title'] = 'PRIVATE_CHANGED_TITLE'; self.write()
            before = self.db.read_bytes(); outputs = []
            for script, command in (('recap.py', ['check-import']), ('import_check.py', [])):
                result = subprocess.run([sys.executable, script, '--db', str(self.db), *command,
                    str(self.path), '--source', 'demo', '--format', 'web', '--limit', '1'],
                    capture_output=True, env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=20)
                self.assertEqual(result.returncode, int(conflicts)); self.assertEqual(result.stderr, b'')
                outputs.append(json.loads(result.stdout.decode('ascii')))
            self.assertEqual(outputs[0], outputs[1]); self.assertEqual(outputs[0]['conflicts_found'], conflicts)
            self.assertEqual(self.db.read_bytes(), before)

    def test_documented_commands_execute_in_new_private_scratch_directory(self):
        document = Path('docs/IMPORT_CONFLICTS.md').read_text(encoding='utf-8')
        destination = self.root / 'documented'; outputs = []
        for block in re.findall(r'```sh\n(.*?)```', document, re.S):
            for line in block.strip().splitlines():
                command = [part.replace('../recap-conflict-demo', str(destination)) for part in shlex.split(line)]
                if command[0] == 'mkdir':
                    Path(command[1]).mkdir(); continue
                self.assertEqual(command[0], 'python')
                result = subprocess.run([sys.executable, *command[1:]], capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                outputs.append(json.loads(result.stdout))
        self.assertEqual(len(outputs), 3)
        self.assertEqual(outputs[1], outputs[2])
        self.assertEqual(outputs[1]['archive_comparison']['identical'], 2)

    def test_cli_failures_have_no_success_json_or_new_database(self):
        missing = self.root / 'missing.sqlite'
        for script, command in (('recap.py', ['check-import']), ('import_check.py', [])):
            for options in ([], ['--expected-export-sha256', '0'*64], ['--limit', '0']):
                result = subprocess.run([sys.executable, script, '--db', str(missing), *command,
                    str(self.path), '--source', 'demo', '--format', 'web', *options],
                    capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b''); self.assertTrue(result.stderr)
                self.assertNotIn(b'Traceback', result.stderr); self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
