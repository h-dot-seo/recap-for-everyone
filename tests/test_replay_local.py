"""Strict synthetic turn grammar; unsupported inputs never yield partial text."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from recaplib.replay_local import reconstruct


def event(kind, **values):
    return dict(type='event_msg', payload=dict(type=kind, **values))


def turn(identity, aliases=False):
    text = 'Synthetic question ' + identity
    return [event('turn_started' if aliases else 'task_started', turn_id=identity),
            event('user_message', message=text),
            dict(type='response_item', payload=dict(type='message', id=identity+'u', role='user',
                 content=[dict(type='input_text', text=text)])),
            dict(type='response_item', payload=dict(type='message', id=identity+'a', role='assistant',
                 content=[dict(type='output_text', text='Synthetic answer ' + identity)])),
            event('turn_complete' if aliases else 'task_complete', turn_id=identity)]


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'rollout.jsonl'
        self.meta = dict(type='session_meta', payload=dict(id='synthetic'))

    def run_records(self, records):
        self.path.write_text(''.join(json.dumps(record) + '\n' for record in records))
        before = self.path.read_bytes(); result = reconstruct(self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(result.get('original_sha256'), hashlib.sha256(before).hexdigest())
        return result

    def reject(self, records, code):
        result = self.run_records(records)
        self.assertFalse(result['supported']); self.assertEqual(result['reason_code'], code)
        self.assertFalse(result['partial_output']); self.assertNotIn('turns', result)
        self.assertNotIn('Synthetic question', json.dumps(result))

    def test_rollback_complete_turns_then_new_turn_preserves_line_provenance(self):
        result = self.run_records([self.meta, *turn('a'), *turn('b', True),
                                   event('thread_rolled_back', num_turns=1), *turn('c')])
        self.assertTrue(result['supported']); self.assertFalse(result['full_model_history_reconstructed'])
        self.assertEqual([t['turn_id'] for t in result['turns']], ['a', 'c'])
        self.assertEqual(result['rolled_back_turns'], 1)
        self.assertEqual(result['turns'][0]['messages'][0]['origin_locator'], 'line:4')
        self.assertNotIn('Synthetic question b', json.dumps(result))

    def test_repeated_rollback_zero_and_all_turns(self):
        result = self.run_records([self.meta, *turn('a'), *turn('b'), event('thread_rolled_back', num_turns=0),
                                   event('thread_rolled_back', num_turns=1), event('thread_rolled_back', num_turns=1)])
        self.assertTrue(result['supported']); self.assertEqual(result['turns'], [])
        self.assertEqual(result['rolled_back_turns'], 2)

    def test_invalid_rollback_counts_and_active_rollback(self):
        for count in (-1, True, 1.0, 2, 2**32, None):
            self.reject([self.meta, *turn('a'), event('thread_rolled_back', num_turns=count)], 'UNRESOLVED_ROLLBACK_COUNT')
        self.reject([self.meta, event('task_started', turn_id='a'), event('thread_rolled_back', num_turns=0)], 'ROLLBACK_INSIDE_TURN')

    def test_compaction_forks_and_unknown_records_fail_closed(self):
        self.reject([self.meta, *turn('a'), dict(type='compacted', payload=dict(replacement_history=[]))], 'COMPACTION_UNSUPPORTED')
        for field in ('history_base', 'forked_from_id', 'parent_thread_id', 'history_mode', 'subagent_history_start_ordinal'):
            meta = dict(type='session_meta', payload=dict(id='synthetic', **{field: 'PRIVATE_VALUE'}))
            self.reject([meta, *turn('a')], 'UNRESOLVED_HISTORY')
        self.reject([self.meta, *turn('a'), event('token_count')], 'UNSCOPED_TOKEN_COUNT')
        self.reject([self.meta, *turn('a'), dict(type='turn_context', payload={})], 'UNSCOPED_TURN_CONTEXT')

    def test_incomplete_overlapping_reused_and_mismatched_turns(self):
        self.reject([self.meta, *turn('a')[:-1]], 'INCOMPLETE_TURN')
        self.reject([self.meta, event('task_started', turn_id='a'), event('task_started', turn_id='b')], 'NESTED_TURN')
        self.reject([self.meta, *turn('a'), *turn('a')], 'INVALID_OR_REUSED_TURN_ID')
        records = [self.meta, *turn('a')]; records[-1]['payload']['turn_id'] = 'wrong'
        self.reject(records, 'UNMATCHED_TURN_COMPLETION')

    def test_user_evidence_and_text_only_contract(self):
        records = [self.meta, *turn('a')]; records[2]['payload']['message'] = 'mismatch'
        self.reject(records, 'USER_EVENT_MISMATCH')
        records = [self.meta, *turn('a')]; del records[2]
        self.reject(records, 'MISSING_USER_EVENT')
        records = [self.meta, *turn('a')]; records[3]['payload']['content'] = [dict(type='input_image', text='private')]
        self.reject(records, 'NON_TEXT_UNSUPPORTED')
        records = [self.meta, *turn('a')]; records[4]['payload']['role'] = 'user'
        self.reject(records, 'AMBIGUOUS_USER_BOUNDARY')
        records = [self.meta, *turn('a')]; records[3]['payload']['turn_id'] = 'other'
        self.reject(records, 'MESSAGE_TURN_MISMATCH')

    def test_causal_root_and_session_source_boundaries(self):
        meta = dict(type='session_meta', payload=dict(id='synthetic', session_id='other'))
        self.reject([meta, *turn('a')], 'UNRESOLVED_HISTORY')
        meta = dict(type='session_meta', payload=dict(id='synthetic', source={'subagent': 'private'}))
        self.reject([meta, *turn('a')], 'SESSION_SOURCE_UNSUPPORTED')
        records = [self.meta, *turn('a')]; records[-1]['payload']['root_turn_id'] = 'other'
        self.reject(records, 'UNRESOLVED_HISTORY')

    def test_media_and_unknown_user_event_fields_fail_closed(self):
        for field in ('images', 'local_images', 'text_elements', 'file_ids', 'audio',
                      'audio_references', 'audio_order', 'local_audio', 'image_details',
                      'file_id_details', 'image_order', 'local_image_details'):
            records = [self.meta, *turn('a')]; records[2]['payload'][field] = ['PRIVATE_MEDIA']
            self.reject(records, 'NON_TEXT_UNSUPPORTED')
        records = [self.meta, *turn('a')]; records[2]['payload']['future_media'] = 'private'
        self.reject(records, 'USER_EVENT_FIELDS_UNSUPPORTED')

    def test_additional_history_markers_and_unknown_metadata_fail_closed(self):
        for field, value in [('forked_from_ordinal_exclusive', 4), ('thread_source', 'subagent'),
                             ('attached_thread', True)]:
            meta = dict(type='session_meta', payload=dict(id='synthetic', **{field: value}))
            self.reject([meta, *turn('a')], 'UNRESOLVED_HISTORY')
        meta = dict(type='session_meta', payload=dict(id='synthetic', future_history={}))
        self.reject([meta, *turn('a')], 'SESSION_METADATA_UNSUPPORTED')

    def test_cli_equivalence_failure_exit_and_no_database_access(self):
        self.run_records([self.meta, *turn('a')]); db = Path(self.tmp.name) / 'never.sqlite'
        outputs = []
        for args in [('replay_local.py', self.path), ('recap.py', '--db', db, 'replay-local', self.path)]:
            result = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr); outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0], outputs[1]); self.assertFalse(db.exists())
        self.path.write_text('{bad json}\n')
        for args in [('replay_local.py', self.path), ('recap.py', 'replay-local', self.path)]:
            result = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 1); self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(json.loads(result.stdout)['reason_code'], 'INVALID_JSON')
