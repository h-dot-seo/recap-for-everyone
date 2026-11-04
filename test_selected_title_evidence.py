"""Synthetic exact-user-message title selection and reviewed archive workflows."""
import copy
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from conversation_search import find
from recap import ingest
from session_workflow import import_export, titles
from title_batch import review_queue, select_proposal
from title_excerpt import excerpt
from title_proposal import apply_preview, content_fingerprint, preview, snapshot
from title_suggestion import suggest


class SelectedTitleEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.path = self.root / 'synthetic.jsonl'
        self.records = [dict(conversation_id='chat', message_id=identity, role=role,
                             timestamp='synthetic', title='New chat', text=text)
                        for identity, role, text in (
                            ('opening', 'user', 'Can you help me?'),
                            ('assistant', 'assistant', 'Synthetic assistant response'),
                            ('chosen', 'user', 'Compare synthetic orchard irrigation designs'),
                            ('greeting', 'user', 'Hello!'),
                            ('empty', 'user', '!? 👩\u200d🔬'),
                            ('prefix', 'user', '!' * 80 + 'Later letters'),
                            ('tool', 'tool', 'Synthetic tool result'),
                            ('system', 'system', 'Synthetic system instructions'))]
        self.load()

    def load(self):
        self.path.write_text(''.join(json.dumps(row) + '\n' for row in self.records), encoding='utf-8')
        ingest(self.db, 'demo', self.path)

    def call(self, script, *args, ok=True):
        env = dict(os.environ, PYTHONIOENCODING='ascii', PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, script, '--db', str(self.db), *map(str, args)],
                                capture_output=True, timeout=20, env=env)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr.decode('ascii', errors='replace'))
        self.assertNotIn(b'Traceback', result.stderr)
        return json.loads(result.stdout) if ok else result

    def test_default_shape_and_explicit_choice_are_distinct_and_readonly(self):
        before = self.db.read_bytes(), self.path.read_bytes()
        rows, digest = snapshot(self.db, 'demo', 'chat')
        expected = dict(source='demo', conversation='chat', content_sha256=digest,
                        provider='local-extractive', **excerpt(rows))
        self.assertEqual(suggest(self.db, 'demo', 'chat'), expected)
        self.assertEqual(suggest(self.db, 'demo', 'chat', None), expected)
        result = suggest(self.db, 'demo', 'chat', 'chosen')
        self.assertEqual(result['title'], 'Compare synthetic orchard irrigation designs')
        self.assertEqual(result['evidence_message_ids'], ['chosen'])
        self.assertEqual(result['content_sha256'], digest)
        self.assertEqual(result['evidence_selection'], dict(mode='explicit_user_message', message_id='chosen',
            scope='raw archived user message; not branch, replay or source-attributed selection'))
        self.assertEqual(result['provider'], 'local-extractive')
        self.assertEqual((self.db.read_bytes(), self.path.read_bytes()), before)

    def test_invalid_selector_shapes_reject_before_snapshot(self):
        for value in ('', False, 0, 1, [], {}, b'chosen'):
            with self.subTest(value=value), patch('title_suggestion.snapshot') as read:
                with self.assertRaises(ValueError):
                    suggest(self.db, 'demo', 'chat', value)
                read.assert_not_called()

    def test_missing_nonuser_and_unusable_never_fall_back(self):
        before = self.db.read_bytes()
        for identity in ('missing', 'assistant', 'tool', 'system', 'empty', 'prefix', ' chosen '):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                suggest(self.db, 'demo', 'chat', identity)
        self.assertEqual(self.db.read_bytes(), before)

    def test_single_snapshot_and_full_fingerprint_even_when_selecting_one(self):
        rows, digest = snapshot(self.db, 'demo', 'chat')
        original = copy.deepcopy(rows)
        with patch('title_suggestion.snapshot', return_value=(rows, digest)) as read:
            result = suggest(self.db, 'demo', 'chat', 'chosen')
        read.assert_called_once_with(self.db, 'demo', 'chat')
        self.assertEqual(rows, original)
        self.assertEqual(result['content_sha256'], content_fingerprint(rows))
        self.assertNotEqual(result['content_sha256'], content_fingerprint([rows[2]]))
        with patch('title_suggestion.snapshot', return_value=(rows + [rows[2]], digest)):
            with self.assertRaises(ValueError):
                suggest(self.db, 'demo', 'chat', 'chosen')

    def test_exact_identity_does_not_normalize_or_trim(self):
        nfc = '선택'
        nfd = unicodedata.normalize('NFD', nfc)
        self.records.extend(dict(conversation_id='chat', message_id=identity, role='user', timestamp='synthetic',
                                 title='New chat', text=text) for identity, text in
                            ((nfc, 'Synthetic NFC choice'), (nfd, 'Synthetic NFD choice'), (' padded ', 'Synthetic padded choice')))
        self.load()
        for identity, title in ((nfc, 'Synthetic NFC choice'), (nfd, 'Synthetic NFD choice'), (' padded ', 'Synthetic padded choice')):
            result = suggest(self.db, 'demo', 'chat', identity)
            self.assertEqual(result['title'], title)
            self.assertEqual(result['evidence_message_ids'], [identity])
        with self.assertRaises(ValueError):
            suggest(self.db, 'demo', 'chat', 'padded')

    def test_greeting_choice_is_explicit_but_keeps_existing_advisory(self):
        result = suggest(self.db, 'demo', 'chat', 'greeting')
        self.assertEqual(result['title'], 'Hello!')
        self.assertEqual(result['evidence_message_ids'], ['greeting'])
        self.assertEqual(result['selection_method'], 'first_user_greeting_fallback')
        self.assertEqual(result['evidence_selection']['mode'], 'explicit_user_message')
        self.assertIn('REPORTED_GREETING_FALLBACK', preview(self.db, result)['title_advisory']['quality_flags'])

    def test_cleaning_and_eighty_code_point_bound_are_unchanged(self):
        text = '\x00합성\n\t연구 👩\u200d🔬 می\u200cروم\u202e ' + '검토 ' * 80
        self.records[2]['text'] = text
        self.db = self.root / 'cleaning.sqlite'
        self.load()
        result = suggest(self.db, 'demo', 'chat', 'chosen')
        for key, value in excerpt([dict(role='user', message_id='chosen', text=text)]).items():
            self.assertEqual(result[key], value)
        self.assertLessEqual(len(result['title']), 80)
        self.assertTrue(result['truncated'])
        self.assertEqual(snapshot(self.db, 'demo', 'chat')[0][2]['text'], text)

    def test_other_conversation_or_source_identity_is_not_selectable(self):
        other = dict(self.records[2], conversation_id='other', message_id='elsewhere')
        self.records.append(other)
        self.load()
        for conversation, identity in (('chat', 'elsewhere'), ('other', 'opening')):
            with self.assertRaises(ValueError):
                suggest(self.db, 'demo', conversation, identity)
        with self.assertRaises(ValueError):
            suggest(self.db, 'other-source', 'chat', 'chosen')

    def test_unselected_content_changes_stale_both_proposal_and_preview(self):
        proposal = suggest(self.db, 'demo', 'chat', 'chosen')
        reviewed = preview(self.db, proposal)
        self.records.append(dict(self.records[0], message_id='later', text='Synthetic later constraint'))
        self.load()
        before = self.db.read_bytes()
        for action in (lambda: preview(self.db, proposal), lambda: apply_preview(self.db, reviewed)):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(titles(self.db, 'demo', 'chat')['revision'], 0)

    def test_supplied_queue_preview_replacement_apply_search_and_source_preservation(self):
        original = self.path.read_bytes()
        before = self.db.read_bytes()
        proposal = suggest(self.db, 'demo', 'chat', 'chosen')
        queue = review_queue(self.db, 'demo', supplied_proposals=[proposal], supplied_only=True)
        self.assertEqual(select_proposal(queue, 'chat'), proposal)
        reviewed = preview(self.db, select_proposal(queue, 'chat'), with_evidence=True)
        self.assertEqual(reviewed['review_evidence']['messages'][0]['message_id'], 'chosen')
        self.assertEqual(self.db.read_bytes(), before)
        replaced = preview(self.db, proposal, 'Synthetic irrigation comparison', with_evidence=True)
        self.assertEqual(replaced['proposal']['provider'], 'operator')
        self.assertEqual(replaced['proposal']['evidence_message_ids'], ['chosen'])
        self.assertNotIn('evidence_selection', replaced['proposal'])
        apply_preview(self.db, replaced)
        self.assertEqual(find(self.db, 'irrigation comparison', 'demo')['matches'][0]['display_title'],
                         'Synthetic irrigation comparison')
        self.assertEqual(self.path.read_bytes(), original)
        with self.assertRaises(ValueError):
            apply_preview(self.db, replaced)

    def test_ascii_cli_parity_and_clean_failures_without_writes(self):
        self.records[2]['text'] = '합성 과수원 관개 비교 👩\u200d🔬'
        self.db = self.root / 'unicode.sqlite'
        self.load()
        before = self.db.read_bytes()
        identity = ['--source', 'demo', '--conversation', 'chat']
        expected = suggest(self.db, 'demo', 'chat', 'chosen')
        self.assertEqual(self.call('recap.py', 'suggest-title', *identity, '--message', 'chosen'), expected)
        self.assertEqual(self.call('title_suggestion.py', *identity, '--message', 'chosen'), expected)
        for script, command in (('recap.py', ['suggest-title']), ('title_suggestion.py', [])):
            for selected in ('missing', 'assistant', 'empty', ''):
                self.call(script, *command, *identity, '--message', selected, ok=False)
        self.assertEqual(self.db.read_bytes(), before)

    def test_web_and_local_imported_ids_select_later_evidence(self):
        for kind in ('web', 'local', 'local-codex'):
            with self.subTest(kind=kind):
                path = self.root / (kind + '.json')
                texts = [('opening', 'Can you help me?'), ('target', 'Synthetic orchard irrigation schedule')]
                if kind == 'web':
                    mapping = {identity: dict(parent=None if index == 0 else 'opening', message=dict(
                        author=dict(role='user'), content=dict(parts=[text])))
                        for index, (identity, text) in enumerate(texts)}
                    path.write_text(json.dumps([dict(id='imported', title='New chat', current_node='target', mapping=mapping)]))
                else:
                    records = [dict(type='session_meta', payload=dict(id='imported'))]
                    records.extend(dict(type='response_item', payload=dict(type='message', role='user', id=identity,
                        content=[dict(type='input_text', text=text)])) for identity, text in texts)
                    path.write_text(''.join(json.dumps(record) + '\n' for record in records))
                original = path.read_bytes()
                import_export(self.db, kind, path, kind)
                before = self.db.read_bytes()
                proposal = suggest(self.db, kind, 'imported', 'target')
                self.assertEqual(proposal['title'], texts[1][1])
                evidence = preview(self.db, proposal, with_evidence=True)['review_evidence']['messages'][0]
                self.assertEqual(evidence['message_id'], 'target')
                self.assertGreater(evidence['export_provenance_count'], 0)
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(path.read_bytes(), original)


    def test_published_focus_example_commands_require_separate_apply(self):
        doc = Path('docs/TITLE_REVIEW_HINTS.md').read_text(encoding='utf-8')
        section = doc.split('## Choose a more informative user message', 1)[1].split('\n## ', 1)[0]
        commands = [line for line in section.splitlines() if line.startswith(('mkdir ', 'python recap.py '))]
        self.assertEqual(len(commands), 7)
        scratch = self.root / 'focus example with spaces'
        source = Path('examples/title-focus-web.json')
        original = source.read_bytes()
        db = scratch / 'archive.sqlite'
        baseline = None
        initial_snapshot = None
        results = []
        apply_args = None
        for line in commands:
            # Parse the published POSIX command before substituting platform paths.
            args = [arg.replace('../recap-title-focus-demo', str(scratch)) for arg in shlex.split(line)]
            if args[0] == 'mkdir':
                Path(args[1]).mkdir()
                continue
            self.assertEqual(args.pop(0), 'python')
            self.assertNotIn('>', args, 'the exact-message guide uses native saving')
            target = Path(args[args.index('--output') + 1]) if '--output' in args else None
            is_apply = 'apply-title' in args
            if is_apply:
                self.assertEqual(db.read_bytes(), baseline)
                self.assertEqual(titles(db, 'demo', 'synthetic-title-focus')['revision'], 0)
                self.assertEqual(source.read_bytes(), original)
                reviewed = json.loads((scratch / 'reviewed.json').read_bytes())
                self.assertEqual(reviewed['proposal']['title'], 'Compare synthetic orchard irrigation schedules')
                self.assertEqual(reviewed['proposal']['evidence_message_ids'], ['u2'])
                evidence = reviewed['review_evidence']['messages'][0]
                self.assertEqual(evidence['message_id'], 'u2')
                self.assertGreater(evidence['export_provenance_count'], 0)
                apply_args = args
            result = subprocess.run([sys.executable, *args], capture_output=True, timeout=20,
                                    env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            results.append(value)
            if target:
                raw = target.read_bytes()
                self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
                self.assertEqual(value['status'], 'SAVED')
                self.assertEqual(value['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(value['bytes'], len(raw))
                self.assertEqual(value['document_kind'], 'proposal' if 'suggest-title' in args else 'preview')
            if 'import' in args:
                baseline = db.read_bytes()
                initial_snapshot = snapshot(db, 'demo', 'synthetic-title-focus')
                self.assertEqual(suggest(db, 'demo', 'synthetic-title-focus')['title'], 'Can you help with my project?')
            elif not is_apply:
                self.assertEqual(db.read_bytes(), baseline)
        self.assertIsNotNone(apply_args)
        self.assertEqual(len(results), 6)
        self.assertEqual(snapshot(db, 'demo', 'synthetic-title-focus'), initial_snapshot)
        self.assertEqual(source.read_bytes(), original)
        match = find(db, 'Compare synthetic orchard irrigation schedules', 'demo')['matches'][0]
        self.assertEqual(match['display_title'], 'Compare synthetic orchard irrigation schedules')
        self.assertTrue(match['matched_title'])
        after = db.read_bytes()
        repeated = subprocess.run([sys.executable, *apply_args], capture_output=True, timeout=20)
        self.assertEqual(repeated.returncode, 1)
        self.assertNotIn(b'Traceback', repeated.stderr)
        self.assertEqual(db.read_bytes(), after)


    def test_local_fallback_id_keeps_original_basename_and_physical_line(self):
        path = self.root / 'synthetic fallback.jsonl'
        records = [dict(type='session_meta', payload=dict(id='fallback')),
                   dict(type='response_item', payload=dict(type='message', role='user',
                        content=[dict(type='input_text', text='Synthetic fallback irrigation request')]))]
        path.write_text(json.dumps(records[0]) + '\n\n' + json.dumps(records[1]) + '\n', encoding='utf-8')
        original = path.read_bytes()
        for kind in ('local', 'local-codex'):
            with self.subTest(kind=kind):
                import_export(self.db, kind, path, kind)
                before = self.db.read_bytes()
                identity = 'synthetic fallback.jsonl:3'
                proposal = suggest(self.db, kind, 'fallback', identity)
                self.assertEqual(proposal['evidence_message_ids'], [identity])
                self.assertEqual(proposal['title'], 'Synthetic fallback irrigation request')
                self.assertEqual(proposal['evidence_selection']['message_id'], identity)
                for invalid in ('session.jsonl:3', 'synthetic fallback.jsonl:2', str(path) + ':3'):
                    with self.assertRaises(ValueError):
                        suggest(self.db, kind, 'fallback', invalid)
                evidence = preview(self.db, proposal, with_evidence=True)['review_evidence']['messages'][0]
                self.assertTrue(any(row['locator'] == 'line:3' for row in evidence['export_provenance']))
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(path.read_bytes(), original)

    def test_explicit_raw_selection_does_not_claim_branch_or_replay_filtering(self):
        local = Path('examples/rollback-session.jsonl')
        original = local.read_bytes()
        import_export(self.db, 'rollback', local, 'local-codex')
        proposal = suggest(self.db, 'rollback', 'synthetic-rollout', 'rollback-session.jsonl:4')
        self.assertEqual(proposal['title'], 'Synthetic question discarded')
        self.assertNotIn('projection_context', proposal)
        self.assertNotIn('attribution_context', proposal)
        self.assertIn('not branch, replay or source-attributed', proposal['evidence_selection']['scope'])
        preview(self.db, proposal)
        self.assertEqual(local.read_bytes(), original)
        path = self.root / 'synthetic-fork.json'
        mapping = {identity: dict(parent=parent, message=dict(author=dict(role='user'), content=dict(parts=[text])))
                   for identity, parent, text in [('root', None, 'Can you help me?'),
                       ('abandoned', 'root', 'Synthetic abandoned orchard plan'),
                       ('current', 'root', 'Synthetic current irrigation plan')]}
        path.write_text(json.dumps([dict(id='fork', title='New chat', current_node='current', mapping=mapping)]))
        original = path.read_bytes()
        import_export(self.db, 'fork', path, 'web')
        before = self.db.read_bytes()
        proposal = suggest(self.db, 'fork', 'fork', 'abandoned')
        self.assertEqual(proposal['title'], 'Synthetic abandoned orchard plan')
        self.assertNotIn('branch_context', proposal)
        self.assertEqual(proposal['evidence_selection']['mode'], 'explicit_user_message')
        self.assertIn('not branch, replay or source-attributed', proposal['evidence_selection']['scope'])
        preview(self.db, proposal)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
