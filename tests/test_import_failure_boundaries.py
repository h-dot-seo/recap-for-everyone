"""Synthetic deep-JSON and incoming-identity failures before archive creation."""
import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from recaplib.export_inventory import list_export
from recaplib.import_check import check_import
from recap import ingest, search
from recaplib.replay_local import reconstruct
from recaplib.session_workflow import import_export, inspect_export
from recaplib.strict_json import loads
from recaplib.title_plan import make_plan
from recaplib.web_branch import branch_view


from tests._nesting import deep_json


def normalized(**changes):
    return dict(dict(conversation_id='chat', message_id='u', role='user',
                     timestamp='synthetic', title='Original', text='Synthetic orchard'), **changes)


def web(text='Synthetic orchard'):
    return dict(id='chat', title='Original', current_node='u', mapping={
        'u': dict(parent=None, message=dict(author=dict(role='user'), create_time=0,
                                           content=dict(parts=[text])))})


def local():
    return [dict(type='session_meta', payload=dict(id='chat')),
            dict(type='response_item', timestamp='synthetic', payload=dict(type='message',
                 role='user', id='u', content=[dict(type='input_text', text='Synthetic orchard')]))]


class ImportFailureBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'synthetic.jsonl'
        self.db = self.root / 'existing.sqlite'
        self.missing = self.root / 'missing.sqlite'
        self.write_rows([normalized()])
        ingest(self.db, 'existing', self.path)

    def write_rows(self, rows, separator='\n', bom=False, initial_blank=False):
        text = (separator if initial_blank else '') + separator.join(json.dumps(r) for r in rows) + separator
        self.path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + text.encode())

    def assert_preconnection_failure(self, operation, regex=None):
        before = self.db.read_bytes(), self.path.read_bytes()
        with patch('recap.sqlite3.connect', side_effect=AssertionError('No database access before rejection')):
            for db in (self.missing, self.db):
                with self.assertRaisesRegex(ValueError, regex or '.') as caught:
                    operation(db)
                self.assertNotIn('SYNTHETIC_PRIVATE', str(caught.exception))
        self.assertFalse(self.missing.exists())
        self.assertEqual((self.db.read_bytes(), self.path.read_bytes()), before)

    def test_decoder_depth_errors_are_sanitized_and_do_not_raise_limits(self):
        before = sys.getrecursionlimit()
        # Do not assume a universal numeric object/array limit across Python
        # versions. Every decoder RecursionError must use the same safe boundary.
        with patch('recaplib.strict_json.json.loads', side_effect=RecursionError('SYNTHETIC_PRIVATE_KEY')):
            with self.assertRaisesRegex(ValueError, '^JSON nesting is too deep$'):
                loads('{}')
        self.assertEqual(sys.getrecursionlimit(), before)

    def test_actual_decoder_depth_error_is_sanitized(self):
        before = sys.getrecursionlimit()
        with self.assertRaisesRegex(ValueError, '^JSON nesting is too deep$'):
            loads(deep_json())
        self.assertEqual(sys.getrecursionlimit(), before)

    def test_shallow_nesting_and_long_bracket_strings_remain_valid(self):
        value = '한글' + '[' * 12000 + ']' * 12000
        self.assertEqual(loads(json.dumps(value)), value)
        shallow = '[' * 50 + '"합성"' + ']' * 50
        self.assertEqual(loads(shallow), json.loads(shallow))
        for malformed in ('{"a":1,"a":2}', '"\\ud800"'):
            with self.assertRaises(ValueError):
                loads(malformed)

    def deep_web(self):
        record = web(); record['metadata'] = 'DEPTH_PLACEHOLDER'
        self.path.write_text(json.dumps([record]).replace('"DEPTH_PLACEHOLDER"', deep_json()), encoding='utf-8')

    def deep_local(self):
        records = local(); records[1]['metadata'] = 'DEPTH_PLACEHOLDER'
        text = json.dumps(records[0]) + '\r\n\r\n' + json.dumps(records[1]).replace('"DEPTH_PLACEHOLDER"', deep_json())
        self.path.write_bytes(b'\xef\xbb\xbf' + text.encode())

    def test_deep_web_metadata_rejects_all_source_readers_without_database_access(self):
        self.deep_web()
        self.assert_preconnection_failure(lambda db: import_export(db, 'demo', self.path, 'web'), 'nesting')
        for operation in (lambda: inspect_export(self.path, 'web', conversation='chat'),
                          lambda: list_export(self.path, 'web'),
                          lambda: branch_view(self.path, 'chat'),
                          lambda: check_import(self.missing, 'demo', self.path, 'web'),
                          lambda: make_plan(self.missing, 'demo', 'chat', self.path, 'web')):
            with self.assertRaisesRegex(ValueError, 'nesting'):
                operation()
        self.assertFalse(self.missing.exists())

    def test_deep_unselected_web_metadata_still_rejects_whole_file(self):
        extra = web(); extra['id'] = 'other'; extra['metadata'] = 'DEPTH_PLACEHOLDER'
        self.path.write_text(json.dumps([web(), extra]).replace('"DEPTH_PLACEHOLDER"', deep_json()), encoding='utf-8')
        self.assert_preconnection_failure(lambda db: import_export(db, 'demo', self.path, 'web', conversation='chat'), 'nesting')

    def test_deep_local_metadata_reports_physical_line_and_replay_json_failure(self):
        self.deep_local()
        for kind in ('local', 'local-codex'):
            self.assert_preconnection_failure(lambda db: import_export(db, 'demo', self.path, kind), ':3$')
            with self.assertRaisesRegex(ValueError, ':3$'):
                list_export(self.path, kind)
        result = reconstruct(self.path)
        self.assertFalse(result['supported'])
        self.assertEqual(result['reason_code'], 'INVALID_JSON')
        self.assertEqual(result['line'], 3)
        self.assertFalse(result['partial_output'])
        self.assertNotIn('SYNTHETIC_PRIVATE', json.dumps(result))
        self.assertEqual(result['original_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_deep_normalized_metadata_rejects_late_row_before_connect(self):
        row = normalized(message_id='v', metadata='DEPTH_PLACEHOLDER')
        self.path.write_text(json.dumps(normalized()) + '\n' + json.dumps(row).replace('"DEPTH_PLACEHOLDER"', deep_json()))
        self.assert_preconnection_failure(lambda db: ingest(db, 'demo', self.path), 'line 2$')

    def assert_local_encoder_failure(self):
        before = self.db.read_bytes(), self.path.read_bytes()
        for kind in ('local', 'local-codex'):
            self.assert_preconnection_failure(
                lambda db: import_export(db, 'demo', self.path, kind),
                r'^JSON nesting is too deep: .*:3$')
            for operation in (lambda: inspect_export(self.path, kind),
                              lambda: list_export(self.path, kind)):
                with self.assertRaisesRegex(ValueError, r'^JSON nesting is too deep: .*:3$') as caught:
                    operation()
                self.assertNotIn('SYNTHETIC_PRIVATE', str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual((self.db.read_bytes(), self.path.read_bytes()), before)

    def test_local_encoder_recursion_is_sanitized_before_database_access(self):
        self.write_rows(local(), separator='\n\n')
        error = RecursionError('SYNTHETIC_PRIVATE_KEY')
        # Exception notes (where supported) must not appear in CLI diagnostics.
        if hasattr(error, 'add_note'):
            error.add_note('SYNTHETIC_PRIVATE_NOTE')
        with patch('recaplib.local_parser.json.dumps', side_effect=error):
            self.assert_local_encoder_failure()
        code = ("import runpy; from unittest.mock import patch; "
                "error = RecursionError('SYNTHETIC_PRIVATE_KEY'); "
                "patch('recaplib.local_parser.json.dumps', side_effect=error).start(); "
                "runpy.run_path(__import__('sys').argv.pop(1), run_name='__main__')")
        for kind in ('local', 'local-codex'):
            commands = [
                ['recap.py', 'inspect', str(self.path), '--format', kind],
                ['recap.py', '--db', str(self.missing), 'import', str(self.path),
                 '--source', 'demo', '--format', kind],
                ['export_inventory.py', str(self.path), '--format', kind],
            ]
            for command in commands:
                with self.subTest(kind=kind, command=command[0:2]):
                    result = subprocess.run([sys.executable, '-c', code, *command],
                                            capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, '')
                    self.assertIn('JSON nesting is too deep:', result.stderr)
                    self.assertIn(':3', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertNotIn('SYNTHETIC_PRIVATE', result.stderr)
                    self.assertFalse(self.missing.exists())

    def test_actual_local_decoder_encoder_gap_fails_cleanly(self):
        from tests._nesting import MAX_DEPTH, nested
        # Probe the encoder independently: constructing lists iteratively does
        # not first require the decoder to accept the same depth.
        def encoder_fails(depth):
            value = 0
            for _ in range(depth):
                value = [value]
            record = local()[1]
            record['SYNTHETIC_PRIVATE_KEY'] = value
            try:
                json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
            except RecursionError:
                return True
            return False
        low, high = 0, 10000
        while not encoder_fails(high):
            low = high
            if high == MAX_DEPTH:
                self.skipTest('encoder accepted every probed depth up to the byte limit')
            high = min(2 * high, MAX_DEPTH)
        while high - low > 1:
            middle = (low + high) // 2
            if encoder_fails(middle):
                high = middle
            else:
                low = middle
        # Small margin makes the encoder failure independent of helper frames.
        depth = high + 32
        record = local()[1]; record['SYNTHETIC_PRIVATE_KEY'] = 'DEPTH_PLACEHOLDER'
        raw = json.dumps(record).replace('"DEPTH_PLACEHOLDER"', nested(depth))
        try:
            loads(raw)
        except ValueError:
            self.skipTest('no decoder/encoder gap with a 32-frame safety margin on this runtime')
        self.path.write_text(json.dumps(local()[0]) + '\n\n' + raw, encoding='utf-8')
        self.assert_local_encoder_failure()

    def test_incoming_conflicting_fields_fail_before_connect_with_physical_line(self):
        for field, value in [('role', 'assistant'), ('timestamp', 'different'),
                             ('title', 'SYNTHETIC_PRIVATE_TITLE'), ('text', 'SYNTHETIC_PRIVATE_BODY')]:
            for separator in ('\n', '\r\n', '\r'):
                with self.subTest(field=field, separator=separator):
                    rows = [normalized(), normalized(message_id='v'), normalized(**{field: value})]
                    self.write_rows(rows, separator, bom=True, initial_blank=True)
                    self.assert_preconnection_failure(lambda db: ingest(db, 'demo', self.path), 'conflicting message identity at line 4$')

    def test_conflicting_web_records_do_not_create_an_empty_archive(self):
        self.path.write_text(json.dumps([web(), web('SYNTHETIC_PRIVATE_CONFLICT')]))
        self.assert_preconnection_failure(lambda db: import_export(db, 'demo', self.path, 'web'), 'conflicting message identity at line 2$')
        # Parser inspection is not import admission; diagnostics still describe
        # contradictory repeated input against an existing read-only archive.
        self.assertEqual(inspect_export(self.path, 'web')['extracted_messages'], 2)
        report = check_import(self.db, 'demo', self.path, 'web')
        self.assertEqual(report['repeated_input']['conflicting'], 1)
        self.assertTrue(report['conflicts_found'])

    def test_conflicting_local_explicit_ids_fail_before_connect(self):
        records = local(); repeated = copy.deepcopy(records[1])
        repeated['payload']['content'][0]['text'] = 'SYNTHETIC_PRIVATE_CONFLICT'
        self.write_rows([*records, repeated], '\r\n', bom=True)
        for kind in ('local', 'local-codex'):
            self.assert_preconnection_failure(lambda db: import_export(db, 'demo', self.path, kind), 'conflicting message identity at line 2$')

    def test_duplicate_check_applies_to_selected_incoming_batch_only(self):
        other = web(); other['id'] = 'other'
        conflict = copy.deepcopy(other)
        conflict['mapping']['u']['message']['content']['parts'] = ['Different synthetic text']
        self.path.write_text(json.dumps([web(), other, conflict]))
        raw = self.path.read_bytes()
        result = import_export(self.missing, 'demo', self.path, 'web', conversation='chat')
        self.assertEqual((result['records'], result['inserted']), (1, 1))
        self.assertEqual(result['coverage']['selection']['excluded_messages'], 2)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_identical_normalized_duplicates_keep_record_counts_and_first_locator(self):
        first = normalized(); second = normalized(extra='Ignored metadata')
        self.write_rows([first, second, normalized(conversation_id='other')], '\r\n', bom=True, initial_blank=True)
        raw = self.path.read_bytes()
        receipt = ingest(self.missing, 'demo', self.path)
        self.assertEqual((receipt['records'], receipt['inserted']), (3, 2))
        self.assertEqual(receipt['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertTrue(receipt['utf8_bom_present'])
        self.assertEqual(ingest(self.missing, 'demo', self.path)['inserted'], 0)
        with closing(sqlite3.connect(self.missing)) as connection:
            self.assertEqual(connection.execute('SELECT record_count FROM artifacts').fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT source_line FROM messages WHERE conversation_id='chat'").fetchone()[0], 2)
        self.assertEqual(len(search(self.missing, 'orchard')), 2)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_identical_local_duplicates_keep_all_source_occurrences(self):
        records = local(); self.write_rows([*records, copy.deepcopy(records[1])])
        raw = self.path.read_bytes()
        for kind in ('local', 'local-codex'):
            receipt = import_export(self.db, kind, self.path, kind)
            self.assertEqual((receipt['records'], receipt['inserted']), (2, 1))
            with closing(sqlite3.connect(self.db)) as connection:
                self.assertEqual(connection.execute('SELECT locator FROM export_occurrences WHERE source=? ORDER BY locator', (kind,)).fetchall(), [('line:2',), ('line:3',)])
            self.assertEqual(import_export(self.db, kind, self.path, kind)['inserted'], 0)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_missing_message_ids_remain_distinct_physical_occurrences(self):
        for kind in ('local', 'local-codex'):
            records = local(); records[1]['payload'].pop('id')
            second = copy.deepcopy(records[1]); second['payload']['id'] = None
            self.write_rows([*records, second])
            self.assertEqual(import_export(self.db, kind, self.path, kind)['inserted'], 2)
            with closing(sqlite3.connect(self.db)) as connection:
                ids = connection.execute('SELECT message_id FROM messages WHERE source_id=? ORDER BY message_pk', (kind,)).fetchall()
            self.assertEqual(ids, [('synthetic.jsonl:2',), ('synthetic.jsonl:3',)])

    def test_archive_only_conflict_is_still_checked_under_write_lock(self):
        self.write_rows([normalized(message_id='new'), normalized(text='Different incoming text')])
        before = self.db.read_bytes()
        statements = []; real_connect = sqlite3.connect
        def traced(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connection.set_trace_callback(statements.append)
            return connection
        with patch('recap.sqlite3.connect', traced), self.assertRaisesRegex(ValueError, 'conflicting message identity'):
            ingest(self.db, 'existing', self.path)
        self.assertEqual(self.db.read_bytes(), before)
        lock = statements.index('BEGIN IMMEDIATE')
        reads = [i for i, sql in enumerate(statements) if sql.startswith('SELECT role,timestamp,title,text')]
        self.assertTrue(reads)
        self.assertTrue(all(i > lock for i in reads))
        with closing(real_connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 1)

    def test_cli_deep_and_conflicting_inputs_fail_cleanly_without_database(self):
        def call(*args):
            result = subprocess.run([sys.executable, *map(str, args)], capture_output=True,
                                    env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(b'Traceback', result.stderr)
            self.assertNotIn(b'SYNTHETIC_PRIVATE', result.stdout + result.stderr)
            self.assertFalse(self.missing.exists())
        for kind in ('web', 'local', 'local-codex'):
            self.deep_web() if kind == 'web' else self.deep_local()
            for script in ('recap.py', 'session_workflow.py'):
                call(script, '--db', self.missing, 'inspect', self.path, '--format', kind)
                call(script, '--db', self.missing, 'import', self.path, '--format', kind, '--source', 'demo')
            call('export_inventory.py', self.path, '--format', kind)
        self.write_rows([normalized(), normalized(text='SYNTHETIC_PRIVATE_CONFLICT')])
        call('recap.py', '--db', self.missing, 'ingest', self.path, '--source', 'demo')
        self.path.write_text(json.dumps([web(), web('SYNTHETIC_PRIVATE_CONFLICT')]))
        for script in ('recap.py', 'session_workflow.py'):
            call(script, '--db', self.missing, 'import', self.path, '--format', 'web', '--source', 'demo')
