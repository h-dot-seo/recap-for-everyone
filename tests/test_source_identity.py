"""Synthetic source identity validation before archive and title evidence work."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from recaplib.branch_title import suggest_branch
from recaplib.export_inventory import list_export
from recaplib.import_check import check_import
from recaplib.session_workflow import import_export, inspect_export, normalize, titles
from recaplib.title_plan import make_plan, check_plan
from recaplib.web_branch import branch_view


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.jsonl'
        self.db = Path(self.tmp.name) / 'archive.sqlite'

    @staticmethod
    def web(aliases=None, text='Synthetic orchard request'):
        return dict(aliases if aliases is not None else {'id': 'synthetic'},
                    title='New chat', current_node='u', mapping={'u': dict(parent=None,
                    message=dict(author=dict(role='user'), content=dict(parts=[text])))})

    @staticmethod
    def local(aliases=None, text='Synthetic orchard request'):
        return [dict(type='session_meta', payload=aliases if aliases is not None else {'id': 'synthetic'}),
                dict(type='response_item', payload=dict(type='message', role='user', id='u',
                     content=[dict(type='input_text', text=text)]))]

    def write(self, kind, aliases=None, text='Synthetic orchard request', extra=()):
        data = ([self.web(aliases, text), *extra] if kind == 'web'
                else [*self.local(aliases, text), *extra])
        self.path.write_text(json.dumps(data) if kind == 'web'
                             else '\n'.join(map(json.dumps, data)) + '\n', encoding='utf-8')

    @staticmethod
    def invalid_aliases(alias):
        yield {'id': 'SYNTHETIC_PRIVATE_FIRST', alias: 'SYNTHETIC_PRIVATE_SECOND'}
        for bad in (False, True, 0, 7, [], {}, {'SYNTHETIC_PRIVATE': 'value'}):
            yield {'id': bad, alias: 'synthetic'}
            yield {'id': 'synthetic', alias: bad}
        for first, second in (('e\u0301', '\u00e9'), (' synthetic', 'synthetic'),
                              ('synthetic ', 'synthetic')):
            yield {'id': first, alias: second}
        yield {}
        yield {'id': '', alias: None}

    def test_invalid_aliases_fail_before_new_or_existing_archive_changes(self):
        for kind in ('web', 'local', 'local-codex'):
            alias = 'conversation_id' if kind == 'web' else 'session_id'
            self.write(kind)
            import_export(self.db, kind, self.path, kind)
            before = self.db.read_bytes()
            missing = self.db.with_name('missing.sqlite')
            for aliases in self.invalid_aliases(alias):
                for text in ('Synthetic orchard request', ' '):
                    with self.subTest(kind=kind, aliases=aliases, text=text):
                        self.write(kind, aliases, text)
                        for db in (missing, self.db):
                            with self.assertRaises(ValueError) as caught:
                                import_export(db, kind, self.path, kind)
                            self.assertNotIn('SYNTHETIC_PRIVATE', str(caught.exception))
                        self.assertFalse(missing.exists())
                        self.assertEqual(self.db.read_bytes(), before)

    def test_invalid_unselected_record_is_not_hidden_by_selection(self):
        for kind in ('web', 'local', 'local-codex'):
            alias = 'conversation_id' if kind == 'web' else 'session_id'
            for aliases in ({'id': 'other', alias: 'different'}, {'id': 'other', alias: False}):
                extra = ([self.web(aliases, '')] if kind == 'web'
                         else [dict(type='session_meta', payload=aliases)])
                self.write(kind, extra=extra)
                for operation in (
                        lambda: normalize(self.path, kind, conversation='synthetic'),
                        lambda: import_export(self.db, 'demo', self.path, kind, conversation='synthetic'),
                        lambda: inspect_export(self.path, kind),
                        lambda: list_export(self.path, kind),
                        lambda: check_import(self.db, 'demo', self.path, kind)):
                    with self.subTest(kind=kind, aliases=aliases), self.assertRaises(ValueError):
                        operation()
                self.assertFalse(self.db.exists())

    def test_alias_fallback_and_exact_literal_identity_are_preserved(self):
        for kind in ('web', 'local', 'local-codex'):
            alias = 'conversation_id' if kind == 'web' else 'session_id'
            for identity in ('synthetic', ' padded 한글 ', 'e\u0301', '\u00e9', ' '):
                variants = [{'id': identity}, {alias: identity}, {'id': identity, alias: identity}]
                for absent in (None, ''):
                    variants += [{'id': absent, alias: identity}, {'id': identity, alias: absent}]
                for aliases in variants:
                    with self.subTest(kind=kind, aliases=aliases):
                        self.write(kind, aliases)
                        raw = self.path.read_bytes()
                        rows = normalize(self.path, kind, conversation=identity)
                        self.assertEqual(rows[0]['conversation_id'], identity)
                        self.assertEqual(rows[0]['message_id'], 'u')
                        self.assertEqual(rows[0]['text'], 'Synthetic orchard request')
                        self.assertEqual(rows[0]['origin_sha256'], hashlib.sha256(raw).hexdigest())
                        self.assertEqual(rows[0]['origin_locator'], 'mapping:u' if kind == 'web' else 'line:2')
                        inventory = list_export(self.path, kind)
                        self.assertEqual(inventory['conversations'][0]['conversation'], identity)
                        self.assertTrue(inventory['conversations'][0]['selection_supported'])
                        if kind == 'web':
                            self.assertEqual(branch_view(self.path, identity)['messages'], rows)
                        self.assertEqual(self.path.read_bytes(), raw)

    def test_valid_aliases_agree_through_import_plan_and_branch_evidence(self):
        for kind in ('web', 'local', 'local-codex'):
            alias = 'conversation_id' if kind == 'web' else 'session_id'
            for i, aliases in enumerate(({'id': '', alias: ' 한글 '}, {alias: ' 한글 '},
                                        {'id': ' 한글 ', alias: ' 한글 '})):
                source = f'{kind}-{i}'
                self.write(kind, aliases)
                raw = self.path.read_bytes()
                import_export(self.db, source, self.path, kind, conversation=' 한글 ')
                titles(self.db, source, ' 한글 ', 'Reviewed orchard title', 0)
                before = self.db.read_bytes()
                plan = make_plan(self.db, source, ' 한글 ', self.path, kind)
                self.assertEqual(plan['conversation'], ' 한글 ')
                self.assertEqual(plan['original_sha256'], hashlib.sha256(raw).hexdigest())
                self.assertTrue(check_plan(self.db, self.path, plan)['valid'])
                if kind == 'web':
                    proposal = suggest_branch(self.db, source, ' 한글 ', self.path)
                    self.assertEqual(proposal['conversation'], ' 한글 ')
                    self.assertEqual(proposal['evidence_message_ids'], ['u'])
                    self.assertEqual(proposal['branch_context']['original_sha256'], plan['original_sha256'])
                self.assertEqual(self.path.read_bytes(), raw)
                self.assertEqual(self.db.read_bytes(), before)

    def test_malformed_message_ids_reject_even_without_text(self):
        for kind in ('local', 'local-codex'):
            self.write(kind)
            import_export(self.db, kind, self.path, kind)
            before = self.db.read_bytes()
            missing = self.db.with_name('missing.sqlite')
            for bad in (False, True, 0, 17, [], {}, {'SYNTHETIC_PRIVATE': 'value'}):
                for text in ('Synthetic orchard request', '', ' '):
                    records = self.local(text=text)
                    records[1]['payload']['id'] = bad
                    self.path.write_text('\n'.join(map(json.dumps, records)))
                    with self.subTest(kind=kind, bad=bad, text=text):
                        for db in (missing, self.db):
                            with self.assertRaises(ValueError) as caught:
                                import_export(db, kind, self.path, kind)
                            self.assertNotIn('SYNTHETIC_PRIVATE', str(caught.exception))
                        self.assertFalse(missing.exists())
                        self.assertEqual(self.db.read_bytes(), before)

    def test_message_id_fallback_retains_physical_line_and_warning(self):
        for kind in ('local', 'local-codex'):
            for value in (None, '', 'missing'):
                records = self.local()
                if value == 'missing':
                    del records[1]['payload']['id']
                else:
                    records[1]['payload']['id'] = value
                self.path.write_bytes(b'\xef\xbb\xbf' + (json.dumps(records[0]) + '\r\n\r\n' +
                                      json.dumps(records[1]) + '\r\n').encode())
                rows, report = normalize(self.path, kind, include_report=True)
                self.assertEqual(rows[0]['message_id'], 'synthetic.jsonl:3')
                self.assertEqual(rows[0]['origin_locator'], 'line:3')
                self.assertEqual(report['messages_without_explicit_id'], 1)
                self.assertTrue(any('basename' in warning for warning in report['warnings']))
            for identity in (' padded 한글 ', 'e\u0301', '\u00e9', ' '):
                records = self.local(); records[1]['payload']['id'] = identity
                self.path.write_text('\n'.join(map(json.dumps, records)))
                rows, report = normalize(self.path, kind, include_report=True)
                self.assertEqual(rows[0]['message_id'], identity)
                self.assertEqual(report['messages_without_explicit_id'], 0)

    def test_unsupported_role_and_nonmessage_id_policy_is_unchanged(self):
        extra = [dict(type='response_item', payload=dict(type='message', role=role, id={}, content=None))
                 for role in ('system', 'developer', 'tool', 'future_role')]
        extra += [dict(type='response_item', payload=dict(type='function_call', id={}))]
        for kind in ('local', 'local-codex'):
            self.write(kind, extra=extra)
            rows = normalize(self.path, kind)
            self.assertEqual([r['message_id'] for r in rows], ['u'])

    def test_invalid_local_message_identity_has_physical_line_and_clean_cli_error(self):
        for kind in ('local', 'local-codex'):
            for role in ('user', 'assistant'):
                records = self.local(text='SYNTHETIC_PRIVATE_BODY')
                records[1]['payload'].update(role=role, id={'SYNTHETIC_PRIVATE_ID': 17})
                self.path.write_bytes(b'\xef\xbb\xbf' + (json.dumps(records[0]) + '\r\n\r\n' +
                                      json.dumps(records[1]) + '\r\n').encode())
                with self.assertRaisesRegex(ValueError, r':3$'):
                    normalize(self.path, kind)
                for command in ('inspect', 'import'):
                    args = [sys.executable, 'recap.py', '--db', str(self.db), command,
                            str(self.path), '--format', kind]
                    if command == 'import':
                        args += ['--source', 'demo']
                    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertNotIn('SYNTHETIC_PRIVATE', result.stdout + result.stderr)
                    self.assertRegex(result.stderr, r':3\s*$')
                    self.assertFalse(self.db.exists())

    def test_conflicting_web_aliases_cannot_generate_wrong_target_proposal_or_plan(self):
        self.write('web', {'id': 'SYNTHETIC_PRIVATE_FIRST'})
        import_export(self.db, 'demo', self.path, 'web')
        titles(self.db, 'demo', 'SYNTHETIC_PRIVATE_FIRST', 'Reviewed title', 0)
        before = self.db.read_bytes()
        self.write('web', {'id': 'SYNTHETIC_PRIVATE_FIRST', 'conversation_id': 'SYNTHETIC_PRIVATE_SECOND'})
        for operation in (lambda: suggest_branch(self.db, 'demo', 'SYNTHETIC_PRIVATE_FIRST', self.path),
                          lambda: make_plan(self.db, 'demo', 'SYNTHETIC_PRIVATE_FIRST', self.path, 'web'),
                          lambda: branch_view(self.path, 'SYNTHETIC_PRIVATE_FIRST')):
            with self.assertRaises(ValueError) as caught:
                operation()
            self.assertNotIn('SYNTHETIC_PRIVATE', str(caught.exception))
        self.assertEqual(self.db.read_bytes(), before)

    def test_cli_errors_are_clean_and_do_not_echo_identifiers_or_body(self):
        for kind in ('web', 'local', 'local-codex'):
            alias = 'conversation_id' if kind == 'web' else 'session_id'
            self.write(kind, {'id': 'SYNTHETIC_PRIVATE_FIRST', alias: 'SYNTHETIC_PRIVATE_SECOND'},
                       text='SYNTHETIC_PRIVATE_BODY')
            commands = [('recap.py', 'inspect', self.path, '--format', kind),
                        ('recap.py', '--db', self.db, 'import', self.path, '--format', kind, '--source', 'demo'),
                        ('export_inventory.py', self.path, '--format', kind),
                        ('title_plan.py', '--db', self.db, 'export', self.path, '--format', kind,
                         '--source', 'demo', '--conversation', 'SYNTHETIC_PRIVATE_FIRST')]
            if kind == 'web':
                commands.append(('web_branch.py', self.path, '--conversation', 'SYNTHETIC_PRIVATE_FIRST'))
            for command in commands:
                with self.subTest(kind=kind, command=command[0:2]):
                    result = subprocess.run([sys.executable, *map(str, command)], capture_output=True,
                                            text=True, timeout=20)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertNotIn('SYNTHETIC_PRIVATE', result.stdout + result.stderr)
                    self.assertFalse(self.db.exists())
