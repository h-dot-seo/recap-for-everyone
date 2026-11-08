"""Synthetic contract only: no remote title API or real account/data access."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from session_workflow import import_export, titles
from title_plan import make_plan
from title_transfer import dry_run, simulate, MockTitleAdapter, APPROVAL_SCHEMA


class TitleTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name)/'archive.sqlite'
        self.path = Path(self.tmp.name)/'source.json'
        self.path.write_bytes(Path('examples/web-export.json').read_bytes())
        import_export(self.db, 'web', self.path, 'web')
        titles(self.db, 'web', 'synthetic-chat', 'Synthetic reviewed title', 0)
        self.plan = make_plan(self.db, 'web', 'synthetic-chat', self.path, 'web')
        self.target = dict(provider='synthetic-mock', account_id='invented-account',
                           conversation_id='separate-target-id', revision='opaque-v1', title='Mock old title')
        self.request = dry_run(self.db, self.path, self.plan, self.target)
        self.approval = dict(schema=APPROVAL_SCHEMA, request_sha256=self.request['request_sha256'], approve=True)
        self.adapter = MockTitleAdapter(self.target)

    def test_dry_run_and_approved_simulation_preserve_files_and_use_separate_target(self):
        raw = self.path.read_bytes(); db = self.db.read_bytes()
        with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
            self.assertEqual(dry_run(self.db, self.path, self.plan, self.target), self.request)
            self.assertEqual(self.adapter.snapshot(), self.target)
            result = simulate(self.db, self.path, self.request, self.approval, self.adapter)
        self.assertEqual(result['execution_status'], 'SIMULATED_ONLY'); self.assertFalse(result['remote_mutation'])
        self.assertTrue(result['mock_state_changed']); self.assertEqual(result['target_after']['title'], self.plan['proposed_title'])
        self.assertEqual(result['target_after']['conversation_id'], 'separate-target-id')
        self.assertNotEqual(result['target_after']['revision'], self.target['revision'])
        self.assertEqual(self.path.read_bytes(), raw); self.assertEqual(self.db.read_bytes(), db)
        with self.assertRaisesRegex(ValueError, 'MOCK_TARGET_STALE'):
            simulate(self.db, self.path, self.request, self.approval, self.adapter)

    def test_explicit_approval_bound_to_complete_request(self):
        for approve in (False, None, 1, 'true'):
            with self.assertRaises(ValueError):
                simulate(self.db, self.path, self.request, dict(self.approval, approve=approve), self.adapter)
        for approval in ({}, None, dict(self.approval, extra=True), dict(self.approval, request_sha256='0'*64)):
            with self.assertRaises(ValueError): simulate(self.db, self.path, self.request, approval, self.adapter)
        changed_target = dict(self.target, account_id='different-invented-account')
        other = dry_run(self.db, self.path, self.plan, changed_target)
        with self.assertRaisesRegex(ValueError, 'approval does not match'):
            simulate(self.db, self.path, other, self.approval, MockTitleAdapter(changed_target))
        self.assertEqual(self.adapter.snapshot(), self.target)

    def test_request_tampering_unknown_fields_and_stale_plan_rejected(self):
        for key in self.request:
            altered = copy.deepcopy(self.request); del altered[key]
            with self.assertRaises((ValueError, KeyError)):
                simulate(self.db, self.path, altered, self.approval, self.adapter)
        for altered in (dict(self.request, unexpected=True), dict(self.request, proposed_title='Different'),
                        dict(self.request, request_sha256='0'*64)):
            with self.assertRaises(ValueError): simulate(self.db, self.path, altered, self.approval, self.adapter)
        titles(self.db, 'web', 'synthetic-chat', 'New local title', 1)
        with self.assertRaisesRegex(ValueError, 'stale or altered'):
            simulate(self.db, self.path, self.request, self.approval, self.adapter)
        self.assertEqual(self.adapter.snapshot(), self.target)

    def test_changed_source_and_target_any_field_block_simulation(self):
        for key, value in [('account_id', 'other'), ('conversation_id', 'other'), ('revision', 'v2'), ('title', 'Other title')]:
            adapter = MockTitleAdapter(dict(self.target, **{key: value}))
            before = adapter.snapshot()
            with self.assertRaisesRegex(ValueError, 'MOCK_TARGET_STALE'):
                simulate(self.db, self.path, self.request, self.approval, adapter)
            self.assertEqual(adapter.snapshot(), before)
        self.path.write_bytes(self.path.read_bytes()+b'\n')
        with self.assertRaises(ValueError): simulate(self.db, self.path, self.request, self.approval, self.adapter)
        self.assertEqual(self.adapter.snapshot(), self.target)

    def test_unknown_provider_and_invalid_target_fail_closed(self):
        for target in (None, {}, dict(self.target, provider='chatgpt'), dict(self.target, endpoint='https://invalid.test'),
                       dict(self.target, revision=1), dict(self.target, account_id=''), dict(self.target, title='')):
            with self.assertRaises(ValueError): dry_run(self.db, self.path, self.plan, target)
        class OtherAdapter(MockTitleAdapter): pass
        with self.assertRaisesRegex(ValueError, 'PROVIDER_NOT_CONFIGURED'):
            simulate(self.db, self.path, self.request, self.approval, OtherAdapter(self.target))

    def test_no_change_is_based_on_mock_title_not_archived_original(self):
        target = dict(self.target, title=self.plan['proposed_title'])
        request = dry_run(self.db, self.path, self.plan, target)
        self.assertEqual(self.plan['action'], 'manual_rename'); self.assertEqual(request['action'], 'no_change')
        result = simulate(self.db, self.path, request, dict(self.approval, request_sha256=request['request_sha256']), MockTitleAdapter(target))
        self.assertFalse(result['mock_state_changed']); self.assertEqual(result['target_after'], target)

    def test_atomic_mock_revision_allows_only_one_writer(self):
        def attempt(_):
            try: return simulate(self.db, self.path, self.request, self.approval, self.adapter)['mock_state_changed']
            except ValueError as exc:
                self.assertIn('MOCK_TARGET_STALE', str(exc)); return False
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(attempt, range(2))), [False, True])

    def test_local_retained_title_plan_uses_same_transfer_contract(self):
        from replay_title import suggest_replay
        from title_proposal import preview, apply_preview
        path = Path('examples/rollback-session.jsonl')
        import_export(self.db, 'local', path, 'local-codex')
        apply_preview(self.db, preview(self.db, suggest_replay(self.db, 'local', 'synthetic-rollout', path)))
        plan = make_plan(self.db, 'local', 'synthetic-rollout', path, 'local-codex')
        request = dry_run(self.db, path, plan, self.target)
        result = simulate(self.db, path, request, dict(self.approval, request_sha256=request['request_sha256']), self.adapter)
        self.assertEqual(result['target_after']['title'], 'Synthetic question retained')
        self.assertTrue(request['plan']['extraction_warnings'])
        self.assertFalse(request['plan']['effective_history_reconstructed'])

    def test_cli_dry_run_simulate_and_clean_failure_do_not_write_inputs(self):
        def save(name, value):
            path = Path(self.tmp.name)/name; path.write_text(json.dumps(value), encoding='utf-8'); return path
        plan = save('plan.json', self.plan); target = save('target.json', self.target)
        request = save('request.json', self.request); approval = save('approval.json', self.approval)
        files = [self.db, self.path, plan, target, request, approval]
        before = [p.read_bytes() for p in files]
        def call(*args, ok=True):
            result = subprocess.run([sys.executable, 'recap.py', '--db', str(self.db), *map(str,args)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0 if ok else 1, result.stderr); self.assertNotIn('Traceback', result.stderr)
            return json.loads(result.stdout) if ok else result
        self.assertEqual(call('title-adapter-dry-run', self.path, plan, target), self.request)
        result = call('title-adapter-simulate', self.path, request, approval, target)
        self.assertEqual(result['execution_status'], 'SIMULATED_ONLY')
        self.assertEqual(before, [p.read_bytes() for p in files])
        approval.write_text('{"approve":true,"approve":false}', encoding='utf-8')
        self.assertEqual(call('title-adapter-simulate', self.path, request, approval, target, ok=False).stdout, '')
