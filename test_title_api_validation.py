"""Synthetic direct-title identity/revision boundaries and CLI regressions.

Fixtures contain invented conversations only. No real archives, credentials,
network calls, models, or remote title changes are used by these tests.
"""
from contextlib import closing
from enum import IntEnum
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from session_workflow import import_export, titles
from title_proposal import apply_preview, preview
from title_suggestion import suggest


ROOT = Path(__file__).resolve().parent
PRIVATE_MESSAGE = 'SYNTHETIC_PRIVATE_MESSAGE_47 orchard experiment details'
PRIVATE_TITLE = 'SYNTHETIC_PRIVATE_ORIGINAL_TITLE_47'
PRIVATE_ID = 'SYNTHETIC_PRIVATE_UNKNOWN_ID_47'
SOURCE_ERROR = 'source must be nonempty text'
CONVERSATION_ERROR = 'conversation must be nonempty text'
REVISION_ERROR = 'expected revision must be a nonnegative integer or None'
SURROGATES = ('\ud800', '\udfff', PRIVATE_ID + '\udc80', '\ud83c\udf31')
BAD_SOURCES = (None, '', ' \t\n', False, True, 0, 1, 1.0, [], {}, b'1')
BAD_CONVERSATIONS = (None, '', False, True, 0, 1, 1.0, [], {}, b'1')
BAD_REVISIONS = (False, True, -1, -100, 0.0, 1.0, float('nan'),
                 float('inf'), '', '0', '1', [], {}, b'1', '\ud800')


class RevisionSubclass(int):
    pass


class RevisionEnum(IntEnum):
    ZERO = 0
    ONE = 1


class UnusablePath:
    def __fspath__(self):
        raise AssertionError('database path was accessed before validation')


class TitleApiValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.db = self.root / 'synthetic.sqlite'
        self.missing = self.root / 'missing.sqlite'
        self.export = self.root / 'synthetic-export.json'
        self.import_records('1', ('1', '01', '1.0', 'True'))

    def import_records(self, source, conversations):
        records = [dict(id=conversation, title=PRIVATE_TITLE, mapping={
            'u': dict(parent=None, message=dict(author=dict(role='user'),
                      create_time=0, content=dict(parts=[PRIVATE_MESSAGE]))),
            'a': dict(parent='u', message=dict(author=dict(role='assistant'),
                      create_time=1, content=dict(parts=['Synthetic assistant reply']))),
        }) for conversation in conversations]
        self.export.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
        return import_export(self.db, source, self.export, 'web')

    def core_state(self):
        with closing(sqlite3.connect(self.db)) as connection:
            return {name: connection.execute('SELECT * FROM ' + name + ' ORDER BY rowid').fetchall()
                    for name in ('artifacts', 'messages', 'export_provenance', 'export_occurrences')}

    def history(self):
        with closing(sqlite3.connect(self.db)) as connection:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='title_history'").fetchone():
                return None
            return connection.execute('SELECT * FROM title_history ORDER BY id').fetchall()

    def archive_state(self):
        with closing(sqlite3.connect(self.db)) as connection:
            dump = tuple(connection.iterdump())
        return self.db.read_bytes(), dump

    def rejected_cases(self):
        for source in BAD_SOURCES:
            yield source, '1', None, SOURCE_ERROR
        for source in SURROGATES:
            yield source, '1', None, 'source must contain valid Unicode text'
        for conversation in BAD_CONVERSATIONS:
            yield '1', conversation, None, CONVERSATION_ERROR
        for conversation in SURROGATES:
            yield '1', conversation, None, 'conversation must contain valid Unicode text'
        for revision in BAD_REVISIONS + (RevisionSubclass(0), RevisionEnum.ONE):
            yield '1', '1', revision, REVISION_ERROR

    def assert_pre_io_rejection(self, field, values, error):
        before = self.archive_state()
        source_before = self.export.read_bytes()
        with patch('session_workflow.readonly', side_effect=AssertionError('read database opened')) as ro, \
             patch('session_workflow.sqlite3.connect', side_effect=AssertionError('database opened')) as connect, \
             patch('session_workflow.Path', side_effect=AssertionError('database path examined')) as path:
            for value in values:
                for db in (self.db, self.missing, UnusablePath()):
                    for title in (None, 'Synthetic replacement'):
                        kwargs = dict(source='1', conversation='1', expected_revision=None)
                        kwargs[field] = value
                        with self.subTest(field=field, value=repr(value), db=type(db).__name__, write=title is not None):
                            with self.assertRaises(ValueError) as caught:
                                titles(db, title=title, **kwargs)
                            self.assertEqual(str(caught.exception), error)
            ro.assert_not_called()
            connect.assert_not_called()
            path.assert_not_called()
        self.assertEqual(self.archive_state(), before)
        self.assertEqual(self.export.read_bytes(), source_before)
        self.assertFalse(self.missing.exists())

    def assert_rejections_preserve_archive(self):
        before = self.archive_state()
        core = self.core_state()
        history = self.history()
        export = self.export.read_bytes()
        for source, conversation, revision, message in self.rejected_cases():
            for title in (None, 'Synthetic forbidden replacement'):
                with self.subTest(source=repr(source), conversation=repr(conversation),
                                  revision=repr(revision), write=title is not None):
                    with self.assertRaises(ValueError) as caught:
                        titles(self.db, source, conversation, title, revision)
                    self.assertEqual(str(caught.exception), message)
        self.assertEqual(self.archive_state(), before)
        self.assertEqual(self.core_state(), core)
        self.assertEqual(self.history(), history)
        self.assertEqual(self.export.read_bytes(), export)

    def cli(self, script, *args, db=None, synthetic_argv=False):
        argv = [script, '--db', str(self.db if db is None else db), 'title', *args]
        if synthetic_argv:
            # Code-point arrays preserve even adjacent surrogate pairs on Windows
            # without asking the OS or a JSON string decoder to rewrite them.
            code = ('import json,runpy,sys; '
                    'sys.argv=["".join(map(chr,value)) for value in json.loads(sys.argv[1])]; '
                    'runpy.run_path(sys.argv[0],run_name="__main__")')
            command = [sys.executable, '-c', code, json.dumps([[ord(char) for char in value] for value in argv])]
        else:
            command = [sys.executable, *argv]
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                              encoding='ascii', timeout=20,
                              env=dict(os.environ, PYTHONIOENCODING='ascii'))

    def assert_clean_failure(self, result, message=None):
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn(PRIVATE_MESSAGE, result.stderr)
        self.assertNotIn(PRIVATE_TITLE, result.stderr)
        self.assertNotIn(PRIVATE_ID, result.stderr)
        self.assertNotIn(str(self.root), result.stderr)
        if message is not None:
            self.assertEqual(result.stderr, message + '\n')

    def test_source_types_rejected_before_read_write_or_path_access(self):
        self.assert_pre_io_rejection('source', BAD_SOURCES, SOURCE_ERROR)

    def test_source_surrogates_rejected_before_read_write_or_path_access(self):
        self.assert_pre_io_rejection('source', SURROGATES, 'source must contain valid Unicode text')

    def test_conversation_types_rejected_before_read_write_or_path_access(self):
        self.assert_pre_io_rejection('conversation', BAD_CONVERSATIONS, CONVERSATION_ERROR)

    def test_conversation_surrogates_rejected_before_read_write_or_path_access(self):
        self.assert_pre_io_rejection('conversation', SURROGATES, 'conversation must contain valid Unicode text')

    def test_bad_revisions_rejected_before_read_write_or_path_access(self):
        self.assert_pre_io_rejection('expected_revision', BAD_REVISIONS, REVISION_ERROR)

    def test_integer_subclasses_are_not_exact_builtin_revisions(self):
        self.assert_pre_io_rejection('expected_revision',
                                    (RevisionSubclass(0), RevisionSubclass(1), RevisionEnum.ZERO, RevisionEnum.ONE),
                                    REVISION_ERROR)

    def test_revision_validation_precedes_invalid_title_and_content_hash(self):
        with patch('session_workflow.readonly', side_effect=AssertionError('read database opened')), \
             patch('session_workflow.sqlite3.connect', side_effect=AssertionError('database opened')):
            for title in (None, '', [], '\ud800'):
                with self.subTest(title=repr(title)), self.assertRaises(ValueError) as caught:
                    titles(UnusablePath(), '1', '1', title, 1.0, 'bad fingerprint')
                self.assertEqual(str(caught.exception), REVISION_ERROR)

    def test_rejected_calls_preserve_archive_without_creating_history(self):
        self.assertIsNone(self.history())
        self.assert_rejections_preserve_archive()
        self.assertIsNone(self.history())

    def test_rejected_calls_preserve_existing_title_history_and_provenance(self):
        titles(self.db, '1', '1', 'Existing synthetic title', 0)
        self.assert_rejections_preserve_archive()

    def test_original_boolean_source_integer_conversation_bug_is_rejected(self):
        before = self.archive_state()
        with self.assertRaises(ValueError) as caught:
            titles(self.db, True, 1, 'Changed', False)
        self.assertEqual(str(caught.exception), SOURCE_ERROR)
        self.assertEqual(self.archive_state(), before)
        self.assertEqual(titles(self.db, '1', '1')['display_title'], PRIVATE_TITLE)
        self.assertIsNone(self.history())

    def test_float_and_boolean_revisions_cannot_match_integer_zero_or_one(self):
        for invalid in (False, 0.0):
            with self.subTest(revision=invalid), self.assertRaisesRegex(ValueError, '^' + REVISION_ERROR + '$'):
                titles(self.db, '1', '1', 'Bad zero revision', invalid)
        first = titles(self.db, '1', '1', 'Valid first title', 0)
        self.assertEqual(first['revision'], 1)
        before = self.archive_state()
        for invalid in (True, 1.0):
            with self.subTest(revision=invalid), self.assertRaisesRegex(ValueError, '^' + REVISION_ERROR + '$'):
                titles(self.db, '1', '1', 'Bad one revision', invalid)
        self.assertEqual(self.archive_state(), before)
        self.assertEqual(titles(self.db, '1', '1')['display_title'], 'Valid first title')

    def test_numeric_text_source_and_conversation_keys_are_distinct(self):
        for source in ('01', '1.0', 'True'):
            self.import_records(source, ('1', '01', '1.0', 'True'))
        core = self.core_state()
        expected = {}
        for source in ('1', '01', '1.0', 'True'):
            for conversation in ('1', '01', '1.0', 'True'):
                title = 'Synthetic label %s / %s' % (source, conversation)
                expected[source, conversation] = title
                result = titles(self.db, source, conversation, title, 0)
                self.assertEqual(result['display_title'], title)
        for identity, title in expected.items():
            with self.subTest(identity=identity):
                self.assertEqual(titles(self.db, *identity)['display_title'], title)
        self.assertEqual(self.core_state(), core)
        self.assertEqual({(row[1], row[2]) for row in self.history()}, set(expected))

    def test_unicode_source_labels_keep_exact_normalization_and_padding(self):
        sources = ('é', 'e\u0301', 'source', '  source  ', '한글 🌱', 'nul\x00source')
        for index, source in enumerate(sources):
            self.import_records(source, ('1',))
            result = titles(self.db, source, '1', 'Synthetic label %d' % index, 0)
            self.assertEqual(result['revision'], index + 1)
        for index, source in enumerate(sources):
            self.assertEqual(titles(self.db, source, '1')['display_title'], 'Synthetic label %d' % index)
        self.assertEqual([row[1] for row in self.history()], list(sources))

    def test_conversation_unicode_whitespace_and_nul_identities_remain_literal(self):
        conversations = ('é', 'e\u0301', 'conversation', '  conversation  ',
                         ' \t\n', '한글 🌱', 'nul\x00one', 'nul\x00two')
        self.import_records('exact', conversations)
        core = self.core_state()
        for index, conversation in enumerate(conversations):
            changed = titles(self.db, 'exact', conversation, 'Exact synthetic title %d' % index, 0)
            self.assertEqual(changed['display_title'], 'Exact synthetic title %d' % index)
        for index, conversation in enumerate(conversations):
            self.assertEqual(titles(self.db, 'exact', conversation)['display_title'], 'Exact synthetic title %d' % index)
        self.assertEqual([row[2] for row in self.history()], list(conversations))
        self.assertEqual(self.core_state(), core)

    def test_default_and_explicit_none_keep_lower_level_legacy_writes(self):
        before = self.archive_state()
        self.assertEqual(titles(self.db, '1', '1'), titles(self.db, '1', '1', expected_revision=None))
        self.assertEqual(self.archive_state(), before)
        first = titles(self.db, '1', '1', 'Legacy omitted guard')
        second = titles(self.db, '1', '1', 'Legacy explicit null guard', None)
        self.assertGreater(second['revision'], first['revision'])
        self.assertEqual(second['prior_titles'], ['Legacy omitted guard'])
        self.assertEqual(titles(self.db, '1', '1')['display_title'], 'Legacy explicit null guard')

    def test_valid_revision_on_read_is_informational_not_compare_and_swap(self):
        current = titles(self.db, '1', '1', 'Current synthetic title', 0)
        before = self.archive_state()
        for revision in (0, current['revision'], current['revision'] + 1, 10 ** 100):
            with self.subTest(revision=revision):
                self.assertEqual(titles(self.db, '1', '1', expected_revision=revision),
                                 titles(self.db, '1', '1'))
        self.assertEqual(self.archive_state(), before)

    def test_exact_revisions_apply_and_stale_revisions_never_write(self):
        core = self.core_state()
        first = titles(self.db, '1', '1', 'First exact revision', 0)
        second = titles(self.db, '1', '1', 'Second exact revision', first['revision'])
        self.assertGreater(second['revision'], first['revision'])
        before = self.archive_state()
        for revision in (0, first['revision'], second['revision'] + 1, 10 ** 100):
            with self.subTest(revision=revision), self.assertRaisesRegex(ValueError, 'stale title preview'):
                titles(self.db, '1', '1', 'Stale forbidden title', revision)
        self.assertEqual(self.archive_state(), before)
        self.assertEqual(self.core_state(), core)
        self.assertEqual(second['original_title'], PRIVATE_TITLE)
        self.assertEqual(second['prior_titles'], ['First exact revision'])

    def test_revision_is_history_identity_not_per_conversation_counter(self):
        first = titles(self.db, '1', '1', 'First conversation', 0)
        other = titles(self.db, '1', '01', 'Other conversation', 0)
        self.assertGreater(other['revision'], first['revision'])
        result = titles(self.db, '1', '1', 'Checked original conversation', first['revision'])
        self.assertGreater(result['revision'], other['revision'])
        self.assertEqual(titles(self.db, '1', '01')['display_title'], 'Other conversation')

    def test_ordinary_suggest_preview_apply_preserves_archive_and_provenance(self):
        core = self.core_state()
        before = self.archive_state()
        proposal = suggest(self.db, '1', '1')
        reviewed = preview(self.db, proposal, replacement_title='Reviewed orchard plan 🌱', with_evidence=True)
        self.assertIs(type(reviewed['expected_revision']), int)
        self.assertEqual(reviewed['expected_revision'], 0)
        self.assertEqual(self.archive_state(), before)
        result = apply_preview(self.db, reviewed)
        self.assertEqual(result['display_title'], 'Reviewed orchard plan 🌱')
        self.assertIs(type(result['revision']), int)
        self.assertGreater(result['revision'], 0)
        self.assertEqual(self.core_state(), core)
        before_stale = self.archive_state()
        with self.assertRaisesRegex(ValueError, 'stale title preview'):
            apply_preview(self.db, reviewed)
        self.assertEqual(self.archive_state(), before_stale)

    def test_both_title_clis_preview_and_apply_successfully(self):
        for script, conversation in (('recap.py', '1'), ('session_workflow.py', '01')):
            with self.subTest(script=script):
                identity = ('--source', '1', '--conversation', conversation)
                before = self.archive_state()
                result = self.cli(script, *identity)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')
                original = json.loads(result.stdout)
                self.assertEqual(original['revision'], 0)
                self.assertEqual(self.archive_state(), before)
                core = self.core_state()
                result = self.cli(script, *identity, '--set', '검토한 과수원 계획 🌱', '--expected-revision', '0')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')
                changed = json.loads(result.stdout)
                self.assertEqual(changed['display_title'], '검토한 과수원 계획 🌱')
                self.assertIs(type(changed['revision']), int)
                self.assertGreater(changed['revision'], 0)
                self.assertEqual(titles(self.db, '1', conversation)['revision'], changed['revision'])
                self.assertEqual(self.core_state(), core)

    def test_both_title_clis_preserve_unicode_and_whitespace_identity(self):
        source, conversation = '  출처 e\u0301 🌱  ', '  대화 é 🌱  '
        self.import_records(source, (conversation,))
        for script in ('recap.py', 'session_workflow.py'):
            with self.subTest(script=script):
                current = titles(self.db, source, conversation)
                result = self.cli(script, '--source', source, '--conversation', conversation,
                                  '--set', 'Unicode exact identity 🌱', '--expected-revision', str(current['revision']))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['display_title'], 'Unicode exact identity 🌱')
                self.assertEqual(self.history()[-1][1:3], (source, conversation))

    def test_both_title_clis_keep_valid_read_revision_informational(self):
        changed = titles(self.db, '1', '1', 'Current synthetic title', 0)
        before = self.archive_state()
        for script in ('recap.py', 'session_workflow.py'):
            result = self.cli(script, '--source', '1', '--conversation', '1', '--expected-revision', '0')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['revision'], changed['revision'])
        self.assertEqual(self.archive_state(), before)

    def test_both_title_clis_invalid_text_identity_is_clean_and_read_only(self):
        before = self.archive_state()
        cases = (('', '1', SOURCE_ERROR), (' \t\n', '1', SOURCE_ERROR), ('1', '', CONVERSATION_ERROR))
        for script in ('recap.py', 'session_workflow.py'):
            for source, conversation, error in cases:
                for write_args in ((), ('--set', 'Forbidden synthetic title', '--expected-revision', '0')):
                    with self.subTest(script=script, source=repr(source), conversation=repr(conversation), write=bool(write_args)):
                        self.assert_clean_failure(self.cli(script, '--source', source, '--conversation', conversation, *write_args), error)
        self.assertEqual(self.archive_state(), before)
        self.assertIsNone(self.history())

    def test_both_title_clis_surrogate_errors_do_not_echo_private_identity(self):
        before = self.archive_state()
        for script in ('recap.py', 'session_workflow.py'):
            for field in ('source', 'conversation'):
                for surrogate in SURROGATES:
                    identity = dict(source='1', conversation='1')
                    identity[field] = surrogate
                    for write_args in ((), ('--set', 'Forbidden synthetic title', '--expected-revision', '0')):
                        with self.subTest(script=script, field=field, value=repr(surrogate), write=bool(write_args)):
                            result = self.cli(script, '--source', identity['source'], '--conversation', identity['conversation'],
                                              *write_args, synthetic_argv=True)
                            self.assert_clean_failure(result, field + ' must contain valid Unicode text')
        self.assertEqual(self.archive_state(), before)

    def test_both_title_clis_negative_revision_precedes_missing_database(self):
        for script in ('recap.py', 'session_workflow.py'):
            for write_args in ((), ('--set', 'Forbidden synthetic title')):
                with self.subTest(script=script, write=bool(write_args)):
                    result = self.cli(script, '--source', '1', '--conversation', '1',
                                      '--expected-revision', '-1', *write_args, db=self.missing)
                    self.assert_clean_failure(result, REVISION_ERROR)
                    self.assertFalse(self.missing.exists())

    def test_both_title_clis_reject_fractional_and_noninteger_revision_tokens(self):
        before = self.archive_state()
        for script in ('recap.py', 'session_workflow.py'):
            for revision in ('1.0', 'true', '', 'null'):
                for write_args in ((), ('--set', 'Forbidden synthetic title')):
                    with self.subTest(script=script, revision=revision, write=bool(write_args)):
                        result = self.cli(script, '--source', '1', '--conversation', '1',
                                          '--expected-revision', revision, *write_args)
                        self.assert_clean_failure(result)
                        self.assertIn('invalid int value', result.stderr)
        self.assertEqual(self.archive_state(), before)

    def test_both_title_clis_still_require_write_revision(self):
        before = self.archive_state()
        for script in ('recap.py', 'session_workflow.py'):
            result = self.cli(script, '--source', '1', '--conversation', '1', '--set', 'Forbidden synthetic title')
            self.assert_clean_failure(result, '--set requires --expected-revision from a title preview')
        self.assertEqual(self.archive_state(), before)
        self.assertIsNone(self.history())

    def test_both_title_clis_stale_revision_leaves_no_partial_mutation_or_output(self):
        titles(self.db, '1', '1', 'Current synthetic title', 0)
        before = self.archive_state()
        for script in ('recap.py', 'session_workflow.py'):
            result = self.cli(script, '--source', '1', '--conversation', '1',
                              '--set', 'Forbidden synthetic title', '--expected-revision', '0')
            self.assert_clean_failure(result, 'stale title preview; preview again before applying')
        self.assertEqual(self.archive_state(), before)

    def test_both_title_clis_unknown_conversation_does_not_leak_identity_or_content(self):
        before = self.archive_state()
        for script in ('recap.py', 'session_workflow.py'):
            for source, conversation in ((PRIVATE_ID, '1'), ('1', PRIVATE_ID)):
                for write_args in ((), ('--set', 'Forbidden synthetic title', '--expected-revision', '0')):
                    result = self.cli(script, '--source', source, '--conversation', conversation, *write_args)
                    self.assert_clean_failure(result, 'unknown conversation')
        self.assertEqual(self.archive_state(), before)
        self.assertIsNone(self.history())


if __name__ == '__main__':
    unittest.main()
