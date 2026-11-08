"""Synthetic source -> raw archive -> retained title -> checked apply workflow."""
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from recaplib.replay_title import suggest_replay
from recaplib.session_workflow import import_export, titles
from recaplib.title_proposal import preview, apply_preview, snapshot
from tests.test_replay_local import turn, event


class ReplayTitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'original.jsonl'; self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.records = [dict(type='session_meta', payload=dict(id='synthetic')), *turn('discarded'),
                        event('thread_rolled_back', num_turns=1), *turn('retained')]
        for record in self.records:
            if record['type'] == 'response_item': record['payload'].pop('id')
        self.write(); import_export(self.db, 'local', self.path, 'local-codex')

    def write(self):
        self.path.write_text(''.join(json.dumps(record) + '\n' for record in self.records))

    def suggest(self, path=None):
        return suggest_replay(self.db, 'local', 'synthetic', path or self.path)

    def test_retained_title_maps_real_archive_identity_and_keeps_raw_fingerprint(self):
        db_before = self.db.read_bytes(); raw_before = self.path.read_bytes()
        proposal = self.suggest()
        self.assertEqual(proposal['title'], 'Synthetic question retained')
        self.assertNotIn('Synthetic question discarded', json.dumps(proposal))
        mapping = proposal['projection_context']['evidence_mappings'][0]
        self.assertIsNone(mapping['source_message_id'])
        self.assertEqual(proposal['evidence_message_ids'], [mapping['archive_message_id']])
        self.assertNotEqual(mapping['archive_message_id'], mapping['projection_id'])
        rows, digest = snapshot(self.db, 'local', 'synthetic')
        self.assertEqual(len(rows), 4); self.assertEqual(proposal['content_sha256'], digest)
        self.assertEqual(db_before, self.db.read_bytes()); self.assertEqual(raw_before, self.path.read_bytes())

    def test_renamed_identical_source_uses_provenance_not_filename_ids(self):
        other = Path(self.tmp.name) / 'renamed.jsonl'; other.write_bytes(self.path.read_bytes())
        self.assertEqual(self.suggest(), self.suggest(other))
        import_export(self.db, 'local', other, 'local-codex')
        with self.assertRaisesRegex(ValueError, 'exactly one'): self.suggest(other)

    def test_unimported_bytes_or_missing_occurrence_rejected(self):
        self.path.write_bytes(self.path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError, 'exactly one'): self.suggest()
        self.write()
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("DELETE FROM export_provenance WHERE locator='line:4'")
            c.execute("DELETE FROM export_occurrences WHERE locator='line:4'"); c.commit()
        # Even removed-turn source messages must have verified raw archive evidence.
        with self.assertRaisesRegex(ValueError, 'exactly one'): self.suggest()

    def test_unsupported_projection_or_empty_retained_history_never_yields_title(self):
        self.records.append(dict(type='compacted', payload={})); self.write()
        with self.assertRaisesRegex(ValueError, 'COMPACTION_UNSUPPORTED'): self.suggest()
        self.records.pop(); self.records.append(event('thread_rolled_back', num_turns=1)); self.write()
        import_export(self.db, 'local', self.path, 'local-codex')
        with self.assertRaisesRegex(ValueError, 'no usable user'): self.suggest()

    def test_source_is_read_once_and_legacy_ledger_remains_compatible(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('DROP TABLE export_occurrences'); c.commit()
        original_read = Path.read_bytes; reads = []
        def tracked(path):
            if path == self.path: reads.append(path)
            return original_read(path)
        with patch.object(Path, 'read_bytes', tracked): self.suggest()
        self.assertEqual(len(reads), 1)

    def test_raw_content_and_title_revision_changes_block_stale_apply(self):
        reviewed = preview(self.db, self.suggest())
        titles(self.db, 'local', 'synthetic', 'Other reviewed title', 0)
        with self.assertRaises(ValueError): apply_preview(self.db, reviewed)
        reviewed = preview(self.db, self.suggest())
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE messages SET text='Changed discarded raw text' WHERE message_pk=(SELECT MIN(message_pk) FROM messages)")
            c.commit()
        with self.assertRaisesRegex(ValueError, 'snapshot'): apply_preview(self.db, reviewed)

    def test_explicit_ids_in_discarded_turns_are_also_verified(self):
        for index, record in enumerate(self.records):
            if record['type'] == 'response_item': record['payload']['id'] = f'explicit-{index}'
        self.write(); self.db.unlink(); import_export(self.db, 'local', self.path, 'local-codex')
        self.assertEqual(self.suggest()['title'], 'Synthetic question retained')
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE messages SET message_id='altered' WHERE message_id='explicit-3'")
            for table in ('export_provenance', 'export_occurrences'):
                c.execute(f"UPDATE {table} SET message='altered' WHERE message='explicit-3'")
            c.commit()
        with self.assertRaisesRegex(ValueError, 'explicit source ID'): self.suggest()

    def test_cli_e2e_raw_import_retained_suggestion_apply_search_and_manual_plan(self):
        def call(script, *args):
            result = subprocess.run([sys.executable, script, *map(str, args)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr); return json.loads(result.stdout)
        identity = ('--source', 'local', '--conversation', 'synthetic')
        proposal = call('recap.py', '--db', self.db, 'suggest-replay-title', self.path, *identity)
        self.assertEqual(proposal, call('replay_title.py', '--db', self.db, *identity, self.path))
        saved = Path(self.tmp.name) / 'proposal.json'; saved.write_text(json.dumps(proposal))
        reviewed = call('title_proposal.py', '--db', self.db, 'preview', saved); saved.write_text(json.dumps(reviewed))
        call('title_proposal.py', '--db', self.db, 'apply', saved)
        self.assertEqual(call('recap.py', '--db', self.db, 'list')['conversations'][0]['display_title'], 'Synthetic question retained')
        self.assertEqual(call('recap.py', '--db', self.db, 'find', 'discarded')['total_matches'], 1)
        plan = call('recap.py', '--db', self.db, 'export-title-plan', self.path, '--format', 'local-codex', *identity)
        self.assertEqual(plan['execution_status'], 'NOT_EXECUTED'); self.assertTrue(plan['extraction_warnings'])
        saved.write_text(json.dumps(plan))
        self.assertTrue(call('recap.py', '--db', self.db, 'check-title-plan', self.path, saved)['valid'])
