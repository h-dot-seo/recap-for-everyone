"""Synthetic regressions for explicit, source-attributed title occurrences."""
import hashlib
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from attributed_title import attributed_evidence, suggest_attributed
from session_workflow import import_export, titles
from title_proposal import apply_preview, preview, snapshot
from title_suggestion import excerpt


ROOT = Path(__file__).resolve().parent


def label(kind):
    return {'provenance': {'type': kind}}


def message(identity, texts, kinds=None, role='user'):
    payload = dict(type='message', role=role,
                   content=[dict(type='input_text' if role == 'user' else 'output_text', text=t) for t in texts])
    if identity is not None:
        payload['id'] = identity
    if kinds is not None:
        payload['internal_chat_message_metadata_passthrough'] = dict(content_item_metadata=[label(k) for k in kinds])
    return dict(type='response_item', timestamp='2026-01-01T00:00:00Z', payload=payload)


class AttributedMessageSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / 'synthetic.jsonl'
        self.db = self.directory / 'archive.sqlite'
        self.records = [dict(type='session_meta', payload=dict(id='synthetic')),
                        message('opener', ['Help me think through a project'], ['user']),
                        message('later', ['Synthetic harness instructions', '합성 달력 만들기'], ['harness', 'user']),
                        message('assistant', ['Synthetic assistant answer'], ['user'], role='assistant'),
                        message('unknown', ['Unattributed synthetic text']),
                        message('empty', ['   ', 'Excluded harness'], ['user', 'harness']),
                        message('unusable', ['!!! 👀'], ['user'])]

    def write(self, imported=True):
        self.path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in self.records), encoding='utf-8')
        if imported:
            import_export(self.db, 'local', self.path, 'local-codex')

    def suggest(self, message_id='later', origin_locator=None, path=None):
        return suggest_attributed(self.db, 'local', 'synthetic', path or self.path,
                                  message_id=message_id, origin_locator=origin_locator)

    def sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute(statement, parameters)

    def cli(self, script, *args, success=True):
        result = subprocess.run([sys.executable, str(ROOT / script), *map(str, args)],
                                capture_output=True, text=True, encoding='utf-8',
                                env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('Traceback', result.stderr)
        return result

    def test_later_request_preserves_full_digest_coverage_and_raw_text(self):
        self.write()
        before = (self.path.read_bytes(), self.db.read_bytes())
        default = self.suggest(message_id=None)
        proposal = self.suggest()
        self.assertEqual(default['title'], 'Help me think through a project')
        self.assertEqual(proposal['title'], '합성 달력 만들기')
        self.assertEqual(proposal['evidence_message_ids'], ['later'])
        self.assertEqual(proposal['evidence_selection'], dict(mode='explicit_source_attributed_occurrence',
            message_id='later', origin_locator='line:3',
            scope='verified user-labeled text occurrence in the selected raw conversation'))
        context = proposal['attribution_context']
        self.assertEqual(context['evidence_parts'], [dict(message_id='later', origin_locator='line:3', content_indices=[1])])
        self.assertEqual(context['coverage'], default['attribution_context']['coverage'])
        self.assertFalse(context['producer_attribution_authenticated'])
        self.assertEqual(context['original_sha256'], hashlib.sha256(before[0]).hexdigest())
        rows, digest = snapshot(self.db, 'local', 'synthetic')
        self.assertEqual(proposal['content_sha256'], digest)
        self.assertEqual(proposal['content_sha256'], default['content_sha256'])
        self.assertEqual(next(r['text'] for r in rows if r['message_id'] == 'later'),
                         'Synthetic harness instructions\n합성 달력 만들기')
        self.assertEqual((self.path.read_bytes(), self.db.read_bytes()), before)

    def test_no_options_exactly_preserves_prior_proposal_shape(self):
        self.write()
        rows, digest, context = attributed_evidence(self.db, 'local', 'synthetic', self.path)
        extracted = excerpt([dict(message_id=r['origin_locator'], role=r['role'], text=r['text']) for r in rows])
        parts = context['attribution_context']['evidence_parts']
        context['attribution_context']['evidence_parts'] = [p for p in parts if p['origin_locator'] in extracted['evidence_message_ids']]
        extracted['evidence_message_ids'] = [p['message_id'] for p in context['attribution_context']['evidence_parts']]
        expected = dict(source='local', conversation='synthetic', provider='local-extractive',
                        content_sha256=digest, **extracted, **context)
        self.assertEqual(suggest_attributed(self.db, 'local', 'synthetic', self.path), expected)
        self.assertEqual(self.suggest(message_id=None), expected)
        self.assertNotIn('evidence_selection', expected)

    def test_invalid_selector_arguments_fail_before_any_source_or_database_io(self):
        cases = [dict(message_id=value) for value in ('', 0, False, [], {})]
        cases += [dict(message_id='later', origin_locator=value) for value in
                  ('', 'line:0', 'line:01', 'line:-1', 'line:+1', 'line:1.0', 'line:١',
                   'line:1\n', ' line:1', 'line:1 ', 'LINE:1', 'line:1:2', 1, False, [], {})]
        cases += [dict(origin_locator='line:3')]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), patch('attributed_title.attributed_evidence', side_effect=AssertionError('source/database I/O')):
                with self.assertRaises(ValueError):
                    suggest_attributed(self.db, 'local', 'synthetic', self.path, **kwargs)
        self.assertFalse(self.db.exists())
        self.assertFalse(self.path.exists())

    def test_ids_are_exact_without_trimming_casefolding_or_normalization(self):
        self.records.insert(3, message(' later ', ['Separate exact-space identity'], ['user']))
        self.write()
        self.assertEqual(self.suggest(' later ')['title'], 'Separate exact-space identity')
        self.assertEqual(self.suggest('later')['title'], '합성 달력 만들기')
        for identity in ('Later', 'LATER', 'later\n', ' missing ', ' '):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                self.suggest(identity)

    def test_ineligible_missing_and_wrong_locator_never_fall_back(self):
        self.write()
        before = self.db.read_bytes()
        for identity in ('assistant', 'unknown', 'empty', 'unusable', 'missing'):
            for locator in (None, 'line:3'):
                with self.subTest(identity=identity, locator=locator), self.assertRaises(ValueError):
                    self.suggest(identity, locator)
        for locator in ('line:1', 'line:2', 'line:4', 'line:999'):
            with self.subTest(locator=locator), self.assertRaises(ValueError):
                self.suggest('later', locator)
        self.assertEqual(self.db.read_bytes(), before)

    def test_off_conversation_id_never_selects_other_archive_conversation(self):
        self.write()
        other = self.directory / 'other.jsonl'
        records = [dict(type='session_meta', payload=dict(id='other')),
                   message('foreign', ['Other conversation request'], ['user'])]
        other.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
        import_export(self.db, 'local', other, 'local-codex')
        with self.assertRaises(ValueError):
            self.suggest('foreign')

    def test_duplicate_archive_id_requires_locator_and_preserves_part_positions(self):
        parts = ['First attributed request', 'Second attributed request']
        self.records = self.records[:1] + [message('duplicate', parts, ['user', 'harness']),
                                           message('duplicate', parts, ['harness', 'user'])]
        self.write()
        with self.assertRaises(ValueError):
            self.suggest('duplicate')
        for line, index in ((2, 0), (3, 1)):
            proposal = self.suggest('duplicate', f'line:{line}')
            self.assertEqual(proposal['title'], parts[index])
            self.assertEqual(proposal['attribution_context']['evidence_parts'],
                             [dict(message_id='duplicate', origin_locator=f'line:{line}', content_indices=[index])])
            self.assertEqual(proposal['attribution_context']['coverage']['selected_user_text_parts'], 2)
        self.assertEqual(len(snapshot(self.db, 'local', 'synthetic')[0]), 1)

    def test_identical_duplicate_excerpt_still_requires_locator(self):
        self.records = self.records[:1] + [message('duplicate', ['Identical request'], ['user'])] * 2
        self.write()
        with self.assertRaises(ValueError):
            self.suggest('duplicate')
        for line in (2, 3):
            self.assertEqual(self.suggest('duplicate', f'line:{line}')['evidence_selection']['origin_locator'], f'line:{line}')

    def test_duplicate_noneligible_occurrence_does_not_create_false_ambiguity(self):
        parts = ['Only eligible occurrence', 'Harness text']
        self.records = self.records[:1] + [message('duplicate', parts, ['user', 'harness']),
                                           message('duplicate', parts, ['harness', 'harness'])]
        self.write()
        self.assertEqual(self.suggest('duplicate')['evidence_selection']['origin_locator'], 'line:2')
        with self.assertRaises(ValueError):
            self.suggest('duplicate', 'line:3')

    def test_selected_greeting_retains_greeting_fallback_and_never_uses_later_request(self):
        self.records[1] = message('opener', ['안녕하세요!'], ['user'])
        self.write()
        proposal = self.suggest('opener')
        self.assertEqual(proposal['title'], '안녕하세요!')
        self.assertEqual(proposal['selection_method'], 'first_user_greeting_fallback')
        self.assertEqual(self.suggest(message_id=None)['title'], '합성 달력 만들기')

    def test_selected_excerpt_retains_eighty_codepoint_limit(self):
        text = '합성달력' * 30
        self.records[2] = message('later', [text], ['user'])
        self.write()
        proposal = self.suggest()
        self.assertEqual(proposal['title'], text[:80])
        self.assertTrue(proposal['truncated'])
        self.assertEqual(snapshot(self.db, 'local', 'synthetic')[0][1]['text'], text)

    def test_locator_cannot_bypass_unrelated_bad_attribution(self):
        self.records[1]['payload']['internal_chat_message_metadata_passthrough']['content_item_metadata'] = []
        self.write()
        with self.assertRaises(ValueError):
            self.suggest(origin_locator='line:3')

    def test_locator_cannot_bypass_malformed_source_or_changed_bytes(self):
        self.write()
        original = self.path.read_bytes()
        for suffix in (b'\n', b'{invalid json}\n'):
            self.path.write_bytes(original + suffix)
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                self.suggest(origin_locator='line:3')
        self.path.write_bytes(original)
        self.assertEqual(self.suggest(origin_locator='line:3')['title'], '합성 달력 만들기')

    def test_locator_cannot_bypass_unrelated_archive_content_role_or_timestamp_change(self):
        self.write()
        for column, value in (('text', 'Changed answer'), ('role', 'system'), ('timestamp', 'changed')):
            with closing(sqlite3.connect(self.db)) as connection:
                original = connection.execute(f'SELECT {column} FROM messages WHERE message_id=?', ('assistant',)).fetchone()[0]
            self.sql(f'UPDATE messages SET {column}=? WHERE message_id=?', (value, 'assistant'))
            with self.subTest(column=column), self.assertRaises(ValueError):
                self.suggest(origin_locator='line:3')
            self.sql(f'UPDATE messages SET {column}=? WHERE message_id=?', (original, 'assistant'))

    def test_locator_cannot_bypass_missing_unrelated_provenance(self):
        self.write()
        for table in ('export_provenance', 'export_occurrences'):
            self.sql(f"UPDATE {table} SET locator='line:999' WHERE message='assistant'")
        with self.assertRaises(ValueError):
            self.suggest(origin_locator='line:3')

    def test_locator_cannot_bypass_mismatched_explicit_archive_identity(self):
        self.write()
        for table in ('export_provenance', 'export_occurrences'):
            self.sql(f"UPDATE {table} SET message='renamed-assistant' WHERE message='assistant'")
        self.sql("UPDATE messages SET message_id='renamed-assistant' WHERE message_id='assistant'")
        with self.assertRaises(ValueError):
            self.suggest(origin_locator='line:3')

    def test_renamed_idless_source_uses_actual_archive_identity(self):
        self.records[2]['payload'].pop('id')
        self.write()
        renamed = self.directory / 'renamed.jsonl'
        renamed.write_bytes(self.path.read_bytes())
        identity = next(r['message_id'] for r in snapshot(self.db, 'local', 'synthetic')[0] if '합성' in r['text'])
        original = self.suggest(identity, 'line:3')
        self.assertEqual(self.suggest(identity, 'line:3', renamed), original)
        self.assertEqual(original['evidence_selection']['message_id'], identity)
        self.assertEqual(original['evidence_message_ids'], [identity])

    def test_valid_locator_cannot_resolve_ambiguous_idless_archive_association(self):
        self.records[2]['payload'].pop('id')
        self.write()
        identity = next(r['message_id'] for r in snapshot(self.db, 'local', 'synthetic')[0] if '합성' in r['text'])
        renamed = self.directory / 'renamed.jsonl'
        renamed.write_bytes(self.path.read_bytes())
        import_export(self.db, 'local', renamed, 'local-codex')
        for source_path in (self.path, renamed):
            with self.subTest(path=source_path), self.assertRaises(ValueError):
                self.suggest(identity, 'line:3', source_path)

    def test_locator_counts_blank_physical_lines_and_not_unicode_separators(self):
        self.records[2]['payload']['content'][1]['text'] = '합성\u2028달력 만들기'
        encoded = [json.dumps(record, ensure_ascii=False).encode('utf-8') for record in self.records]
        self.path.write_bytes(b'\xef\xbb\xbf' + encoded[0] + b'\r\n\r\n' + encoded[1] + b'\r' +
                              b'\n'.join(encoded[2:]) + b'\n')
        import_export(self.db, 'local', self.path, 'local-codex')
        proposal = self.suggest(origin_locator='line:4')
        self.assertEqual(proposal['title'], '합성 달력 만들기')
        self.assertEqual(proposal['evidence_selection']['origin_locator'], 'line:4')
        with self.assertRaises(ValueError):
            self.suggest(origin_locator='line:3')

    def test_explicit_preview_apply_rejects_stale_title_and_unselected_content(self):
        self.write()
        reviewed = preview(self.db, self.suggest())
        titles(self.db, 'local', 'synthetic', 'Other title', 0)
        with self.assertRaises(ValueError):
            apply_preview(self.db, reviewed)
        reviewed = preview(self.db, self.suggest())
        self.sql("UPDATE messages SET text='Changed unselected opener' WHERE message_id='opener'")
        with self.assertRaises(ValueError):
            apply_preview(self.db, reviewed)

    def test_both_cli_entrypoints_match_api_and_write_native_utf8_without_mutation(self):
        self.write()
        before = (self.path.read_bytes(), self.db.read_bytes())
        identity = ('--source', 'local', '--conversation', 'synthetic', '--message', 'later', '--origin-locator', 'line:3')
        expected = self.suggest(origin_locator='line:3')
        for script, prefix in (('recap.py', ('--db', self.db, 'suggest-attributed-title')),
                               ('attributed_title.py', ('--db', self.db))):
            with self.subTest(script=script):
                self.assertEqual(self.cli(script, *prefix, self.path, *identity), expected)
                saved = self.directory / (script + '.json')
                receipt = self.cli(script, *prefix, self.path, *identity, '--output', saved)
                self.assertEqual(receipt['document_kind'], 'proposal')
                self.assertEqual(receipt['encoding'], 'UTF-8')
                self.assertIn('합성 달력 만들기'.encode('utf-8'), saved.read_bytes())
                self.assertEqual(json.loads(saved.read_text(encoding='utf-8')), expected)
        self.assertEqual((self.path.read_bytes(), self.db.read_bytes()), before)

    def test_cli_selection_failure_never_echoes_private_id_marker(self):
        self.write()
        marker = 'synthetic-private-selector-marker-123'
        before = self.db.read_bytes()
        for script, prefix in (('recap.py', ('--db', self.db, 'suggest-attributed-title')),
                               ('attributed_title.py', ('--db', self.db))):
            result = self.cli(script, *prefix, self.path, '--source', 'local',
                              '--conversation', 'synthetic', '--message', marker, success=False)
            self.assertNotIn(marker, result.stderr)
            self.assertEqual(result.stderr, 'selected message must identify exactly one user-attributed '
                             'source occurrence; use its origin locator when repeated\n')
        self.assertEqual(self.db.read_bytes(), before)

    def test_cli_invalid_selectors_do_not_create_database_or_output(self):
        for script, prefix in (('recap.py', ('--db', self.db, 'suggest-attributed-title')),
                               ('attributed_title.py', ('--db', self.db))):
            for selection in (('--origin-locator', 'line:3'), ('--message', ''),
                              ('--message', 'later', '--origin-locator', 'line:01')):
                with self.subTest(script=script, selection=selection):
                    output = self.directory / 'must-not-exist.json'
                    result = self.cli(script, *prefix, self.path, '--source', 'local',
                                      '--conversation', 'synthetic', *selection, '--output', output, success=False)
                    self.assertNotIn('No such file', result.stderr)
                    self.assertFalse(self.db.exists())
                    self.assertFalse(output.exists())

    def test_rejected_candidate_selection_has_fixed_error_without_content_leak(self):
        self.write()
        expected = ('selected message must identify exactly one user-attributed source occurrence; '
                    'use its origin locator when repeated')
        for identity, locator in (('missing', None), ('assistant', None), ('empty', None),
                                  ('unknown', None), ('later', 'line:2')):
            with self.subTest(identity=identity, locator=locator), self.assertRaises(ValueError) as error:
                self.suggest(identity, locator)
            self.assertEqual(str(error.exception), expected)

    def test_exact_documented_workflow_changes_only_explicitly_applied_title(self):
        document = (ROOT / 'docs' / 'ATTRIBUTED_MESSAGE_SELECTION.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', document, flags=re.S)
        commands = [shlex.split(line) for block in blocks for line in block.splitlines() if line.strip()]
        self.assertEqual(len(commands), 10)
        # Tokenize first: replacing a Windows temporary path before shlex would
        # interpret backslashes as shell escapes and corrupt the argument.
        work = self.directory / 'documented demo with spaces'
        fixture = ROOT / 'examples' / 'title-focus-attributed.jsonl'
        original = fixture.read_bytes()
        db = work / 'archive.sqlite'
        baseline = None
        baseline_db = None
        for tokens in commands:
            tokens = [str(work) + token[len('../recap-attributed-focus-demo'):]
                      if token.startswith('../recap-attributed-focus-demo') else
                      str(fixture) if token == 'examples/title-focus-attributed.jsonl' else token
                      for token in tokens]
            if tokens[0] == 'mkdir':
                Path(tokens[1]).mkdir()
                continue
            self.assertEqual(tokens[:2], ['python', 'recap.py'])
            before = db.read_bytes() if db.exists() else None
            result = self.cli('recap.py', *tokens[2:])
            if 'import' in tokens:
                with closing(sqlite3.connect(db)) as connection:
                    baseline = {table: connection.execute('SELECT * FROM ' + table).fetchall()
                                for table in ('messages', 'export_provenance', 'export_occurrences')}
                baseline_db = db.read_bytes()
                self.assertEqual(len(baseline['messages']), 4)
            elif 'apply-title' not in tokens:
                self.assertEqual(db.read_bytes(), before)
            if '--output' in tokens:
                self.assertEqual(result['encoding'], 'UTF-8')
                self.assertEqual(result['status'], 'SAVED')
                output = Path(tokens[tokens.index('--output') + 1])
                self.assertEqual(result['sha256'], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(fixture.read_bytes(), original)
        primary = json.loads((work / 'proposal.json').read_text(encoding='utf-8'))
        repeated = json.loads((work / 'occurrence-proposal.json').read_text(encoding='utf-8'))
        primary_review = json.loads((work / 'reviewed.json').read_text(encoding='utf-8'))
        repeated_review = json.loads((work / 'occurrence-reviewed.json').read_text(encoding='utf-8'))
        self.assertEqual(primary['title'], 'Compare synthetic orchard irrigation designs')
        self.assertEqual(primary['attribution_context']['evidence_parts'],
                         [dict(message_id='focus-user', origin_locator='line:3', content_indices=[1])])
        self.assertEqual(repeated['title'], 'Choose synthetic orchard watering sensors')
        self.assertEqual(repeated['attribution_context']['evidence_parts'],
                         [dict(message_id='repeated-user', origin_locator='line:6', content_indices=[1])])
        self.assertEqual(primary_review['expected_revision'], 0)
        self.assertEqual(repeated_review['expected_revision'], 1)
        self.assertEqual(repeated_review['previous_title'], primary['title'])
        self.assertIn('Synthetic runtime instructions', json.dumps(primary_review['review_evidence']))
        with closing(sqlite3.connect(db)) as connection:
            after = {table: connection.execute('SELECT * FROM ' + table).fetchall() for table in baseline}
        self.assertEqual(after, baseline)
        self.assertNotEqual(db.read_bytes(), baseline_db)
        inventory = self.cli('recap.py', '--db', db, 'list')
        self.assertEqual(inventory['conversations'][0]['display_title'], primary['title'])
        self.assertEqual(inventory['conversations'][0]['revision'], 1)

    def test_cli_saved_proposal_requires_separate_preview_and_apply(self):
        self.write()
        before = self.db.read_bytes()
        raw = self.path.read_bytes()
        saved = self.directory / 'proposal.json'
        reviewed = self.directory / 'preview.json'
        self.cli('recap.py', '--db', self.db, 'suggest-attributed-title', self.path,
                 '--source', 'local', '--conversation', 'synthetic', '--message', 'later', '--output', saved)
        self.cli('title_proposal.py', '--db', self.db, 'preview', saved, '--output', reviewed)
        self.assertEqual(self.db.read_bytes(), before)
        result = self.cli('title_proposal.py', '--db', self.db, 'apply', reviewed)
        self.assertEqual(result['display_title'], '합성 달력 만들기')
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertIn('Synthetic harness instructions', snapshot(self.db, 'local', 'synthetic')[0][1]['text'])


if __name__ == '__main__':
    unittest.main()
