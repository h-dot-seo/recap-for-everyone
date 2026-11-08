"""Accounting metadata is scoped and ignored, never output as text or costs."""
import json
import tempfile
import unittest
from pathlib import Path
from recaplib.replay_local import reconstruct
from tests.test_replay_local import turn, event


def accounting():
    usage = dict(input_tokens=10, cached_input_tokens=1, output_tokens=3,
                 reasoning_output_tokens=0, total_tokens=13)
    return event('token_count', info=dict(total_token_usage=usage, last_token_usage=usage,
                 model_context_window=1000, last_usage_includes_reasoning=False),
                 rate_limits=dict(limit_id='PRIVATE_LIMIT', credits=dict(has_credits=True, unlimited=False, balance='PRIVATE_BALANCE')))


class TokenProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'input.jsonl'
        self.meta = dict(type='session_meta', payload=dict(id='synthetic'))

    def run_records(self, records):
        self.path.write_text(''.join(json.dumps(record) + '\n' for record in records))
        before = self.path.read_bytes(); result = reconstruct(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertNotIn('PRIVATE_', json.dumps(result))
        return result

    def test_repeated_accounting_is_ignored_without_changing_user_turn_counts(self):
        records = [self.meta, *turn('a')]; records.insert(-1, accounting()); records.insert(-1, accounting())
        records.extend(turn('b')); records.append(event('thread_rolled_back', num_turns=1))
        result = self.run_records(records)
        self.assertTrue(result['supported']); self.assertEqual(result['retained_turns'], 1)
        self.assertEqual(result['rolled_back_turns'], 1)
        self.assertEqual(result['token_count_records_ignored'], 2)
        self.assertEqual(result['turns'][0]['token_count_records'], 2)
        self.assertEqual(len(result['turns'][0]['messages']), 2)

    def test_unscoped_or_unknown_fields_are_rejected_without_partial_output(self):
        result = self.run_records([self.meta, accounting()])
        self.assertEqual(result['reason_code'], 'UNSCOPED_TOKEN_COUNT')
        for field in ('future_payload', 'turn_id'):
            record = accounting(); record['payload'][field] = 'PRIVATE_VALUE'
            records = [self.meta, *turn('a')]; records.insert(-1, record)
            result = self.run_records(records)
            self.assertEqual(result['reason_code'], 'TOKEN_FIELDS_UNSUPPORTED'); self.assertNotIn('turns', result)

    def test_invalid_basic_metadata_shapes_and_counter_types_fail_closed(self):
        bad = []
        for key, value in [('info', []), ('rate_limits', 'private')]:
            record = accounting(); record['payload'][key] = value; bad.append(record)
        for value in (True, 1.0, 2**63, -(2**63)-1, 'private'):
            record = accounting(); record['payload']['info']['last_token_usage']['input_tokens'] = value; bad.append(record)
        record = accounting(); record['payload']['info']['total_token_usage'].pop('output_tokens'); bad.append(record)
        record = accounting(); record['payload']['rate_limits']['credits'] = 'private'; bad.append(record)
        for record in bad:
            records = [self.meta, *turn('a')]; records.insert(-1, record)
            result = self.run_records(records)
            self.assertFalse(result['supported']); self.assertNotIn('turns', result)

    def test_accounting_does_not_make_unsupported_events_acceptable(self):
        for extra in [dict(type='compacted', payload={}), event('turn_aborted'),
                      dict(type='response_item', payload=dict(type='function_call'))]:
            records = [self.meta, *turn('a')]; records.insert(-1, accounting()); records.insert(-1, extra)
            result = self.run_records(records)
            self.assertFalse(result['supported']); self.assertNotIn('turns', result)
