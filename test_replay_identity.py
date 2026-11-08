"""Missing source IDs stay missing; projection identities refer to immutable bytes."""
import json
import tempfile
import unittest
from pathlib import Path
from replay_local import reconstruct
from test_replay_local import turn, event


class ProjectionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'input.jsonl'
        self.meta = dict(type='session_meta', payload=dict(id='synthetic'))

    def write(self, records):
        self.path.write_text(''.join(json.dumps(record) + '\n' for record in records))
        return reconstruct(self.path)

    def test_missing_and_null_ids_have_distinct_nonremote_projection_ids(self):
        records = [self.meta, *turn('a')]
        records[3]['payload'].pop('id'); records[4]['payload']['id'] = None
        result = self.write(records); self.assertTrue(result['supported'])
        messages = result['turns'][0]['messages']
        self.assertEqual([m['message_id'] for m in messages], [None, None])
        self.assertNotEqual(messages[0]['projection_id'], messages[1]['projection_id'])
        self.assertEqual(messages[0]['projection_id'], 'sha256:'+result['original_sha256']+':line:4')
        self.assertEqual(messages[0]['identity_basis'], 'source byte hash and line only')

    def test_projection_identity_stable_on_rename_but_changes_with_bytes(self):
        records = [self.meta, *turn('a')]; records[3]['payload'].pop('id')
        first = self.write(records); other = Path(self.tmp.name) / 'renamed.jsonl'
        other.write_bytes(self.path.read_bytes())
        self.assertEqual(first, reconstruct(other))
        other.write_bytes(other.read_bytes()+b'\n')
        changed = reconstruct(other)
        self.assertNotEqual(first['turns'][0]['messages'][0]['projection_id'], changed['turns'][0]['messages'][0]['projection_id'])

    def test_explicit_id_namespace_and_duplicates_remain_distinct(self):
        records = [self.meta, *turn('a')]
        records[3]['payload']['id'] = 'sha256:synthetic:line:4'
        result = self.write(records); message = result['turns'][0]['messages'][0]
        self.assertEqual(message['message_id'], 'sha256:synthetic:line:4')
        self.assertNotEqual(message['message_id'], message['projection_id'])
        for bad in ('', 4, True, {}, []):
            records = [self.meta, *turn('a')]; records[3]['payload']['id'] = bad
            self.assertEqual(self.write(records)['reason_code'], 'INVALID_OR_REUSED_MESSAGE_ID')
        records = [self.meta, *turn('a')]; records[4]['payload']['id'] = 'au'
        self.assertEqual(self.write(records)['reason_code'], 'INVALID_OR_REUSED_MESSAGE_ID')

    def test_missing_ids_do_not_change_rollback_or_merge_identical_messages(self):
        records = [self.meta, *turn('a'), *turn('b')]
        for record in records:
            if record['type'] == 'response_item':
                record['payload'].pop('id')
                record['payload']['content'][0]['text'] = 'Synthetic repeated text'
            elif record['type'] == 'event_msg' and record['payload']['type'] == 'user_message':
                record['payload']['message'] = 'Synthetic repeated text'
        before = self.write(records)
        self.assertEqual(sum(len(t['messages']) for t in before['turns']), 4)
        records.append(event('thread_rolled_back', num_turns=1))
        result = self.write(records)
        self.assertTrue(result['supported']); self.assertEqual(result['retained_turns'], 1)
        self.assertEqual(len(result['turns'][0]['messages']), 2)
        self.assertEqual(result['rolled_back_turns'], 1)

    def test_encryption_status_nested_turn_and_future_metadata_fail_closed(self):
        changes = [({'encrypted_content':'PRIVATE_CIPHER'}, 'ENCRYPTED_MESSAGE_UNSUPPORTED'),
                   ({'status':'incomplete'}, 'INCOMPLETE_MESSAGE'),
                   ({'phase':'unknown'}, 'MESSAGE_PHASE_UNSUPPORTED'),
                   ({'internal_chat_message_metadata_passthrough': {'turn_id':'wrong'}}, 'MESSAGE_TURN_MISMATCH'),
                   ({'internal_chat_message_metadata_passthrough': {'content_item_kinds': []}}, 'MESSAGE_METADATA_UNSUPPORTED'),
                   ({'future_history': {}}, 'MESSAGE_FIELDS_UNSUPPORTED')]
        for fields, reason in changes:
            records = [self.meta, *turn('a')]; records[3]['payload'].update(fields)
            result = self.write(records)
            self.assertFalse(result['supported']); self.assertEqual(result['reason_code'], reason)
            self.assertNotIn('turns', result); self.assertNotIn('PRIVATE_', json.dumps(result))

    def test_matching_nested_turn_and_optional_metadata_are_not_emitted(self):
        records = [self.meta, *turn('a')]
        records[3]['payload'].update(status='completed', phase='commentary',
            internal_chat_message_metadata_passthrough=dict(turn_id='a', create_time=1.5))
        result = self.write(records); self.assertTrue(result['supported'])
        self.assertNotIn('internal_chat_message_metadata_passthrough', json.dumps(result))
