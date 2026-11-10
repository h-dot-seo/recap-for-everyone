"""Synthetic JSON snapshot isolation for preview and explicit title apply."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recaplib import title_proposal
from recaplib.session_workflow import import_export, titles
from recap import ingest
from tests._nesting import deep_json
from recaplib.title_proposal import apply_preview, preview, snapshot
from recaplib.title_suggestion import suggest


class TitlePreviewFreezeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        import_export(self.db, 'synthetic', 'examples/web-export.json', 'web')
        self.proposal = suggest(self.db, 'synthetic', 'synthetic-chat')
        self.proposal['context'] = dict(parts=[dict(label='Synthetic original metadata')])

    def test_preview_and_caller_nested_objects_are_independent_in_both_directions(self):
        original = copy.deepcopy(self.proposal)
        reviewed = preview(self.db, self.proposal)
        self.assertEqual(reviewed['proposal'], original)
        self.proposal['title'] = 'Later caller wording'
        self.proposal['evidence_message_ids'].clear()
        self.proposal['context']['parts'][0]['label'] = 'Later caller metadata'
        self.assertEqual(reviewed['proposal'], original)
        reviewed['proposal']['context']['parts'].append(dict(label='Only returned metadata'))
        self.assertEqual(len(self.proposal['context']['parts']), 1)
        self.assertEqual(reviewed['title_advisory']['character_count'], len(original['title']))
        self.assertEqual(apply_preview(self.db, reviewed)['display_title'], original['title'])

    def test_preview_freezes_before_reading_database(self):
        original = copy.deepcopy(self.proposal)
        real_snapshot = title_proposal._snapshot_rows
        def mutate(*args):
            self.proposal['title'] = 'Changed during snapshot read'
            self.proposal['evidence_message_ids'].clear()
            return real_snapshot(*args)
        with patch.object(title_proposal, '_snapshot_rows', mutate):
            reviewed = preview(self.db, self.proposal)
        self.assertEqual(reviewed['proposal'], original)

    def test_apply_freezes_before_validation_and_write(self):
        reviewed = preview(self.db, self.proposal)
        original_title = reviewed['proposal']['title']
        real_preview = title_proposal.preview
        def mutate_after_validation(*args, **kwargs):
            result = real_preview(*args, **kwargs)
            reviewed['proposal']['title'] = 'Changed after validation'
            reviewed['proposal']['evidence_message_ids'].clear()
            reviewed['expected_revision'] = 999
            return result
        with patch.object(title_proposal, 'preview', mutate_after_validation):
            result = apply_preview(self.db, reviewed)
        self.assertEqual(result['display_title'], original_title)

    def test_replacement_is_operator_wording_and_does_not_modify_input(self):
        original = copy.deepcopy(self.proposal)
        reviewed = preview(self.db, self.proposal, 'Synthetic chosen wording')
        self.assertEqual(self.proposal, original)
        self.assertEqual(reviewed['proposal']['provider'], 'operator')
        self.assertNotIn('context', reviewed['proposal'])
        reviewed['proposal']['evidence_message_ids'].clear()
        self.assertEqual(self.proposal['evidence_message_ids'], original['evidence_message_ids'])

    @staticmethod
    def invalid_values():
        cycle = []; cycle.append(cycle)
        return [float('nan'), float('inf'), -float('inf'), object(), {'not-json'}, '\ud800', cycle]

    def test_invalid_json_metadata_rejected_before_preview_database_access(self):
        before = self.db.read_bytes()
        for value in self.invalid_values():
            proposal = dict(self.proposal, extra=value)
            with self.subTest(kind=type(value).__name__), patch.object(title_proposal, 'readonly') as read:
                with self.assertRaises(ValueError) as caught:
                    preview(self.db, proposal)
                read.assert_not_called()
                self.assertNotIn('Traceback', str(caught.exception))
        self.assertEqual(self.db.read_bytes(), before)

    def test_invalid_review_envelope_rejected_before_validation_or_write(self):
        reviewed = preview(self.db, self.proposal)
        before = self.db.read_bytes()
        for value in self.invalid_values():
            candidate = dict(reviewed, retained_metadata=value)
            with self.subTest(kind=type(value).__name__), patch.object(title_proposal, 'preview') as validate:
                with self.assertRaises(ValueError):
                    apply_preview(self.db, candidate)
                validate.assert_not_called()
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(titles(self.db, 'synthetic', 'synthetic-chat')['revision'], 0)

    def test_advisory_remains_descriptive_not_an_authentication_token(self):
        reviewed = preview(self.db, self.proposal)
        reviewed['title_advisory'] = dict(operator_note='Synthetic edited advisory')
        self.assertEqual(apply_preview(self.db, reviewed)['display_title'], self.proposal['title'])

    def test_invalid_identity_types_fail_before_database_reads_in_all_paths(self):
        for source, conversation in [(value, 'synthetic-chat') for value in (None, '', ' ', 1, True, False, [], {})] + [
                ('synthetic', value) for value in (None, '', 1, True, False, [], {})]:
            proposal = dict(self.proposal, source=source, conversation=conversation)
            reviewed = dict(proposal=proposal, expected_revision=0)
            for operation in (lambda: snapshot(self.db, source, conversation),
                              lambda: preview(self.db, proposal),
                              lambda: apply_preview(self.db, reviewed)):
                with self.subTest(source=source, conversation=conversation), patch.object(title_proposal, 'readonly') as read:
                    with self.assertRaises(ValueError):
                        operation()
                    read.assert_not_called()

    def test_numeric_and_boolean_identities_cannot_select_literal_string_ids(self):
        path = Path(self.tmp.name) / 'synthetic-identities.jsonl'
        path.write_text(json.dumps(dict(conversation_id='1', message_id='u', role='user',
            timestamp='synthetic', text='Synthetic numeric-looking identity')) + '\n')
        ingest(self.db, '1', path)
        valid = suggest(self.db, '1', '1')
        before = self.db.read_bytes()
        for source, conversation in ((1, '1'), ('1', 1), (1, 1), (True, '1'), ('1', True)):
            candidate = dict(valid, source=source, conversation=conversation)
            with self.subTest(source=source, conversation=conversation):
                with self.assertRaises(ValueError):
                    preview(self.db, candidate)
                with self.assertRaises(ValueError):
                    apply_preview(self.db, dict(proposal=candidate, expected_revision=0))
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(apply_preview(self.db, preview(self.db, valid))['display_title'], valid['title'])

    def test_literal_unicode_whitespace_and_quoted_identities_are_not_rewritten(self):
        path = Path(self.tmp.name) / 'synthetic-literal-identities.jsonl'
        cases = [('합성 원본', '대화'), (' source with spaces ', ' '),
                 ('source \"quoted\"', "conversation 'quoted'"), ('1', '01')]
        for source, conversation in cases:
            path.write_text(json.dumps(dict(conversation_id=conversation, message_id='u', role='user',
                timestamp='synthetic', text='Synthetic literal identity')) + '\n')
            ingest(self.db, source, path)
            with self.subTest(source=source, conversation=conversation):
                proposal = suggest(self.db, source, conversation)
                reviewed = preview(self.db, proposal)
                self.assertEqual(reviewed['proposal']['source'], source)
                self.assertEqual(reviewed['proposal']['conversation'], conversation)
                self.assertEqual(len(snapshot(self.db, source, conversation)[0]), 1)
                self.assertEqual(apply_preview(self.db, reviewed)['display_title'], proposal['title'])

    def test_deep_title_files_fail_cleanly_in_both_cli_entry_points(self):
        path = Path(self.tmp.name) / 'deep-synthetic.json'
        path.write_text('{"SYNTHETIC_PRIVATE":' + deep_json() + '}')
        missing = Path(self.tmp.name) / 'missing.sqlite'
        before = self.db.read_bytes()
        for database in (missing, self.db):
            for script, command in (('recap.py', 'preview-title'), ('recap.py', 'apply-title'),
                                    ('title_proposal.py', 'preview'), ('title_proposal.py', 'apply')):
                with self.subTest(database=database.name, script=script, command=command):
                    result = subprocess.run([sys.executable, script, '--db', str(database), command, str(path)],
                                            capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, '')
                    self.assertIn('nesting is too deep', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertNotIn('SYNTHETIC_PRIVATE', result.stderr)
                    self.assertFalse(missing.exists())
                    self.assertEqual(self.db.read_bytes(), before)

    def test_both_cli_preview_apply_flows_retain_json_metadata(self):
        for script, preview_command, apply_command in (('recap.py', 'preview-title', 'apply-title'),
                                                       ('title_proposal.py', 'preview', 'apply')):
            with self.subTest(script=script):
                path = Path(self.tmp.name) / 'proposal.json'
                path.write_text(json.dumps(self.proposal))
                result = subprocess.run([sys.executable, script, '--db', str(self.db), preview_command, str(path)],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                reviewed = json.loads(result.stdout)
                self.assertEqual(reviewed['proposal'], self.proposal)
                path.write_text(json.dumps(reviewed))
                result = subprocess.run([sys.executable, script, '--db', str(self.db), apply_command, str(path)],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['display_title'], self.proposal['title'])


if __name__ == '__main__':
    unittest.main()
