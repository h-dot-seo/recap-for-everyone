"""Synthetic explicit-legacy compatibility; no expanded history reconstruction."""
import json
import tempfile
import unittest
from pathlib import Path

from replay_local import reconstruct_bytes
from replay_title import suggest_replay
from session_workflow import import_export
from test_replay_local import event, turn
from title_proposal import snapshot


class ReplayHistoryModeTests(unittest.TestCase):
    @staticmethod
    def raw(metadata):
        records = [dict(type='session_meta', payload=dict(id='synthetic', **metadata)),
                   *turn('discarded'), event('thread_rolled_back', num_turns=1),
                   *turn('retained')]
        return ''.join(json.dumps(record) + '\n' for record in records).encode()

    def test_absent_null_and_explicit_legacy_preserve_retained_turns(self):
        for metadata in ({}, {'history_mode': None}, {'history_mode': 'legacy'}):
            with self.subTest(metadata=metadata):
                result = reconstruct_bytes(self.raw(metadata))
                self.assertTrue(result['supported'])
                self.assertEqual(result['retained_turns'], 1)
                self.assertEqual(result['rolled_back_turns'], 1)
                self.assertEqual(result['turns'][0]['turn_id'], 'retained')
                self.assertFalse(result['full_model_history_reconstructed'])

    def test_paginated_unknown_and_malformed_modes_fail_closed(self):
        for mode in ('paginated', 'future', '', 'Legacy', False, True, 0, 1, [], {}):
            with self.subTest(mode=mode):
                result = reconstruct_bytes(self.raw({'history_mode': mode}))
                self.assertFalse(result['supported'])
                self.assertEqual(result['reason_code'], 'UNRESOLVED_HISTORY')
                self.assertFalse(result['partial_output'])
                self.assertNotIn('turns', result)

    def test_explicit_legacy_does_not_override_history_guards(self):
        fields = ('history_base', 'forked_from_id', 'parent_thread_id',
                  'subagent_history_start_ordinal', 'forked_from_ordinal_exclusive',
                  'thread_source', 'attached_thread')
        for field in fields:
            with self.subTest(field=field):
                value = True if field == 'attached_thread' else 'synthetic-marker'
                result = reconstruct_bytes(self.raw({'history_mode': 'legacy', field: value}))
                self.assertFalse(result['supported'])
                self.assertEqual(result['reason_code'], 'UNRESOLVED_HISTORY')
                self.assertNotIn('turns', result)

    def test_legacy_retained_title_keeps_raw_archive_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.jsonl'
            db = Path(tmp) / 'archive.sqlite'
            raw = self.raw({'history_mode': 'legacy'})
            path.write_bytes(raw)
            import_export(db, 'synthetic', path, 'local-codex')
            before = db.read_bytes()
            proposal = suggest_replay(db, 'synthetic', 'synthetic', path)
            self.assertEqual(proposal['title'], 'Synthetic question retained')
            self.assertEqual(proposal['projection_context']['rolled_back_turns'], 1)
            rows, digest = snapshot(db, 'synthetic', 'synthetic')
            self.assertEqual(len(rows), 4)
            self.assertEqual(proposal['content_sha256'], digest)
            self.assertEqual(db.read_bytes(), before)
            self.assertEqual(path.read_bytes(), raw)
