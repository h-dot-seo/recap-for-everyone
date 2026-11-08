"""Synthetic incomplete/replayed history markers without reconstructing them."""
import json
import tempfile
import unittest
from pathlib import Path
from recaplib.session_workflow import normalize, inspect_export, import_export, titles
from recaplib.title_plan import make_plan, check_plan


class RolloutContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.jsonl'; self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.records = [dict(type='session_meta', payload=dict(id='synthetic',
                            forked_from_id='PRIVATE_PARENT', history_base=dict(path='PRIVATE_PATH'),
                            parent_thread_id='PRIVATE_THREAD', history_mode='paginated')),
                        self.message('first', 'Synthetic original question'),
                        dict(type='compacted', payload=dict(message='PRIVATE_SUMMARY',
                            replacement_history=[dict(role='user', content='PRIVATE_REPLACEMENT')])),
                        dict(type='event_msg', payload=dict(type='thread_rolled_back', num_turns=1)),
                        self.message('second', 'Synthetic later question')]
        self.write()

    @staticmethod
    def message(identity, text):
        return dict(type='response_item', payload=dict(type='message', id=identity,
                    role='user', content=[dict(type='input_text', text=text)]))

    def write(self):
        self.path.write_text(''.join(json.dumps(record) + '\n' for record in self.records))

    def test_context_markers_warn_without_extracting_private_metadata(self):
        rows, report = normalize(self.path, 'local-codex', include_report=True)
        counts = report['rollout_context']
        for name in ('compacted_records', 'rollback_events', 'fork_metadata_records',
                     'referenced_history_records', 'parent_thread_records', 'paginated_history_records'):
            self.assertEqual(counts[name], 1)
        self.assertFalse(report['effective_history_reconstructed'])
        self.assertGreaterEqual(len(report['warnings']), 3)
        self.assertNotIn('PRIVATE_', json.dumps(report))
        self.assertEqual([row['message_id'] for row in rows], ['first', 'second'])
        self.assertEqual([row['origin_locator'] for row in rows], ['line:2', 'line:5'])
        self.assertNotIn('PRIVATE_', json.dumps(rows))

    def test_fixed_unknown_categories_and_unsupported_roles(self):
        # Missing tags remain unknown; supplied malformed tags now reject in the
        # dedicated discriminator tests instead of risking a hidden boundary.
        self.records.extend([dict(type='PRIVATE_TYPE', payload=dict(text='PRIVATE_TEXT')),
                             dict(payload=dict(secret='PRIVATE_SHAPE')),
                             dict(type='response_item', payload=dict(type='function_call', arguments='PRIVATE_ARGS')),
                             dict(type='response_item', payload=dict(type='message', role='developer', content=[]))])
        self.write(); report = inspect_export(self.path, 'local-codex')
        self.assertEqual(report['rollout_context']['other_records'], 2)
        self.assertEqual(report['rollout_context']['nonmessage_response_items'], 1)
        self.assertEqual(report['rollout_context']['skipped_role_messages'], 1)
        self.assertNotIn('PRIVATE_', json.dumps(report))

    def test_fallback_identity_warning_is_explicit(self):
        self.records = [dict(type='session_meta', payload=dict(id='synthetic')), self.message('first', 'Synthetic')]
        self.records[1]['payload'].pop('id'); self.write()
        report = inspect_export(self.path, 'local')
        self.assertEqual(report['messages_without_explicit_id'], 1)
        self.assertTrue(any('basename' in warning for warning in report['warnings']))

    def test_import_keeps_raw_messages_and_carries_same_coverage(self):
        expected = inspect_export(self.path, 'local-codex'); expected.pop('mode')
        raw = self.path.read_bytes()
        result = import_export(self.db, 'typed', self.path, 'local-codex')
        self.assertEqual(result['inserted'], 2)
        self.assertEqual(result['coverage'], expected)
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(import_export(self.db, 'typed', self.path, 'local-codex')['inserted'], 0)

    def test_manual_plan_surfaces_warnings_and_old_version_is_rejected(self):
        import_export(self.db, 'typed', self.path, 'local-codex')
        titles(self.db, 'typed', 'synthetic', 'Reviewed synthetic title', 0)
        before = self.db.read_bytes()
        plan = make_plan(self.db, 'typed', 'synthetic', self.path, 'local-codex')
        self.assertEqual(plan['schema'], 'recap.manual-title-plan.v2')
        self.assertEqual(plan['extraction_warnings'], inspect_export(self.path, 'local-codex')['warnings'])
        self.assertFalse(plan['effective_history_reconstructed'])
        self.assertNotIn('PRIVATE_', json.dumps(plan))
        self.assertTrue(check_plan(self.db, self.path, plan)['valid'])
        plan['schema'] = 'recap.manual-title-plan.v1'
        with self.assertRaisesRegex(ValueError, 'unsupported title plan'): check_plan(self.db, self.path, plan)
        self.assertEqual(self.db.read_bytes(), before)
