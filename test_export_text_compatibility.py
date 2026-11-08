"""Synthetic UTF-8 signatures and physical-line compatibility, preserving bytes."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from attributed_title import suggest_attributed
from branch_title import suggest_branch
from conversation_search import find
from conversation_view import conversation
from export_inventory import list_export
from import_check import check_import
from local_parser import parse_artifact
from prepare_web_export import prepare_web_export
from recap import ingest
from replay_local import reconstruct_bytes
from replay_title import suggest_replay
from session_workflow import import_export, inspect_export, normalize, titles
from source_text import BOM_UTF8, decode_source, physical_lines
from strict_json import loads
from test_attributed_title import label, message, text_part
from test_replay_local import turn
from title_adapter import prepare_request, request_document, complete_response, AdapterConfig, AdapterError
from title_plan import make_plan, check_plan
from title_proposal import preview, apply_preview


ROOT = Path(__file__).resolve().parent


class ExportTextCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'synthetic.jsonl'
        self.db = self.root / 'archive.sqlite'

    @staticmethod
    def framed(raw, newline=b'\n', bom=True):
        raw = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        return (BOM_UTF8 if bom else b'') + raw.replace(b'\n', newline)

    def copied(self, name, newline=b'\n', bom=True):
        self.path = self.root / name
        self.path.write_bytes(self.framed((ROOT / 'examples' / name).read_bytes(), newline, bom))
        return self.path.read_bytes()

    def reset_db(self):
        if self.db.exists():
            self.db.unlink()

    def test_decoder_only_removes_one_initial_signature(self):
        body = '합성\ufeff본문\u2028\u2029\u0085'.encode('utf-8')
        self.assertEqual(decode_source(BOM_UTF8 + body), body.decode('utf-8'))
        self.assertEqual(decode_source(BOM_UTF8 * 2 + b'{}'), '\ufeff{}')
        self.assertEqual(decode_source(b' ' + BOM_UTF8 + b'{}'), ' \ufeff{}')
        self.assertEqual(physical_lines(BOM_UTF8 + b'a\r\nb\rc\n\n'), ['a', 'b', 'c', '', ''])
        self.assertEqual(physical_lines(body), [body.decode('utf-8')])
        for raw in (b'\xff', b'\xc0\xaf', b'\xef\xbb', b'\xed\xa0\x80'):
            with self.subTest(raw=raw), self.assertRaises(UnicodeError):
                decode_source(raw)

    def test_all_export_formats_inventory_selection_and_original_hash(self):
        cases = [('web', 'web-export.json', 'synthetic-chat'),
                 ('local', 'local-session.jsonl', 'synthetic-local'),
                 ('local-codex', 'rollback-session.jsonl', 'synthetic-rollout')]
        for kind, name, cid in cases:
            for newline in (b'\n', b'\r\n', b'\r'):
                with self.subTest(kind=kind, newline=newline):
                    self.reset_db()
                    raw = self.copied(name, newline)
                    digest = hashlib.sha256(raw).hexdigest()
                    report = inspect_export(self.path, kind, cid, digest)
                    self.assertTrue(report['utf8_bom_present'])
                    self.assertEqual(report['original_sha256'], digest)
                    self.assertEqual(report['original_bytes'], len(raw))
                    inventory = list_export(self.path, kind, expected_export_sha256=digest)
                    self.assertEqual(inventory['conversations'][0]['conversation'], cid)
                    self.assertTrue(inventory['coverage']['utf8_bom_present'])
                    self.assertFalse(self.db.exists())
                    result = import_export(self.db, 'demo', self.path, kind, cid, digest)
                    self.assertEqual(result['inserted'], report['selection']['selected_messages'])
                    self.assertEqual(result['coverage']['original_sha256'], digest)
                    self.assertEqual(self.path.read_bytes(), raw)

    def test_no_bom_preserves_existing_receipt_shapes(self):
        raw = self.copied('rollback-session.jsonl', bom=False)
        self.assertNotIn('utf8_bom_present', inspect_export(self.path, 'local-codex'))
        self.assertNotIn('utf8_bom_present', reconstruct_bytes(raw))
        normalized = self.root / 'normalized.jsonl'
        normalized.write_bytes((ROOT / 'examples/conversations.jsonl').read_bytes())
        self.assertNotIn('utf8_bom_present', ingest(self.db, 'demo', normalized))

    def test_blank_mixed_newlines_preserve_physical_local_and_replay_locators(self):
        records = [dict(type='session_meta', payload=dict(id='synthetic')), *turn('one')]
        lines = [json.dumps(row, ensure_ascii=False).encode() for row in records]
        raw = BOM_UTF8 + lines[0] + b'\r\n\r' + lines[1] + b'\n' + lines[2] + b'\r' + lines[3] + b'\r\n' + lines[4] + b'\n' + lines[5]
        self.path.write_bytes(raw)
        parsed = parse_artifact(self.path, self.path.name, content_profile='codex')
        self.assertEqual([m.line_number for m in parsed.messages], [5, 6])
        projected = reconstruct_bytes(raw)
        self.assertTrue(projected['supported'])
        self.assertTrue(projected['utf8_bom_present'])
        self.assertEqual([m['origin_locator'] for m in projected['turns'][0]['messages']], ['line:5', 'line:6'])
        import_export(self.db, 'demo', self.path, 'local-codex')
        proposed = suggest_replay(self.db, 'demo', 'synthetic', self.path)
        self.assertEqual(proposed['evidence_message_ids'], ['oneu'])
        self.assertEqual(proposed['projection_context']['evidence_mappings'][0]['origin_locator'], 'line:5')

    def test_unicode_separators_bom_and_escaped_newlines_remain_message_data(self):
        text = '합성\ufeff계획\u2028두번째\u2029세번째\u0085끝\r\n내용'
        records = [dict(type='session_meta', payload=dict(id='synthetic')),
                   message([text_part(text)], [label('user')])]
        raw = BOM_UTF8 + b'\r'.join(json.dumps(row, ensure_ascii=False).encode() for row in records)
        self.path.write_bytes(raw)
        rows = normalize(self.path, 'local-codex')
        self.assertEqual(rows[0]['text'], text)
        self.assertEqual(rows[0]['origin_locator'], 'line:2')
        import_export(self.db, 'demo', self.path, 'local-codex')
        proposed = suggest_attributed(self.db, 'demo', 'synthetic', self.path)
        self.assertEqual(proposed['attribution_context']['evidence_parts'][0]['origin_locator'], 'line:2')
        archived = conversation(self.db, 'demo', 'synthetic')['messages'][0]
        self.assertEqual(archived['text'], text)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_web_bom_branch_adapter_preview_apply_search_and_plan(self):
        raw = self.copied('web-export.json', b'\r\n')
        import_export(self.db, 'demo', self.path, 'web')
        proposed = suggest_branch(self.db, 'demo', 'synthetic-chat', self.path, 'm2')
        prepared = prepare_request(self.db, 'demo', 'synthetic-chat', evidence_scope='web-branch', input_path=self.path, node='m2')
        self.assertEqual(json.loads(prepared.payload)['messages'][0]['text'], proposed['title'])
        apply_preview(self.db, preview(self.db, proposed))
        self.assertEqual(find(self.db, 'synthetic orchard')['total_matches'], 1)
        plan = make_plan(self.db, 'demo', 'synthetic-chat', self.path, 'web')
        self.assertEqual(plan['original_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertTrue(check_plan(self.db, self.path, plan)['valid'])
        self.assertEqual(self.path.read_bytes(), raw)

    def test_replay_bom_and_bare_cr_support_title_and_adapter(self):
        raw = self.copied('rollback-session.jsonl', b'\r')
        import_export(self.db, 'demo', self.path, 'local-codex')
        proposed = suggest_replay(self.db, 'demo', 'synthetic-rollout', self.path)
        self.assertEqual(proposed['title'], 'Synthetic question retained')
        prepared = prepare_request(self.db, 'demo', 'synthetic-rollout', evidence_scope='local-replay', input_path=self.path)
        self.assertEqual(json.loads(prepared.payload)['messages'][0]['text'], proposed['title'])
        apply_preview(self.db, preview(self.db, proposed))
        self.assertEqual(find(self.db, 'discarded')['total_matches'], 1)
        plan = make_plan(self.db, 'demo', 'synthetic-rollout', self.path, 'local-codex')
        self.assertTrue(check_plan(self.db, self.path, plan)['valid'])
        self.assertEqual(self.path.read_bytes(), raw)

    def test_attributed_bom_and_bare_cr_keep_part_indices(self):
        raw = self.copied('source-attributed-session.jsonl', b'\r')
        import_export(self.db, 'demo', self.path, 'local-codex')
        proposed = suggest_attributed(self.db, 'demo', 'synthetic-attributed', self.path)
        self.assertEqual(proposed['title'], 'Design a synthetic lunar calendar')
        parts = proposed['attribution_context']['evidence_parts']
        self.assertEqual(parts, [dict(message_id='synthetic-u1', origin_locator='line:2', content_indices=[2])])
        prepared = prepare_request(self.db, 'demo', 'synthetic-attributed', evidence_scope='local-attributed', input_path=self.path)
        self.assertEqual(json.loads(prepared.payload)['messages'][0]['text'], proposed['title'])
        apply_preview(self.db, preview(self.db, proposed))
        self.assertEqual(find(self.db, 'lunar calendar')['total_matches'], 1)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_normalized_ingest_preserves_byte_hash_and_physical_lines(self):
        rows = [dict(conversation_id='synthetic', message_id=str(i), role='user', timestamp='synthetic', text='합성 계획') for i in range(2)]
        raw = BOM_UTF8 + json.dumps(rows[0], ensure_ascii=False).encode() + b'\r\n\r' + json.dumps(rows[1], ensure_ascii=False).encode()
        self.path.write_bytes(raw)
        result = ingest(self.db, 'demo', self.path)
        self.assertTrue(result['utf8_bom_present'])
        self.assertEqual(result['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['inserted'], 2)
        messages = conversation(self.db, 'demo', 'synthetic')['messages']
        self.assertEqual([m['source_line'] for m in messages], [1, 3])
        self.assertEqual(ingest(self.db, 'demo', self.path)['inserted'], 0)
        self.assertEqual(self.path.read_bytes(), raw)

    def test_bom_change_does_not_bypass_hash_lease_or_provenance(self):
        plain = self.copied('web-export.json', bom=False)
        original_hash = hashlib.sha256(plain).hexdigest()
        import_export(self.db, 'demo', self.path, 'web')
        self.path.write_bytes(BOM_UTF8 + plain)
        for call in (lambda: import_export(self.db, 'demo', self.path, 'web', expected_export_sha256=original_hash),
                     lambda: list_export(self.path, 'web', expected_export_sha256=original_hash),
                     lambda: inspect_export(self.path, 'web', expected_export_sha256=original_hash)):
            with self.assertRaisesRegex(ValueError, 'changed after inspection'):
                call()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            suggest_branch(self.db, 'demo', 'synthetic-chat', self.path, 'm2')
        self.assertEqual(check_import(self.db, 'demo', self.path, 'web')['status'], 'NO_CONFLICTS')
        self.assertEqual(import_export(self.db, 'demo', self.path, 'web')['inserted'], 0)
        proposed = suggest_branch(self.db, 'demo', 'synthetic-chat', self.path, 'm2')
        self.assertNotEqual(proposed['branch_context']['original_sha256'], original_hash)
        origins = conversation(self.db, 'demo', 'synthetic-chat')['messages'][0]['export_provenance']
        self.assertEqual(len({p['original_sha256'] for p in origins}), 2)

    def test_reimported_framing_change_stales_saved_scoped_request(self):
        plain = self.copied('web-export.json', bom=False)
        import_export(self.db, 'demo', self.path, 'web')
        config = AdapterConfig(kind='external', endpoint='https://example.invalid/title')
        kwargs = dict(evidence_scope='web-branch', input_path=self.path, node='m2')
        saved = request_document(prepare_request(self.db, 'demo', 'synthetic-chat', config, **kwargs), config)
        self.path.write_bytes(BOM_UTF8 + plain)
        import_export(self.db, 'demo', self.path, 'web')
        with self.assertRaises(AdapterError) as caught:
            complete_response(self.db, 'demo', 'synthetic-chat', saved,
                dict(title='Synthetic orchard plan', evidence_message_ids=['m1']), config, **kwargs)
        self.assertEqual(caught.exception.code, 'PREPARED_REQUEST_STALE')

    def test_zip_member_bom_is_validated_and_copied_without_reencoding(self):
        raw = self.framed((ROOT / 'examples/web-export.json').read_bytes(), b'\r\n')
        archive = self.root / 'synthetic.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('conversations.json', raw)
        destination = self.root / 'prepared.json'
        result = prepare_web_export(archive, 'conversations.json', destination)
        self.assertEqual(destination.read_bytes(), raw)
        self.assertEqual(result['prepared_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertTrue(result['coverage']['utf8_bom_present'])

    def test_signature_and_encoding_failures_before_database_or_prepared_output(self):
        valid = (ROOT / 'examples/web-export.json').read_bytes()
        invalid = [BOM_UTF8 * 2 + valid, b' ' + BOM_UTF8 + valid, b'\xff' + valid,
                   valid.decode().encode('utf-16'), valid.decode().encode('utf-32'),
                   BOM_UTF8 + b'[{"id":"one","id":"two","mapping":{}}]']
        for raw in invalid:
            with self.subTest(prefix=raw[:6]):
                self.path.write_bytes(raw)
                with patch('sqlite3.connect', side_effect=AssertionError('no database access')):
                    with self.assertRaises(ValueError):
                        import_export(self.db, 'demo', self.path, 'web')
                archive = self.root / 'invalid.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr('conversations.json', raw)
                output = self.root / 'never-created.json'
                with self.assertRaises(ValueError):
                    prepare_web_export(archive, 'conversations.json', output)
                self.assertFalse(output.exists())
        self.assertFalse(self.db.exists())

    def test_midfile_signature_and_bad_local_records_fail_without_partial_replay(self):
        records = [dict(type='session_meta', payload=dict(id='synthetic')), *turn('one')]
        lines = [json.dumps(r).encode() for r in records]
        for raw in (BOM_UTF8 * 2 + b'\n'.join(lines), lines[0] + b'\r' + BOM_UTF8 + b'\r'.join(lines[1:]),
                    BOM_UTF8 + b'\r'.join(lines) + b'\r{"type":', b'\xff' + b'\n'.join(lines)):
            with self.subTest(prefix=raw[:6]):
                self.path.write_bytes(raw)
                with patch('sqlite3.connect', side_effect=AssertionError('no database access')):
                    with self.assertRaises(ValueError):
                        import_export(self.db, 'demo', self.path, 'local-codex')
                result = reconstruct_bytes(raw)
                self.assertFalse(result['supported'])
                self.assertFalse(result['partial_output'])
                self.assertNotIn('turns', result)
                self.assertEqual(result['original_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertFalse(self.db.exists())

    def test_input_read_once_and_snapshot_bytes_not_reread(self):
        self.copied('source-attributed-session.jsonl', b'\r')
        import_export(self.db, 'demo', self.path, 'local-codex')
        original_read = Path.read_bytes
        for call in (lambda: normalize(self.path, 'local-codex'),
                     lambda: list_export(self.path, 'local-codex'),
                     lambda: suggest_attributed(self.db, 'demo', 'synthetic-attributed', self.path)):
            reads = []
            def read(path):
                if path == self.path:
                    reads.append(path)
                return original_read(path)
            with patch.object(Path, 'read_bytes', read):
                call()
            self.assertEqual(len(reads), 1)

    def test_signature_support_does_not_relax_generic_json_or_replay_grammar(self):
        with self.assertRaises(ValueError):
            loads('\ufeff{}')
        records = [dict(type='session_meta', payload=dict(id='synthetic')), *turn('one'),
                   dict(type='compacted', payload={})]
        result = reconstruct_bytes(BOM_UTF8 + b'\r'.join(json.dumps(r).encode() for r in records))
        self.assertFalse(result['supported'])
        self.assertEqual(result['reason_code'], 'COMPACTION_UNSUPPORTED')
        self.assertEqual(result['line'], len(records))

    def test_normalized_malformed_encoding_and_late_signature_reject_before_db(self):
        raw = (ROOT/'examples/conversations.jsonl').read_bytes()
        first, second = raw.split(b'\n')[:2]
        for invalid in (BOM_UTF8*2 + raw, b'\xff' + raw, raw.decode().encode('utf-16'),
                        first + b'\r' + BOM_UTF8 + second,
                        BOM_UTF8 + b'{"conversation_id":"one","conversation_id":"two"}'):
            self.path.write_bytes(invalid)
            with patch('sqlite3.connect', side_effect=AssertionError('no database access')):
                with self.assertRaises(ValueError):
                    ingest(self.db, 'demo', self.path)
        self.assertFalse(self.db.exists())

    def test_empty_inputs_keep_existing_format_policies_without_fabricated_text(self):
        self.path.write_bytes(BOM_UTF8 + b'[]')
        report = inspect_export(self.path, 'web')
        self.assertEqual(report['extracted_messages'], 0)
        self.assertTrue(report['warnings'])
        self.path.write_bytes(BOM_UTF8)
        with self.assertRaises(ValueError):
            inspect_export(self.path, 'local-codex')
        self.assertEqual(reconstruct_bytes(BOM_UTF8)['reason_code'], 'MISSING_SESSION')
        receipt = ingest(self.db, 'demo', self.path)
        self.assertEqual((receipt['records'], receipt['inserted']), (0, 0))
        self.assertTrue(receipt['utf8_bom_present'])

    def test_web_unicode_signature_character_inside_text_and_title_is_preserved(self):
        text = '합성\ufeff본문\u2028다음\u2029줄\u0085끝'
        title = '원래\ufeff제목'
        data = [dict(id='synthetic', title=title, current_node='u', mapping={
            'u': dict(parent=None, message=dict(author=dict(role='user'), content=dict(parts=[text])))})]
        raw = BOM_UTF8 + json.dumps(data, ensure_ascii=False).encode()
        self.path.write_bytes(raw)
        rows = normalize(self.path, 'web')
        self.assertEqual(rows[0]['text'], text)
        self.assertEqual(rows[0]['title'], title)
        import_export(self.db, 'demo', self.path, 'web')
        archived = conversation(self.db, 'demo', 'synthetic')
        self.assertEqual(archived['original_title'], title)
        self.assertEqual(archived['messages'][0]['text'], text)
        proposed = suggest_branch(self.db, 'demo', 'synthetic', self.path)
        self.assertEqual(proposed['evidence_message_ids'], ['u'])
        self.assertEqual(self.path.read_bytes(), raw)

    def test_cli_bom_local_title_workflow_with_ascii_output(self):
        original = self.copied('rollback-session.jsonl', b'\r')
        def cli(*args):
            result = subprocess.run([sys.executable, str(ROOT/'recap.py'), *map(str, args)],
                capture_output=True, timeout=30, env=dict(os.environ, PYTHONIOENCODING='ascii'))
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        cli('--db', self.db, 'import', self.path, '--source', 'demo', '--format', 'local-codex')
        proposed = cli('--db', self.db, 'suggest-replay-title', self.path, '--source', 'demo', '--conversation', 'synthetic-rollout')
        saved = self.root/'proposal.json'; saved.write_text(json.dumps(proposed), encoding='utf-8')
        reviewed = cli('--db', self.db, 'preview-title', saved, '--title', '합성 유지 턴 정리')
        self.assertEqual(reviewed['expected_revision'], 0)
        self.assertEqual(reviewed['proposal']['conversation'], 'synthetic-rollout')
        self.assertEqual(reviewed['proposal']['title'], '합성 유지 턴 정리')
        saved.write_text(json.dumps(reviewed), encoding='utf-8')
        cli('--db', self.db, 'apply-title', saved)
        self.assertEqual(cli('--db', self.db, 'find', '합성 유지')['total_matches'], 1)
        self.assertEqual(self.path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
