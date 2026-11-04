"""Synthetic explicit archive-message selection within verified branch/replay scopes."""
import copy
import hashlib
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from branch_title import branch_evidence, suggest_branch
from replay_title import replay_evidence, suggest_replay
from session_workflow import import_export, titles
from title_excerpt import excerpt
from title_proposal import apply_preview, preview, snapshot
from test_replay_local import event, turn


class ScopedMessageSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.web = self.root / 'web.json'
        self.local = self.root / 'local.jsonl'
        self.texts = {'opening': 'Can you help with this project?',
                      'chosen': 'Compare synthetic orchard irrigation designs',
                      'greeting': 'Hello!', 'empty': '!? 👩\u200d🔬',
                      'prefix': '!' * 80 + 'Later letters',
                      'unicode': '\x00합성\n\t연구 👩\u200d🔬 می\u200cروم\u202e ' + '검토 ' * 80}
        mapping = {}
        parent = None
        for identity, text in self.texts.items():
            mapping[identity] = self.web_message(parent, text)
            parent = identity
        mapping['assistant'] = self.web_message(parent, 'Synthetic assistant answer', 'assistant')
        mapping['excluded'] = self.web_message('opening', 'Abandoned synthetic topic')
        self.web_data = [dict(id='web-chat', title='Original', current_node='assistant', mapping=mapping)]
        self.records = [dict(type='session_meta', payload=dict(id='local-chat')), *turn('discarded'),
                        event('thread_rolled_back', num_turns=1)]
        for identity, text in self.texts.items():
            records = turn(identity)
            records[1]['payload']['message'] = text
            records[2]['payload']['content'][0]['text'] = text
            self.records.extend(records)
        self.write_import()

    @staticmethod
    def web_message(parent, text, role='user'):
        return dict(parent=parent, message=dict(author=dict(role=role), content=dict(parts=[text])))

    def write_import(self):
        self.web.write_text(json.dumps(self.web_data), encoding='utf-8')
        self.local.write_text(''.join(json.dumps(r) + '\n' for r in self.records), encoding='utf-8')
        import_export(self.db, 'web', self.web, 'web')
        import_export(self.db, 'local', self.local, 'local-codex')

    def suggest(self, mode, identity=None, **kwargs):
        if mode == 'branch':
            return suggest_branch(self.db, 'web', 'web-chat', self.web, message_id=identity, **kwargs)
        return suggest_replay(self.db, 'local', 'local-chat', self.local, message_id=identity, **kwargs)

    def identity(self, mode, stem):
        return stem if mode == 'branch' else stem + 'u'

    def scope(self, mode):
        return ('web', 'web-chat') if mode == 'branch' else ('local', 'local-chat')

    def test_later_choice_preserves_full_fingerprint_and_scope_context(self):
        for mode in ('branch', 'replay'):
            with self.subTest(mode=mode):
                default = self.suggest(mode)
                chosen = self.identity(mode, 'chosen')
                result = self.suggest(mode, chosen)
                self.assertEqual(result['title'], self.texts['chosen'])
                self.assertEqual(result['evidence_message_ids'], [chosen])
                self.assertEqual(result['content_sha256'], snapshot(self.db, *self.scope(mode))[1])
                self.assertEqual(result['content_sha256'], default['content_sha256'])
                self.assertEqual(result['evidence_selection'], dict(mode='explicit_user_message', message_id=chosen,
                    scope='verified web export branch' if mode == 'branch' else 'verified retained local turns'))
                if mode == 'branch':
                    self.assertEqual(result['branch_context'], default['branch_context'])
                else:
                    context = copy.deepcopy(result['projection_context'])
                    mappings = context.pop('evidence_mappings')
                    other = copy.deepcopy(default['projection_context']); other.pop('evidence_mappings')
                    self.assertEqual(context, other)
                    self.assertEqual([m['archive_message_id'] for m in mappings], [chosen])

    def test_default_and_none_preserve_existing_selection(self):
        for mode in ('branch', 'replay'):
            omitted = (suggest_branch(self.db, 'web', 'web-chat', self.web) if mode == 'branch'
                       else suggest_replay(self.db, 'local', 'local-chat', self.local))
            self.assertEqual(omitted, self.suggest(mode, None))
            self.assertNotIn('evidence_selection', omitted)
            self.assertEqual(omitted['title'], self.texts['opening'])

    def test_invalid_shapes_reject_before_any_source_or_archive_read(self):
        for mode in ('branch', 'replay'):
            for bad in ('', False, 0, 1, [], {}, b'chosen'):
                with self.subTest(mode=mode, bad=bad), patch.object(Path, 'read_bytes', side_effect=AssertionError('source read')), patch('sqlite3.connect', side_effect=AssertionError('archive read')):
                    with self.assertRaisesRegex(ValueError, 'selected message ID must be nonempty text'):
                        self.suggest(mode, bad)

    def test_nonuser_missing_and_out_of_scope_rejected(self):
        cases = {'branch': ('assistant', 'excluded', 'miss', ' chos en ', 'chosenu'),
                 'replay': ('chosena', 'discardedu', 'miss', ' chosenu ', 'chosen')}
        for mode, values in cases.items():
            for identity in values:
                with self.subTest(mode=mode, identity=identity), self.assertRaises(ValueError):
                    self.suggest(mode, identity)

    def test_node_choice_does_not_make_later_message_in_scope(self):
        with self.assertRaises(ValueError):
            self.suggest('branch', 'chosen', node='opening')
        selected = self.suggest('branch', 'excluded', node='excluded')
        self.assertEqual(selected['title'], 'Abandoned synthetic topic')

    def test_unusable_selection_never_falls_back(self):
        for mode in ('branch', 'replay'):
            for stem in ('empty', 'prefix'):
                with self.subTest(mode=mode, stem=stem), self.assertRaisesRegex(ValueError, 'no usable user'):
                    self.suggest(mode, self.identity(mode, stem))

    def test_greeting_is_selected_explicitly(self):
        for mode in ('branch', 'replay'):
            result = self.suggest(mode, self.identity(mode, 'greeting'))
            self.assertEqual(result['title'], 'Hello!')
            self.assertEqual(result['selection_method'], 'first_user_greeting_fallback')

    def test_unicode_cleaning_and_eighty_codepoint_bound_unchanged(self):
        for mode in ('branch', 'replay'):
            identity = self.identity(mode, 'unicode')
            result = self.suggest(mode, identity)
            expected = excerpt([dict(message_id=identity, role='user', text=self.texts['unicode'])])
            for key, value in expected.items():
                self.assertEqual(result[key], value)
            self.assertLessEqual(len(result['title']), 80)
            self.assertTrue(result['truncated'])

    def test_selection_does_not_bypass_other_scoped_content_verification(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE messages SET text='Corrupted synthetic opener' WHERE message_id IN ('opening','openingu')")
        for mode in ('branch', 'replay'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.suggest(mode, self.identity(mode, 'chosen'))

    def test_selection_does_not_bypass_discarded_replay_provenance(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            for table in ('export_provenance', 'export_occurrences'):
                connection.execute(f"DELETE FROM {table} WHERE message='discardedu'")
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.suggest('replay', 'chosenu')

    def test_selection_does_not_bypass_other_branch_provenance(self):
        with closing(sqlite3.connect(self.db)) as connection, connection:
            for table in ('export_provenance', 'export_occurrences'):
                connection.execute(f"DELETE FROM {table} WHERE message='opening'")
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.suggest('branch', 'chosen')

    def test_unselected_raw_content_change_blocks_reviewed_apply(self):
        for mode, identity in (('branch', 'excluded'), ('replay', 'discardedu')):
            reviewed = preview(self.db, self.suggest(mode, self.identity(mode, 'chosen')))
            with closing(sqlite3.connect(self.db)) as connection, connection:
                connection.execute('UPDATE messages SET text=? WHERE message_id=?', ('Changed synthetic raw history', identity))
            with self.assertRaisesRegex(ValueError, 'snapshot'):
                apply_preview(self.db, reviewed)

    def test_mutation_cases_close_connections_without_garbage_collection(self):
        # Keep strong references to every connection, so CPython refcounting
        # cannot hide an unclosed handle that locks files on Windows/PyPy.
        original_connect = sqlite3.connect
        names = (
            'test_selection_does_not_bypass_discarded_replay_provenance',
            'test_selection_does_not_bypass_other_branch_provenance',
            'test_selection_does_not_bypass_other_scoped_content_verification',
            'test_unselected_raw_content_change_blocks_reviewed_apply',
        )
        for name in names:
            with self.subTest(case=name):
                case = type(self)(name)
                connections = []
                def tracked_connect(*args, **kwargs):
                    connection = original_connect(*args, **kwargs)
                    connections.append(connection)
                    return connection
                try:
                    case.setUp()
                    with patch('sqlite3.connect', side_effect=tracked_connect):
                        getattr(case, name)()
                    self.assertTrue(connections, 'mutation case must open a tracked connection')
                    for connection in connections:
                        with self.assertRaisesRegex(sqlite3.ProgrammingError, 'closed'):
                            connection.execute('SELECT 1')
                finally:
                    # Even a regression must release handles before temporary
                    # directory cleanup, without masking the failed assertion.
                    for connection in connections:
                        connection.close()
                    self.assertTrue(case.doCleanups(), 'nested mutation-case cleanup failed')

    def test_ambiguous_scoped_rows_fail_closed(self):
        for mode, evidence, module in (('branch', branch_evidence, 'branch_title'), ('replay', replay_evidence, 'replay_title')):
            path = self.web if mode == 'branch' else self.local
            rows, digest, context = evidence(self.db, *self.scope(mode), path)
            chosen = self.identity(mode, 'chosen')
            duplicate = next(row for row in rows if row['message_id'] == chosen)
            with patch(module + '.' + mode + '_evidence', return_value=(rows + [duplicate], digest, context)):
                with self.assertRaises(ValueError):
                    self.suggest(mode, chosen)

    def test_source_read_once_and_source_archive_unchanged(self):
        before = self.db.read_bytes(), self.web.read_bytes(), self.local.read_bytes()
        original = Path.read_bytes
        for mode in ('branch', 'replay'):
            path = self.web if mode == 'branch' else self.local
            reads = []
            def tracked(candidate):
                if candidate == path:
                    reads.append(candidate)
                return original(candidate)
            with patch.object(Path, 'read_bytes', tracked):
                self.suggest(mode, self.identity(mode, 'chosen'))
            self.assertEqual(reads, [path])
        self.assertEqual(before, (self.db.read_bytes(), self.web.read_bytes(), self.local.read_bytes()))

    def test_renamed_idless_replay_selects_original_archive_id_not_projection_id(self):
        records = copy.deepcopy(self.records)
        for record in records:
            if record['type'] == 'response_item':
                record['payload'].pop('id', None)
        path = self.root / 'idless.jsonl'
        path.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
        import_export(self.db, 'idless', path, 'local-codex')
        rows, _, context = replay_evidence(self.db, 'idless', 'local-chat', path)
        chosen = next(row['message_id'] for row in rows if row['text'] == self.texts['chosen'])
        projection = next(m['projection_id'] for m in context['projection_context']['evidence_mappings'] if m['archive_message_id'] == chosen)
        renamed = self.root / 'renamed.jsonl'; renamed.write_bytes(path.read_bytes())
        result = suggest_replay(self.db, 'idless', 'local-chat', renamed, message_id=chosen)
        self.assertEqual(result['evidence_message_ids'], [chosen])
        self.assertEqual(result['title'], self.texts['chosen'])
        self.assertNotEqual(chosen, projection)
        with self.assertRaises(ValueError):
            suggest_replay(self.db, 'idless', 'local-chat', renamed, message_id=projection)

    def call(self, script, *args, ok=True):
        result = subprocess.run([sys.executable, str(Path(__file__).parent / script), '--db', str(self.db), *map(str, args)],
            capture_output=True, timeout=20, env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0 if ok else 1, result.stderr.decode('ascii', errors='replace'))
        self.assertNotIn(b'Traceback', result.stderr)
        return json.loads(result.stdout) if ok else result

    def test_unified_standalone_cli_parity_and_saved_review_apply_search(self):
        for mode in ('branch', 'replay'):
            source, conversation = self.scope(mode)
            path = self.web if mode == 'branch' else self.local
            identity = self.identity(mode, 'chosen')
            args = (path, '--source', source, '--conversation', conversation, '--message', identity)
            direct = self.call(mode + '_title.py', *args)
            self.assertEqual(direct, self.call('recap.py', 'suggest-' + mode + '-title', *args))
            proposal = self.root / (mode + '-proposal.json')
            reviewed = self.root / (mode + '-reviewed.json')
            receipt = self.call('recap.py', 'suggest-' + mode + '-title', *args, '--output', proposal)
            self.assertEqual(receipt['status'], 'SAVED')
            self.assertEqual(json.loads(proposal.read_text()), direct)
            self.call('recap.py', 'preview-title', proposal, '--output', reviewed)
            self.assertEqual(json.loads(reviewed.read_text())['proposal'], direct)
            changed = self.call('recap.py', 'apply-title', reviewed)
            self.assertEqual(changed['display_title'], self.texts['chosen'])
            self.call('recap.py', 'apply-title', reviewed, ok=False)
            found = self.call('recap.py', 'find', 'orchard irrigation')
            self.assertGreaterEqual(found['total_matches'], 1)

    def test_published_scoped_commands_require_separate_review_and_apply(self):
        repository = Path(__file__).parent
        doc = (repository / 'docs/TITLE_REVIEW_HINTS.md').read_text(encoding='utf-8')
        section = doc.split('## Choose a later message inside a verified branch or retained history', 1)[1].split('## Unicode excerpt boundaries', 1)[0]
        commands = [line for line in section.splitlines() if line.startswith(('mkdir ', 'python recap.py '))]
        self.assertEqual(len(commands), 14)
        scratch = self.root / 'scoped example with spaces'
        db = scratch / 'archive.sqlite'
        fixtures = [repository / 'examples/title-focus-web.json', repository / 'examples/title-focus-local.jsonl']
        originals = {path: path.read_bytes() for path in fixtures}
        self.assertEqual(len(originals[fixtures[1]].splitlines()), 17)
        expected = {
            'web-focus': ('synthetic-title-focus', 'u2', 'Compare synthetic orchard irrigation schedules'),
            'local-focus': ('synthetic-local-focus', 'focus-user', 'Compare synthetic orchard watering schedules')}
        snapshots, revisions, saved = {}, {}, {}
        baseline = None
        results, applied = [], []
        for line in commands:
            # Tokenize POSIX documentation first, then inject platform-specific paths.
            args = [arg.replace('../recap-scoped-focus-demo', str(scratch)) for arg in shlex.split(line)]
            if args[0] == 'mkdir':
                Path(args[1]).mkdir()
                continue
            self.assertEqual(args.pop(0), 'python')
            is_apply = 'apply-title' in args
            if is_apply:
                self.assertEqual(len(saved), 4)
                reviewed = json.loads(Path(args[-1]).read_bytes())
                proposal = reviewed['proposal']
                source = proposal['source']
                apply_source = source
                conversation, identity, title = expected[source]
                self.assertEqual(proposal['conversation'], conversation)
                self.assertEqual(proposal['evidence_message_ids'], [identity])
                self.assertEqual(proposal['title'], title)
                self.assertEqual(reviewed['expected_revision'], 0)
                self.assertEqual(reviewed['previous_title'], titles(db, source, conversation)['display_title'])
                self.assertEqual(titles(db, source, conversation)['revision'], 0)
                evidence = reviewed['review_evidence']['messages'][0]
                self.assertEqual(evidence['message_id'], identity)
                self.assertGreater(evidence['export_provenance_count'], 0)
            for source, revision in revisions.items():
                self.assertEqual(titles(db, source, expected[source][0])['revision'], revision)
            if baseline is not None:
                self.assertEqual(db.read_bytes(), baseline)
            result = subprocess.run([sys.executable, *args], cwd=repository, capture_output=True, timeout=20,
                env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(b'Traceback', result.stderr)
            value = json.loads(result.stdout)
            results.append(value)
            if 'import' in args:
                source = args[args.index('--source') + 1]
                snapshots[source] = snapshot(db, source, expected[source][0])
                revisions[source] = 0
                self.assertEqual(len(snapshots[source][0]), 3 if source == 'web-focus' else 6)
                baseline = db.read_bytes()
            elif is_apply:
                self.assertEqual(value['display_title'], title)
                self.assertGreater(value['revision'], 0)
                revisions[apply_source] = value['revision']
                applied.append(apply_source)
                baseline = db.read_bytes()
            else:
                if baseline is not None:
                    self.assertEqual(db.read_bytes(), baseline)
            if '--output' in args:
                output = Path(args[args.index('--output') + 1])
                raw = output.read_bytes()
                kind = 'preview' if 'preview-title' in args else 'proposal'
                self.assertEqual(value['schema'], 'recap.saved-title-json.v1')
                self.assertEqual(value['status'], 'SAVED')
                self.assertEqual(value['document_kind'], kind)
                self.assertEqual(value['bytes'], len(raw))
                self.assertEqual(value['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertTrue(value['staging_cleanup_complete'])
                self.assertNotIn('proposal', value)
                document = json.loads(raw.decode('utf-8'))
                saved[output.name] = document
                if kind == 'preview':
                    self.assertEqual(document['proposal'], saved[output.name.replace('-reviewed', '-proposal')])
                    self.assertEqual(document['expected_revision'], 0)
            if 'replay-local' in args:
                self.assertTrue(value['supported'])
                self.assertEqual(value['retained_turns'], 2)
                self.assertEqual(value['rolled_back_turns'], 1)
            for source, initial in snapshots.items():
                self.assertEqual(snapshot(db, source, expected[source][0]), initial)
                self.assertEqual(titles(db, source, expected[source][0])['revision'], revisions[source])
            for path, original in originals.items():
                self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(results), 13)
        self.assertEqual(applied, ['web-focus', 'local-focus'])
        self.assertEqual(results[-1]['total_matches'], 1)
        self.assertEqual(results[-1]['matches'][0]['display_title'], expected['local-focus'][2])
        self.assertIn('discarded-user', [row['message_id'] for row in snapshots['local-focus'][0]])

    def test_cli_invalid_selection_has_no_output_file_or_traceback(self):
        for mode in ('branch', 'replay'):
            source, conversation = self.scope(mode)
            path = self.web if mode == 'branch' else self.local
            for script in ('recap.py', mode + '_title.py'):
                output = self.root / ('invalid-' + mode + '-' + script + '.json')
                args = (() if script != 'recap.py' else ('suggest-' + mode + '-title',))
                self.call(script, *args, path, '--source', source, '--conversation', conversation,
                          '--message', 'missing', '--output', output, ok=False)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
