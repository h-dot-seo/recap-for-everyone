"""Synthetic editor-saved UTF-8 title files; no model, network or real sessions."""
from codecs import BOM_UTF8
import hashlib
from tests._cli import run_cli
import recap
from recaplib import title_proposal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recaplib.session_workflow import import_export, titles
from recaplib.strict_json import loads
from tests._nesting import deep_json
from recaplib.title_batch import load_supplied_proposals, select_queue_item, select_proposal, SCHEMA
from recaplib.title_proposal import read_document


class TitleFileEncodingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.path = self.root / 'title.json'

    def test_only_one_initial_signature_is_optional_without_rewriting_bytes(self):
        value = {'title': '합성 과수원 🌱', 'metadata': ['e\u0301', '\ufeffinside', 'a\ufeffb']}
        for prefix in (b'', BOM_UTF8):
            for whitespace in (b'', b' \r\n\t'):
                with self.subTest(prefix=prefix, whitespace=whitespace):
                    raw = prefix + whitespace + json.dumps(value, ensure_ascii=False).encode('utf-8') + b'\r\n'
                    self.path.write_bytes(raw)
                    self.assertEqual(read_document(self.path), value)
                    self.assertEqual(load_supplied_proposals([self.path]), [value])
                    self.assertEqual(self.path.read_bytes(), raw)

    def test_embedded_signature_is_preserved_in_keys_values_and_array_strings(self):
        value = {'\ufeffkey': {'title': 'A\ufeffB'}, 'values': ['\ufeff', 'x\ufeffy']}
        self.path.write_bytes(BOM_UTF8 + json.dumps(value, ensure_ascii=False).encode())
        self.assertEqual(read_document(self.path), value)
        self.assertEqual(load_supplied_proposals([self.path]), [value])

    def test_wrong_encoding_repeated_and_noninitial_signatures_remain_invalid(self):
        valid = b'{"title":"Synthetic"}'
        cases = [BOM_UTF8+BOM_UTF8+valid, b' '+BOM_UTF8+valid, valid+BOM_UTF8,
                 b'{'+BOM_UTF8+b'"title":"Synthetic"}', b'\xff'+valid,
                 valid.decode().encode('utf-16'), valid.decode().encode('utf-32'),
                 BOM_UTF8+b'{"title":"\xff"}']
        for raw in cases:
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                with self.assertRaises(ValueError): read_document(self.path)
                with self.assertRaises(ValueError): load_supplied_proposals([self.path])
                self.assertEqual(self.path.read_bytes(), raw)

    def test_duplicate_members_and_surrogates_still_fail(self):
        cases = [b'{"title":"one","title":"two"}', b'{"x":{"a":1,"a":2}}',
                 b'{"title":"\\ud800"}', b'{"\\udfff":"x"}']
        for raw in cases:
            for prefix in (b'', BOM_UTF8):
                with self.subTest(prefix=prefix, raw=raw[:70]):
                    self.path.write_bytes(prefix+raw)
                    with self.assertRaises(ValueError): read_document(self.path)
                    with self.assertRaises(ValueError): load_supplied_proposals([self.path])

    def test_excessive_nesting_fails_as_nesting_not_byte_budget(self):
        raw = ('{"nested":' + deep_json() + '}').encode()
        for prefix in (b'', BOM_UTF8):
            with self.subTest(prefix=prefix):
                self.path.write_bytes(prefix + raw)
                with self.assertRaisesRegex(ValueError, 'nesting is too deep'):
                    read_document(self.path)
                with self.assertRaisesRegex(ValueError, '^supplied proposal file must contain valid JSON$'):
                    load_supplied_proposals([self.path])
                self.assertEqual(self.path.read_bytes(), prefix + raw)

    def test_supplied_combined_budget_counts_all_original_signature_bytes(self):
        raw = BOM_UTF8+b'{"title":"Synthetic"}'
        self.path.write_bytes(raw)
        other = self.root/'other.json'; other.write_bytes(raw)
        for paths in ([self.path], [self.path, other]):
            size = len(raw)*len(paths)
            with self.subTest(files=len(paths)):
                with patch('recaplib.title_batch.MAX_SUPPLIED_BYTES', size):
                    self.assertEqual(len(load_supplied_proposals(paths)), len(paths))
                with patch('recaplib.title_batch.MAX_SUPPLIED_BYTES', size-1):
                    with self.assertRaisesRegex(ValueError, 'combined 1 MiB limit'):
                        load_supplied_proposals(paths)
        self.assertEqual(self.path.read_bytes(), raw); self.assertEqual(other.read_bytes(), raw)

    def test_selected_queue_copy_depth_errors_are_fixed_without_private_diagnostics(self):
        item = dict(status='READY', conversation='synthetic',
                    proposal=dict(source='mixed', conversation='synthetic'))
        queue = dict(schema=SCHEMA, source='mixed', items=[item])
        with patch('recaplib.title_batch.copy.deepcopy', side_effect=RecursionError('SYNTHETIC_PRIVATE')):
            with self.assertRaisesRegex(ValueError, '^selected queue item nesting is too deep$'):
                select_queue_item(queue, 'synthetic')
            # Exercise the second detached proposal copy independently too.
            with patch('recaplib.title_batch.select_queue_item', return_value=item):
                with self.assertRaisesRegex(ValueError, '^selected queue item nesting is too deep$'):
                    select_proposal(queue, 'synthetic')

    def test_shared_json_parser_and_in_memory_contract_are_not_relaxed(self):
        with self.assertRaises(ValueError): loads('\ufeff{"title":"Synthetic"}')
        # The file reader decodes JSON values, while consumers still validate shape.
        self.path.write_bytes(BOM_UTF8+b'["not a proposal"]')
        self.assertEqual(read_document(self.path), ['not a proposal'])
        with self.assertRaisesRegex(ValueError, 'one JSON object'):
            load_supplied_proposals([self.path])


class TitleFileEncodingWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root/'archive.sqlite'
        self.sources = [Path('examples/web-export.json'), Path('examples/source-attributed-session.jsonl')]
        self.originals = {p: p.read_bytes() for p in self.sources}
        import_export(self.db, 'mixed', self.sources[0], 'web')
        import_export(self.db, 'mixed', self.sources[1], 'local-codex')

    def call(self, *args, script='recap.py', success=True):
        entry = {'recap.py': recap.main, 'title_proposal.py': title_proposal.main}[script]
        result = run_cli(entry, ['--db', str(self.db), *map(str, args)])
        result.stdout = result.stdout.encode('ascii'); result.stderr = result.stderr.encode('ascii')
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr.decode('ascii', errors='replace'))
        self.assertNotIn(b'Traceback', result.stderr); result.stdout.decode('ascii')
        if not success:
            self.assertEqual(result.stdout, b''); return result
        return json.loads(result.stdout)

    def add_bom(self, path):
        path.write_bytes(BOM_UTF8+path.read_bytes()); return path

    def generated(self, local=False):
        path = self.root/('local-proposal.json' if local else 'web-proposal.json')
        if local:
            args = ('suggest-attributed-title', self.sources[1], '--conversation', 'synthetic-attributed')
        else:
            args = ('suggest-branch-title', self.sources[0], '--conversation', 'synthetic-chat', '--node', 'm2')
        self.call(*args, '--source', 'mixed', '--output', path)
        return self.add_bom(path)

    def test_web_and_typed_local_native_files_survive_editor_signatures_to_apply_search(self):
        for local, identity, query in [(False, 'synthetic-chat', 'orchard'),
                                      (True, 'synthetic-attributed', 'lunar calendar')]:
            with self.subTest(local=local):
                before = self.db.read_bytes(); proposal = self.generated(local)
                original = proposal.read_bytes(); reviewed = self.root/(identity+'-reviewed.json')
                receipt = self.call('preview-title', proposal, '--with-evidence', '--output', reviewed)
                raw = reviewed.read_bytes()
                self.assertEqual(receipt['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertFalse(raw.startswith(BOM_UTF8))
                self.assertEqual(self.db.read_bytes(), before)
                self.add_bom(reviewed); frozen = reviewed.read_bytes()
                result = self.call('apply-title', reviewed)
                self.assertGreater(result['revision'], 0)
                self.assertEqual(titles(self.db, 'mixed', identity)['revision'], result['revision'])
                self.assertGreaterEqual(self.call('find', query, '--source', 'mixed')['total_matches'], 1)
                self.assertEqual(proposal.read_bytes(), original); self.assertEqual(reviewed.read_bytes(), frozen)
        for path, raw in self.originals.items(): self.assertEqual(path.read_bytes(), raw)

    def test_standalone_preview_and_apply_share_the_same_file_decoder(self):
        proposal = self.generated(); before = self.db.read_bytes()
        reviewed = self.root/'standalone.json'
        self.call('preview', proposal, '--title', '합성 과수원 검토', '--output', reviewed, script='title_proposal.py')
        self.assertEqual(self.db.read_bytes(), before)
        self.add_bom(reviewed)
        result = self.call('apply', reviewed, script='title_proposal.py')
        self.assertEqual(result['display_title'], '합성 과수원 검토')

    def test_mixed_supplied_queue_preview_and_explicit_review_state(self):
        web = self.generated(); local = self.generated(True); before = self.db.read_bytes()
        queue = self.root/'queue.json'
        self.call('review-titles', '--source', 'mixed', '--proposal', web, '--proposal', local,
                  '--supplied-only', '--output', queue)
        self.add_bom(queue); frozen = queue.read_bytes()
        self.assertEqual(read_document(queue)['ready_count'], 2)
        reviewed = self.root/'reviewed.json'
        self.call('preview-title', queue, '--conversation', 'synthetic-attributed', '--output', reviewed)
        self.assertEqual(self.db.read_bytes(), before)
        self.call('review-state', '--source', 'mixed', '--conversation', 'synthetic-chat',
                  '--set', 'deferred', '--from-queue', queue)
        self.assertEqual(titles(self.db, 'mixed', 'synthetic-chat')['revision'], 0)
        self.assertEqual(titles(self.db, 'mixed', 'synthetic-attributed')['revision'], 0)
        self.call('apply-title', self.add_bom(reviewed))
        self.assertEqual(queue.read_bytes(), frozen)
        self.assertEqual(titles(self.db, 'mixed', 'synthetic-attributed')['revision'], 1)
        before = self.db.read_bytes()
        self.call('review-state', '--source', 'mixed', '--conversation', 'synthetic-chat',
                  '--set', 'deferred', '--from-queue', queue, success=False)
        self.assertEqual(self.db.read_bytes(), before)

    def test_signatures_do_not_bypass_stale_revision_or_content(self):
        proposal = self.generated(); reviewed = self.root/'reviewed.json'
        self.call('preview-title', proposal, '--output', reviewed); self.add_bom(reviewed)
        self.call('apply-title', reviewed); after = self.db.read_bytes()
        self.call('apply-title', reviewed, success=False)
        self.assertEqual(self.db.read_bytes(), after)
        value = read_document(proposal); value['content_sha256'] = '0'*64
        stale = self.root/'stale.json'; stale.write_bytes(BOM_UTF8+json.dumps(value).encode())
        target = self.root/'must-not-exist.json'
        self.call('preview-title', stale, '--output', target, success=False)
        self.assertFalse(target.exists()); self.assertEqual(self.db.read_bytes(), after)

    def test_invalid_documents_fail_without_output_archive_changes_or_traceback(self):
        proposal = self.generated(); valid = proposal.read_bytes()[len(BOM_UTF8):]
        invalid = [BOM_UTF8+BOM_UTF8+valid, b' '+BOM_UTF8+valid, valid.decode().encode('utf-16'),
                   BOM_UTF8+b'{"title":"one","title":"two"}', BOM_UTF8+b'{"x":"\\ud800"}',
                   BOM_UTF8+b'[]', BOM_UTF8+b'{"x":NaN}']
        before = self.db.read_bytes(); bad = self.root/'bad.json'; target = self.root/'not-created.json'
        for raw in invalid:
            with self.subTest(raw=raw[:40]):
                bad.write_bytes(raw)
                self.call('preview-title', bad, '--output', target, success=False)
                self.call('apply-title', bad, success=False)
                self.call('review-titles', '--source', 'mixed', '--proposal', bad,
                          '--supplied-only', '--output', target, success=False)
                self.call('review-state', '--source', 'mixed', '--conversation', 'synthetic-chat',
                          '--set', 'deferred', '--from-queue', bad, success=False)
                self.assertFalse(target.exists()); self.assertEqual(bad.read_bytes(), raw)
                self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(list(self.root.glob('.recap-title-*')), [])

    def test_deep_queue_items_fail_cleanly_before_preview_output_or_state_change(self):
        # This used to parse on the available runtime, then fail during deepcopy.
        # A decoder may reject it earlier on another runtime; both must be clean.
        nested = '['*600 + '0' + ']'*600
        raw = ('{"schema":"'+SCHEMA+'","source":"mixed","items":[{"status":"READY",'
               '"conversation":"synthetic-chat","extra":'+nested+','
               '"proposal":{"source":"mixed","conversation":"synthetic-chat"}}]}').encode()
        path = self.root/'deep-queue.json'; target = self.root/'not-created.json'
        proposal = json.dumps(read_document(self.generated()))
        supplied_raw = (proposal[:-1]+', "extra":'+nested+'}').encode()
        supplied = self.root/'deep-supplied.json'
        before = self.db.read_bytes()
        for prefix in (b'', BOM_UTF8):
            with self.subTest(prefix=prefix):
                path.write_bytes(prefix+raw)
                self.call('preview-title', path, '--conversation', 'synthetic-chat', '--output', target, success=False)
                self.call('review-state', '--source', 'mixed', '--conversation', 'synthetic-chat',
                          '--set', 'deferred', '--from-queue', path, success=False)
                supplied.write_bytes(prefix+supplied_raw)
                self.call('review-titles', '--source', 'mixed', '--proposal', supplied,
                          '--supplied-only', '--output', target, success=False)
                self.assertFalse(target.exists()); self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(path.read_bytes(), prefix+raw)
                self.assertEqual(supplied.read_bytes(), prefix+supplied_raw)

    def test_bom_receipt_does_not_become_a_proposal_or_approval(self):
        target = self.root/'proposal.json'
        receipt = self.call('suggest-title', '--source', 'mixed', '--conversation', 'synthetic-chat', '--output', target)
        path = self.root/'receipt.json'; path.write_bytes(BOM_UTF8+json.dumps(receipt).encode())
        before = self.db.read_bytes()
        self.call('preview-title', path, success=False); self.call('apply-title', path, success=False)
        self.assertEqual(self.db.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
