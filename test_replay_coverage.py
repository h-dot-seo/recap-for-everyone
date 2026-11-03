"""Chosen synthetic schema scenarios, not a measured user-usage distribution."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from test_replay_local import turn, event
from replay_local import reconstruct


def scenarios():
    meta = dict(type='session_meta', payload=dict(id='synthetic', source='cli'))
    plain = [meta, *turn('a')]
    context = copy.deepcopy(plain)
    context.insert(2, dict(type='turn_context', payload=dict(turn_id='a', cwd='PRIVATE_CWD',
                    model='PRIVATE_MODEL', approval_policy='on-request', sandbox_policy=dict(type='read-only'))))
    token = copy.deepcopy(plain); token.insert(-1, event('token_count', info={}))
    no_id = copy.deepcopy(plain); no_id[3]['payload'].pop('id')
    tool = copy.deepcopy(plain); tool.insert(-1, dict(type='response_item', payload=dict(type='function_call', arguments='PRIVATE_ARGS')))
    media = copy.deepcopy(plain); media[2]['payload']['file_ids'] = ['PRIVATE_FILE']
    compact = copy.deepcopy(plain); compact.append(dict(type='compacted', payload=dict(replacement_history=[])))
    fork = copy.deepcopy(plain); fork[0]['payload']['history_base'] = dict(thread_id='PRIVATE_PARENT')
    attribution = copy.deepcopy(plain); attribution[1]['payload']['turn_attribution'] = dict(turn_id='a')
    no_user_event = copy.deepcopy(plain); del no_user_event[2]
    open_turn = copy.deepcopy(plain); open_turn.pop()
    mismatched_context = copy.deepcopy(context); mismatched_context[2]['payload']['turn_id'] = 'other'
    rollback = [copy.deepcopy(meta), *turn('a'), *turn('b'), event('thread_rolled_back', num_turns=1)]
    return [
        ('plain completed text', plain, None),
        ('matching turn context', context, None),
        ('token accounting event', token, 'EVENT_UNSUPPORTED'),
        ('missing explicit message ID', no_id, 'INVALID_OR_REUSED_MESSAGE_ID'),
        ('tool invocation', tool, 'RESPONSE_UNSUPPORTED'),
        ('user image/file reference', media, 'NON_TEXT_UNSUPPORTED'),
        ('compacted history', compact, 'COMPACTION_UNSUPPORTED'),
        ('inherited history', fork, 'UNRESOLVED_HISTORY'),
        ('modern turn attribution', attribution, 'TURN_ATTRIBUTION_UNSUPPORTED'),
        ('missing user event', no_user_event, 'MISSING_USER_EVENT'),
        ('ongoing turn', open_turn, 'INCOMPLETE_TURN'),
        ('mismatched turn context', mismatched_context, 'CONTEXT_TURN_MISMATCH'),
        ('completed-turn rollback', rollback, None),
    ]


class ReplayCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'rollout.jsonl'

    def project(self, records):
        self.path.write_text(''.join(json.dumps(record) + '\n' for record in records))
        raw = self.path.read_bytes(); result = reconstruct(self.path)
        self.assertEqual(raw, self.path.read_bytes())
        return result

    def test_representative_matrix_exact_supported_and_rejected_counts(self):
        counts = dict(supported=0, unsupported=0)
        for name, records, reason in scenarios():
            with self.subTest(scenario=name):
                result = self.project(records)
                self.assertEqual(result['supported'], reason is None)
                if reason is not None:
                    self.assertEqual(result['reason_code'], reason)
                    self.assertNotIn('turns', result)
                    counts['unsupported'] += 1
                else:
                    self.assertFalse(result['full_model_history_reconstructed'])
                    counts['supported'] += 1
                self.assertNotIn('PRIVATE_', json.dumps(result))
        self.assertEqual(counts, dict(supported=3, unsupported=10))

    def test_context_is_not_a_user_turn_and_payload_is_not_emitted(self):
        records = scenarios()[1][1]
        records.extend(turn('b')); records.append(event('thread_rolled_back', num_turns=1))
        result = self.project(records)
        self.assertTrue(result['supported'])
        self.assertEqual(result['retained_turns'], 1)
        self.assertEqual(result['rolled_back_turns'], 1)
        self.assertEqual(result['turn_context_records_ignored'], 1)
        self.assertEqual(result['turns'][0]['turn_context_records'], 1)
        self.assertNotIn('PRIVATE_', json.dumps(result))

    def test_unknown_context_fields_and_wrong_metadata_shapes_rejected(self):
        for fields, reason in [({'future_history': {}}, 'CONTEXT_FIELDS_UNSUPPORTED'),
                               ({'cwd': []}, 'INVALID_CONTEXT_METADATA'),
                               ({'sandbox_policy': 'private'}, 'INVALID_CONTEXT_METADATA')]:
            records = [dict(type='session_meta', payload=dict(id='synthetic')),
                       event('task_started', turn_id='a'),
                       dict(type='turn_context', payload=dict(turn_id='a', **fields))]
            result = self.project(records)
            self.assertFalse(result['supported']); self.assertEqual(result['reason_code'], reason)
            self.assertNotIn('turns', result)

    def test_unscoped_missing_repeated_and_wrong_root_context_rejected(self):
        context = dict(type='turn_context', payload=dict(turn_id='a'))
        cases = [
            ([dict(type='session_meta', payload=dict(id='synthetic')), context], 'UNSCOPED_TURN_CONTEXT'),
            ([dict(type='session_meta', payload=dict(id='synthetic')), event('task_started', turn_id='a'),
              dict(type='turn_context', payload={})], 'CONTEXT_TURN_MISMATCH'),
            ([dict(type='session_meta', payload=dict(id='synthetic')), event('task_started', turn_id='a'), context, context], 'REPEATED_TURN_CONTEXT'),
            ([dict(type='session_meta', payload=dict(id='synthetic')), event('task_started', turn_id='a'),
              dict(type='turn_context', payload=dict(turn_id='a', root_turn_id='other'))], 'CONTEXT_TURN_MISMATCH')]
        for records, reason in cases:
            with self.subTest(reason=reason):
                result = self.project(records); self.assertFalse(result['supported'])
                self.assertEqual(result['reason_code'], reason); self.assertNotIn('turns', result)
