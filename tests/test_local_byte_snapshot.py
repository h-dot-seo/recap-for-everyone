"""Synthetic local parsing without a temporary copy of source bytes."""
from codecs import BOM_UTF8
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recaplib.attributed_title import suggest_attributed
from recaplib.export_inventory import list_export
from recaplib.import_check import check_import
from recaplib.local_parser import LocalImportError, parse_artifact, parse_jsonl_bytes
from recaplib.replay_title import suggest_replay
from recaplib.session_workflow import _normalize_bytes, import_export, inspect_export, normalize
from recaplib.title_proposal import apply_preview, preview
from tests.test_replay_local import turn, event


def local_records():
    return [dict(type='session_meta', payload=dict(id='synthetic')),
            dict(type='response_item', timestamp=0, payload=dict(type='message', id='u', role='user',
                content=[dict(type='input_text', text='  합성\u2028orchard\tplan  '),
                         dict(type='input_image', image_url='synthetic-image')])),
            dict(type='response_item', payload=dict(type='message', role='assistant',
                content=[dict(type='output_text', text='  Synthetic reply  ')]))]


def jsonl(records):
    return ''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in records).encode('utf-8')


class LocalByteSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.path = self.root/'chosen-rollout.jsonl'

    def test_byte_and_file_entrypoints_preserve_golden_lines_ids_and_hashes(self):
        records = local_records(); encoded = [json.dumps(x, ensure_ascii=False).encode() for x in records]
        raw = BOM_UTF8+b'\r\n'+encoded[0]+b'\r\n\r\n'+encoded[1]+b'\r'+encoded[2]+b'\n'
        self.path.write_bytes(raw); label = 'exports/합성-session.jsonl'
        for profile in ('legacy', 'codex'):
            with self.subTest(profile=profile):
                parsed = parse_jsonl_bytes(raw, label, profile)
                self.assertEqual(parsed, parse_artifact(self.path, label, content_profile=profile))
                self.assertEqual(parsed.observed_record_count, 3)
                self.assertEqual(parsed.sessions[0].line_number, 2)
                self.assertEqual([m.line_number for m in parsed.messages], [4, 5])
                self.assertEqual([m.message_key for m in parsed.messages], ['u', label+':5'])
                self.assertEqual([m.explicit_id for m in parsed.messages], [True, False])
                self.assertEqual(parsed.messages[0].timestamp_utc, '0')
                text = records[1]['payload']['content'][0]['text']
                expected = text if profile == 'codex' else text.strip()
                self.assertEqual(parsed.messages[0].text, expected)
                self.assertEqual(parsed.messages[0].text_sha256, hashlib.sha256(expected.encode()).hexdigest())
                variant = json.dumps(records[1], ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
                self.assertEqual(parsed.messages[0].variant_sha256, hashlib.sha256(variant).hexdigest())
                self.assertEqual(parsed.skipped_content_parts, 1 if profile == 'codex' else 0)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_bytes_parser_never_opens_reads_writes_resolves_or_stages_its_label(self):
        raw = jsonl(local_records())
        with patch.object(Path, 'open', side_effect=AssertionError('no open')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('no read')), \
             patch.object(Path, 'write_bytes', side_effect=AssertionError('no write')), \
             patch.object(Path, 'resolve', side_effect=AssertionError('label is not a file')), \
             patch('tempfile.TemporaryDirectory', side_effect=AssertionError('no staging')), \
             patch('sqlite3.connect', side_effect=AssertionError('no database')):
            parsed = parse_jsonl_bytes(raw, 'nonexistent/label.jsonl', 'codex')
        self.assertEqual(parsed.messages[1].message_key, 'nonexistent/label.jsonl:3')

    def test_rejects_mutable_nonbyte_snapshot_and_invalid_arguments_before_io(self):
        raw = jsonl(local_records())
        with patch.object(Path, 'open', side_effect=AssertionError('no I/O')):
            for invalid in (None, raw.decode(), bytearray(raw), memoryview(raw), 1, []):
                with self.subTest(raw_type=type(invalid).__name__), self.assertRaises(LocalImportError):
                    parse_jsonl_bytes(invalid, 'synthetic.jsonl')
            for label in (None, '', 1, Path('synthetic.jsonl')):
                with self.subTest(label=label), self.assertRaises(LocalImportError):
                    parse_jsonl_bytes(raw, label)
            with self.assertRaisesRegex(LocalImportError, 'unsupported local content profile'):
                parse_jsonl_bytes(raw, 'synthetic.jsonl', 'unknown')

    def test_metadata_only_utility_labels_keep_existing_policies(self):
        cases = [('session_index.jsonl', jsonl([dict(id='synthetic', thread_name='Synthetic', updated_at='synthetic')]), 'session_index_metadata'),
                 ('agents/tool-a/raw/synthetic.jsonl', jsonl([dict(type='response_item', payload=False)]), 'agent_raw_evidence')]
        for label, raw, reason in cases:
            with self.subTest(label=label):
                self.path.write_bytes(raw)
                parsed = parse_jsonl_bytes(raw, label, 'codex')
                self.assertEqual(parsed, parse_artifact(self.path, label, content_profile='codex'))
                self.assertEqual(parsed.admission_status, 'accepted_metadata_only')
                self.assertEqual(parsed.reason_code, reason); self.assertEqual(parsed.messages, ())
        with self.assertRaises(LocalImportError):
            parse_jsonl_bytes(cases[0][1], 'renamed-index.jsonl', 'codex')

    def test_byte_diagnostics_use_label_file_diagnostics_keep_explicit_path(self):
        bad = [dict(type='session_meta', payload=dict(id='synthetic')),
               dict(type='response_item', payload=False)]
        raw = b'\n'+jsonl(bad); self.path.write_bytes(raw)
        for operation, locator in [(lambda: parse_jsonl_bytes(raw, 'exports/chosen.jsonl', 'codex'), 'exports/chosen.jsonl:3'),
                                   (lambda: parse_artifact(self.path, 'identity.jsonl', content_profile='codex'), str(self.path)+':3')]:
            with self.subTest(locator=locator), self.assertRaises(LocalImportError) as caught:
                operation()
            self.assertTrue(str(caught.exception).endswith(locator), str(caught.exception))

    def test_malformed_json_records_and_shapes_keep_fixed_physical_line_errors(self):
        meta = jsonl([local_records()[0]])
        cases = [(b'{"x":1,"x":2}', 'invalid JSONL record'),
                 (b'{"x":"\\ud800"}', 'invalid JSONL record'),
                 (b'[]', 'JSONL record is not an object'),
                 (b'{"type":"session_meta","payload":null}', 'invalid session metadata payload'),
                 (b'{"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":false,"text":"SYNTHETIC_PRIVATE"}]}}', 'typed content item type')]
        for ending, reason in cases:
            raw = BOM_UTF8+b'\r\n'+meta+b'\n'+ending+b'\r'
            with self.subTest(reason=reason), self.assertRaises(LocalImportError) as caught:
                parse_jsonl_bytes(raw, 'chosen.jsonl', 'codex')
            message = str(caught.exception)
            self.assertIn(reason, message); self.assertTrue(message.endswith('chosen.jsonl:4'))
            self.assertNotIn('SYNTHETIC_PRIVATE', message)
        with self.assertRaises(ValueError): parse_jsonl_bytes(b'\xff', 'chosen.jsonl', 'codex')

    def test_existing_sqlite_and_artifact_kind_routes_are_unchanged(self):
        db = self.root/'synthetic.sqlite'
        with closing(sqlite3.connect(db)) as connection:
            connection.execute('CREATE TABLE synthetic(value TEXT)'); connection.commit()
        raw = db.read_bytes()
        with patch('recaplib.local_parser._records', side_effect=AssertionError('SQLite is not JSONL')):
            result = parse_artifact(db, 'synthetic.sqlite', artifact_kind='sqlite')
        self.assertEqual(result.reason_code, 'sqlite_backup')
        self.assertEqual(db.read_bytes(), raw)
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('validate before read')):
            with self.assertRaisesRegex(LocalImportError, 'unsupported local artifact kind'):
                parse_artifact(self.path, 'synthetic', artifact_kind='unknown')
            with self.assertRaisesRegex(LocalImportError, 'unsupported local content profile'):
                parse_artifact(self.path, 'synthetic', content_profile='unknown')


class LocalByteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.path = self.root/'chosen-rollout.jsonl'; self.db = self.root/'archive.sqlite'
        self.path.write_bytes(jsonl(local_records()))

    def test_inspection_inventory_and_conflict_check_work_with_temporary_staging_disabled(self):
        import_export(self.db, 'demo', self.path, 'local-codex')
        before = self.db.read_bytes(); original = self.path.read_bytes()
        with patch('tempfile.TemporaryDirectory', side_effect=AssertionError('no source staging')), \
             patch.object(Path, 'write_bytes', side_effect=AssertionError('no source write')):
            for kind in ('local', 'local-codex'):
                with self.subTest(kind=kind):
                    report = inspect_export(self.path, kind)
                    inventory = list_export(self.path, kind)
                    checked = check_import(self.db, 'demo', self.path, kind)
                    self.assertEqual(report['extracted_messages'], 2)
                    self.assertEqual(inventory['conversations'][0]['conversation'], 'synthetic')
                    self.assertEqual(checked['records'], 2)
                    self.assertEqual(report['original_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.db.read_bytes(), before); self.assertEqual(self.path.read_bytes(), original)

    def test_source_read_once_and_same_snapshot_used_after_concurrent_replacement(self):
        original = self.path.read_bytes(); reader = Path.read_bytes; calls = []
        def snapshot(path):
            calls.append(path)
            self.assertEqual(path, self.path)
            raw = reader(path); path.write_bytes(b'changed synthetic file after read')
            return raw
        with patch.object(Path, 'read_bytes', snapshot), \
             patch('tempfile.TemporaryDirectory', side_effect=AssertionError('no staging')):
            rows, report = normalize(self.path, 'local-codex', True, 'synthetic', hashlib.sha256(original).hexdigest())
        self.assertEqual(calls, [self.path]); self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['message_id'], self.path.name+':3')
        self.assertEqual(rows[1]['origin_locator'], 'line:3')
        self.assertEqual(report['original_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(report['original_bytes'], len(original))

    def test_import_preserves_provenance_without_temporary_jsonl_staging(self):
        raw = self.path.read_bytes()
        with patch('tempfile.TemporaryDirectory', side_effect=AssertionError('no JSONL staging')):
            result = import_export(self.db, 'demo', self.path, 'local-codex')
        self.assertEqual(result['inserted'], 2); self.assertEqual(result['coverage']['original_sha256'], hashlib.sha256(raw).hexdigest())
        with closing(sqlite3.connect(self.db)) as connection:
            origins = connection.execute('SELECT original_hash,locator FROM export_occurrences ORDER BY locator').fetchall()
        self.assertEqual(origins, [(hashlib.sha256(raw).hexdigest(), 'line:2'), (hashlib.sha256(raw).hexdigest(), 'line:3')])
        self.assertEqual(import_export(self.db, 'demo', self.path, 'local-codex')['inserted'], 0)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_invalid_local_input_reports_selected_basename_before_db_or_staging(self):
        self.path.write_bytes(jsonl([local_records()[0], dict(type='response_item', payload=False)]))
        raw = self.path.read_bytes()
        with patch('tempfile.TemporaryDirectory', side_effect=AssertionError('no staging')), \
             patch('sqlite3.connect', side_effect=AssertionError('no database')):
            operations = [lambda: inspect_export(self.path, 'local-codex'),
                          lambda: list_export(self.path, 'local-codex'),
                          lambda: import_export(self.db, 'demo', self.path, 'local-codex'),
                          lambda: check_import(self.db, 'demo', self.path, 'local-codex')]
            for operation in operations:
                with self.assertRaises(LocalImportError) as caught: operation()
                self.assertEqual(str(caught.exception), 'invalid response item payload: chosen-rollout.jsonl:2')
        self.assertFalse(self.db.exists()); self.assertEqual(self.path.read_bytes(), raw)

    def test_cli_failure_uses_real_basename_line_without_body_temporary_path_or_traceback(self):
        self.path.write_bytes(b'\n'+jsonl([local_records()[0], dict(type='response_item', payload='SYNTHETIC_PRIVATE')]))
        for args in [('inspect', self.path, '--format', 'local-codex'),
                     ('list-export', self.path, '--format', 'local-codex'),
                     ('--db', self.db, 'import', self.path, '--format', 'local-codex', '--source', 'demo'),
                     ('--db', self.db, 'check-import', self.path, '--format', 'local-codex', '--source', 'demo')]:
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, 'recap.py', *map(str, args)], capture_output=True,
                    env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=30)
                self.assertEqual(result.returncode, 1); self.assertEqual(result.stdout, b'')
                self.assertEqual(result.stderr.decode('ascii').strip(), 'invalid response item payload: chosen-rollout.jsonl:3')
        self.assertFalse(self.db.exists())

    def test_scoped_title_evidence_reads_need_no_temporary_source_copy(self):
        replay = self.root/'retained.jsonl'
        records = [dict(type='session_meta', payload=dict(id='synthetic')), *turn('discarded'),
                   event('thread_rolled_back', num_turns=1), *turn('retained')]
        for record in records:
            if record['type'] == 'response_item': record['payload'].pop('id')
        replay.write_bytes(jsonl(records))
        attributed = Path('examples/source-attributed-session.jsonl')
        import_export(self.db, 'replay', replay, 'local-codex')
        import_export(self.db, 'attributed', attributed, 'local-codex')
        before = self.db.read_bytes(); originals = {p:p.read_bytes() for p in (replay, attributed)}
        with patch('tempfile.TemporaryDirectory', side_effect=AssertionError('no source staging')), \
             patch.object(Path, 'write_bytes', side_effect=AssertionError('no source write')):
            retained = suggest_replay(self.db, 'replay', 'synthetic', replay)
            labeled = suggest_attributed(self.db, 'attributed', 'synthetic-attributed', attributed)
            reviewed = preview(self.db, labeled)
        self.assertEqual(retained['title'], 'Synthetic question retained')
        self.assertEqual(labeled['title'], 'Design a synthetic lunar calendar')
        self.assertEqual(self.db.read_bytes(), before)
        apply_preview(self.db, reviewed)
        for path, raw in originals.items(): self.assertEqual(path.read_bytes(), raw)

    def test_web_normalization_does_not_enter_the_local_byte_parser(self):
        path = Path('examples/web-export.json'); raw = path.read_bytes()
        with patch('recaplib.session_workflow.parse_jsonl_bytes', side_effect=AssertionError('web stays separate')):
            rows, report = _normalize_bytes(raw, path.name, 'web', True)
        self.assertEqual(len(rows), 2); self.assertEqual(report['original_sha256'], hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    unittest.main()
