"""Synthetic pre-import body discovery without body-bearing result fields."""
import hashlib
import json
import os
import shlex
import sqlite3
from contextlib import closing
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from recaplib.export_inventory import list_export
from recaplib.session_workflow import import_export, titles
from recaplib.conversation_view import conversations


class ExportInventoryTextFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'synthetic.json'
        self.db = self.root / 'archive.sqlite'

    @staticmethod
    def web(identity, body='Synthetic body', role='user', title='Other title'):
        return dict(id=identity, title=title, mapping={'m': dict(parent=None,
            message=dict(author=dict(role=role), content=dict(parts=[body])))})

    @staticmethod
    def message(body, role='user', identity='m'):
        return dict(type='response_item', payload=dict(type='message', id=identity,
            role=role, content=[dict(type='input_text' if role == 'user' else 'output_text', text=body)]))

    def web_file(self, records):
        self.path.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')

    def local_file(self, sessions):
        records = []
        for identity, messages in sessions:
            records.append(dict(type='session_meta', payload=dict(id=identity,
                title='Hidden metadata title', cwd='/Synthetic/PrivatePath')))
            records.extend(messages)
        self.path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in records), encoding='utf-8')

    def cli(self, script, *args, ok=True):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / script), *map(str, args)],
            cwd=self.root, capture_output=True, text=True, encoding='utf-8', timeout=20,
            env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertTrue(result.stdout.isascii())
        return json.loads(result.stdout) if ok else result.stderr

    def ids(self, kind='web', **kwargs):
        return [r['conversation'] for r in list_export(self.path, kind, **kwargs)['conversations']]

    def test_opaque_local_ids_discovered_only_by_body_filter(self):
        self.local_file([('00000000-a', [self.message('Other topic')]),
                         ('00000000-b', [self.message('Remember the cobalt orchard request')])])
        for kind in ('local', 'local-codex'):
            self.assertEqual(self.ids(kind, contains='cobalt orchard'), [])
            self.assertEqual(self.ids(kind, text_contains='COBALT ORCHARD'), ['00000000-b'])
            for needle in ('Hidden metadata title', 'PrivatePath', '00000000-b'):
                self.assertEqual(self.ids(kind, text_contains=needle), [])

    def test_counts_use_matching_rows_once_and_full_identity_metadata(self):
        repeated = self.message('Needle needle needle')
        self.local_file([('opaque', [repeated, repeated, self.message('Needle', 'assistant', 'a'),
                                     self.message('Other', identity='other')])])
        for kind in ('local', 'local-codex'):
            result = list_export(self.path, kind, text_contains='needle')
            item, = result['conversations']
            self.assertEqual(item['matched_messages'], 3)
            self.assertEqual(item['matched_role_counts'], {'assistant': 1, 'user': 2})
            self.assertEqual(list(item['matched_role_counts']), ['assistant', 'user'])
            self.assertEqual(item['extracted_messages'], 4)
            self.assertEqual(item['role_counts'], {'assistant': 1, 'user': 3})
            self.assertEqual(result['filter']['matched_messages'], 3)

    def test_all_extracted_web_roles_and_noncurrent_branch(self):
        records = [self.web(role, 'Needle', role) for role in ('user', 'assistant', 'system', 'tool')]
        branch = self.web('branch', 'Other')
        branch['mapping']['alternate'] = dict(parent='m', message=dict(author=dict(role='assistant'),
            content=dict(parts=['Needle on alternate branch'])))
        branch['current_node'] = 'm'
        records.append(branch)
        self.web_file(records)
        result = list_export(self.path, 'web', text_contains='needle')
        self.assertEqual(result['filter']['matched_messages'], 5)
        self.assertEqual(self.ids(text_contains='needle'), ['assistant', 'branch', 'system', 'tool', 'user'])
        self.assertEqual(result['coverage']['branch_policy'], 'all mapping nodes in export order; current_node is not selected')

    def test_rollback_does_not_remove_raw_extracted_text(self):
        self.local_file([('opaque', [self.message('Needle before rollback'),
            dict(type='event_msg', payload=dict(type='thread_rolled_back', num_turns=1))])])
        for kind in ('local', 'local-codex'):
            result = list_export(self.path, kind, text_contains='needle')
            self.assertEqual(len(result['conversations']), 1)
            self.assertFalse(result['coverage']['effective_history_reconstructed'])
            self.assertEqual(result['coverage']['rollout_context']['rollback_events'], 1)

    def test_never_cross_messages_metadata_or_identities_but_keep_part_join(self):
        a = self.web('alpha', 'alpha', title='beta')
        a['mapping']['n'] = dict(parent='m', message=dict(author=dict(role='user'), content=dict(parts=['beta'])))
        b = self.web('b', 'Other'); b['mapping']['m']['message']['content']['parts'] = ['alpha', 'beta']
        self.web_file([a, b, self.web('c', 'beta')])
        self.assertEqual(self.ids(text_contains='alpha beta'), [])
        self.assertEqual(self.ids(text_contains='alphabeta'), [])
        self.assertEqual(self.ids(text_contains='alpha\nbeta'), ['b'])
        self.local_file([('a', [self.message('alpha'), self.message('beta', identity='n')])])
        for kind in ('local', 'local-codex'):
            self.assertEqual(self.ids(kind, text_contains='alpha\nbeta'), [])

    def test_literal_punctuation_whitespace_and_casefold(self):
        self.web_file([self.web('a', 'literal %_*[x] "quote"'), self.web('b', ' alpha '),
                       self.web('c', 'Straße')])
        for needle, ids in [('%_*[x]', ['a']), ('"quote"', ['a']), (' alpha ', ['b']),
                            ('STRASSE', ['c']), ('alpha|beta', [])]:
            self.assertEqual(self.ids(text_contains=needle), ids)

    def test_canonical_unicode_exact_ids_and_no_compatibility_normalization(self):
        self.web_file([self.web('Café', 'Café'), self.web('Cafe\u0301', 'Cafe\u0301'),
            self.web('hangul', '\u1100\u1161'), self.web('wide', 'Ａ')])
        self.assertEqual(self.ids(text_contains='CAFÉ'), ['Café'])
        result = list_export(self.path, 'web', text_contains='CAFÉ', canonical_unicode=True)
        self.assertEqual([r['conversation'] for r in result['conversations']], ['Cafe\u0301', 'Café'])
        self.assertEqual(result['filter']['normalization'], 'NFC(NFD(text).casefold())')
        self.assertEqual(result['filter']['unicode_version'], unicodedata.unidata_version)
        self.assertEqual(self.ids(text_contains='가', canonical_unicode=True), ['hangul'])
        self.assertNotIn('wide', self.ids(text_contains='A', canonical_unicode=True))

    def test_duplicate_web_id_keeps_ambiguity_and_all_metadata(self):
        self.web_file([self.web('duplicate', 'Other', title='First title'),
                       self.web('duplicate', 'Needle', title='Second title'), self.web('good', 'Needle')])
        result = list_export(self.path, 'web', text_contains='needle')
        item = result['conversations'][0]
        self.assertEqual(item['original_titles'], ['First title', 'Second title'])
        self.assertEqual(item['metadata_records'], 2)
        self.assertEqual(item['extracted_messages'], 2)
        self.assertEqual(item['matched_messages'], 1)
        self.assertEqual(item['selection_blocker'], 'AMBIGUOUS_WEB_ID')
        self.assertEqual(result['filter']['matched_conversations'], 2)
        self.assertEqual(result['filter']['matched_selectable_conversations'], 1)
        with self.assertRaises(ValueError):
            import_export(self.db, 'demo', self.path, 'web', 'duplicate')
        self.assertFalse(self.db.exists())

    def test_sparse_pagination_global_counts_and_late_match(self):
        self.web_file([self.web(f'chat-{i:04}', 'Needle' if i in (1001, 1020, 1049) else 'Other')
                       for i in reversed(range(1050))])
        full = list_export(self.path, 'web', limit=1000)
        pages = [list_export(self.path, 'web', text_contains='needle', limit=1, offset=i) for i in range(4)]
        self.assertEqual([r['conversation'] for p in pages for r in p['conversations']],
                         ['chat-1001', 'chat-1020', 'chat-1049'])
        self.assertEqual([p['next_offset'] for p in pages], [1, 2, None, None])
        for p in pages:
            self.assertEqual(p['filter']['matched_messages'], 3)
            self.assertEqual(p['filter']['matched_conversations'], 3)
            for key in ('coverage', 'total_conversations', 'selectable_conversations', 'original_sha256', 'original_bytes'):
                self.assertEqual(p[key], full[key])
        self.assertEqual(list_export(self.path, 'web', text_contains='absent')['filter']['matched_messages'], 0)

    def test_empty_export_and_no_text(self):
        self.web_file([])
        result = list_export(self.path, 'web', text_contains='needle')
        self.assertEqual(result['filter']['matched_messages'], 0)
        self.assertEqual(result['conversations'], [])
        media = self.web('media'); media['mapping']['m']['message']['content']['parts'] = [dict(text='Needle')]
        self.web_file([media])
        self.assertEqual(self.ids(text_contains='needle'), [])

    def test_invalid_unselected_content_still_fails(self):
        for bad in (dict(id='bad', title=3, mapping={}), dict(id='bad', mapping=[]),
                    dict(id='bad', mapping={'bad': dict(parent='missing')})):
            self.web_file([self.web('good', 'Needle'), bad])
            for needle in ('needle', 'absent'):
                with self.subTest(bad=bad, needle=needle), self.assertRaises(ValueError):
                    list_export(self.path, 'web', text_contains=needle, limit=1, offset=999)
        self.local_file([('good', [self.message('Needle')])])
        with self.path.open('a', encoding='utf-8') as output:
            output.write('\n' + json.dumps(dict(type='session_meta', payload={})))
        for kind in ('local', 'local-codex'):
            with self.assertRaises(ValueError):
                list_export(self.path, kind, text_contains='absent', offset=999)

    def test_arguments_validate_before_read(self):
        invalid = ['', ' ', '\n\t', 'x'*257, '\ud800', 'x\udfff', 0, False, [], {}, b'needle']
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('validate before read')):
            for value in invalid:
                with self.subTest(value=repr(value)), self.assertRaisesRegex(ValueError, '^text_contains'):
                    list_export(self.path, 'web', text_contains=value)
            with self.assertRaisesRegex(ValueError, 'choose either contains or text_contains, not both'):
                list_export(self.path, 'web', contains='a', text_contains='b')
            for value in (0, 1, None, 'true', [], {}):
                with self.assertRaises(ValueError):
                    list_export(self.path, 'web', text_contains='a', canonical_unicode=value)
            with self.assertRaises(ValueError):
                list_export(self.path, 'web', canonical_unicode=True)

    def test_existing_local_extraction_whitespace_parts_and_typed_skips(self):
        joined = self.message('unused')
        joined['payload']['content'] = [dict(type='input_text', text=' alpha'),
            dict(type='input_text', text='beta ')]
        skipped = self.message('unused', identity='skipped')
        skipped['payload']['content'] = [dict(type='input_image', text='Hidden unsupported text')]
        self.local_file([('opaque', [joined, skipped])])
        self.assertEqual(self.ids('local-codex', text_contains=' alpha\nbeta '), ['opaque'])
        self.assertEqual(self.ids('local', text_contains=' alpha\nbeta '), [])
        self.assertEqual(self.ids('local', text_contains='alpha\nbeta'), ['opaque'])
        self.assertEqual(self.ids('local-codex', text_contains='Hidden unsupported text'), [])
        self.assertEqual(self.ids('local', text_contains='Hidden unsupported text'), ['opaque'])

    def test_supported_web_text_fields_and_skipped_nested_metadata(self):
        records = []
        for kind in ('code', 'execution_output'):
            record = self.web(kind)
            record['mapping']['m']['message']['content'] = dict(content_type=kind, text='Needle source')
            records.append(record)
        unsupported = self.web('unsupported')
        unsupported['mapping']['m']['message']['content'] = dict(content_type='other', text='Needle hidden')
        records.append(unsupported)
        nested = self.web('nested')
        nested['mapping']['m']['message']['content'] = dict(parts=[dict(text='Needle hidden')])
        records.append(nested)
        self.web_file(records)
        result = list_export(self.path, 'web', text_contains='needle')
        self.assertEqual([r['conversation'] for r in result['conversations']], ['code', 'execution_output'])
        self.assertEqual(result['filter']['matched_messages'], 2)
        self.assertEqual(result['coverage']['text_field_messages'], 2)

    def test_256_codepoints_and_unchanged_default_metadata_shapes(self):
        self.web_file([self.web('needle', '한'*256)])
        self.assertEqual(self.ids(text_contains='한'*256), ['needle'])
        self.assertEqual(list_export(self.path, 'web'), list_export(self.path, 'web', text_contains=None))
        default = list_export(self.path, 'web')
        metadata = list_export(self.path, 'web', contains='needle')
        self.assertNotIn('filter', default)
        self.assertNotIn('text_contains', metadata['filter'])
        for result in (default, metadata):
            self.assertNotIn('matched_messages', result['conversations'][0])
            self.assertNotIn('matched_role_counts', result['conversations'][0])

    def test_no_body_fields_source_snapshot_lease_and_database(self):
        for kind in ('web', 'local', 'local-codex'):
            body = 'Needle PRIVATE_FULL_BODY_SENTINEL'
            if kind == 'web': self.web_file([self.web('opaque', body)])
            else: self.local_file([('opaque', [self.message(body)])])
            raw = self.path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
            with patch.object(Path, 'read_bytes', return_value=raw) as reader, \
                    patch('sqlite3.connect', side_effect=AssertionError('no database')):
                result = list_export(self.path, kind, text_contains='needle', expected_export_sha256=digest)
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(result['original_sha256'], digest)
            self.assertEqual(result['coverage']['expected_export_sha256'], digest)
            self.assertEqual(result['original_bytes'], len(raw))
            self.assertEqual(self.path.read_bytes(), raw)
            self.assertFalse(result['contains_message_text'])
            self.assertNotIn('PRIVATE_FULL_BODY_SENTINEL', json.dumps(result))
            self.assertEqual(result['filter']['fields'], ['extracted_message_text'])
            self.assertEqual(result['filter']['matching'], 'literal substring within one case-folded extracted message')
            self.assertIn('message_scope', result['filter'])
            self.assertIn('warning', result['filter'])
            forbidden = {'text', 'body', 'excerpt', 'message_id', 'origin_locator'}
            self.assertTrue(forbidden.isdisjoint(result['conversations'][0]))
            with self.assertRaises(ValueError):
                list_export(self.path, kind, text_contains='absent', expected_export_sha256='0'*64)
        self.assertEqual({p.name for p in self.root.iterdir()}, {self.path.name})

    def test_both_cli_entrypoints_and_clean_mutual_exclusion(self):
        for kind in ('web', 'local', 'local-codex'):
            if kind == 'web': self.web_file([self.web('opaque', 'Cafe\u0301')])
            else: self.local_file([('opaque', [self.message('Cafe\u0301')])])
            digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
            for canonical, needle in ((False, 'CAFE'), (True, 'CAFÉ')):
                extra = ['--text-contains', needle, '--limit', 1, '--offset', 0, '--expected-export-sha256', digest]
                if canonical: extra += ['--canonical-unicode']
                expected = list_export(self.path, kind, text_contains=needle, canonical_unicode=canonical,
                    limit=1, expected_export_sha256=digest)
                for script, prefix in (('recap.py', ['list-export']), ('export_inventory.py', [])):
                    self.assertEqual(self.cli(script, *prefix, self.path, '--format', kind, *extra), expected)
        for script, prefix in (('recap.py', ['list-export']), ('export_inventory.py', [])):
            for extra in (['--text-contains', ''], ['--text-contains', 'x'*257],
                          ['--contains', 'a', '--text-contains', 'b'], ['--canonical-unicode']):
                self.cli(script, *prefix, self.path, '--format', 'local-codex', *extra, ok=False)

    def test_exact_documented_phrase_discovery_commands(self):
        root = Path(__file__).resolve().parents[1]
        doc = (root / 'docs' / 'EXPORT_INVENTORY.md').read_text(encoding='utf-8')
        section = doc.split('## Find a conversation by remembered message text', 1)[1].split(
            '### From a phrase to a reviewed title', 1)[0]
        commands = [shlex.split(line) for line in section.splitlines() if line.startswith('python ')]
        self.assertEqual(len(commands), 3)
        for tokens in commands:
            args = [str(root / token) if token.startswith('examples/') else token for token in tokens[2:]]
            result = self.cli(tokens[1], *args)
            expected = 'synthetic-chat' if 'web' in args else 'synthetic-attributed'
            self.assertEqual([r['conversation'] for r in result['conversations']], [expected])
            self.assertEqual(result['filter']['matched_conversations'], 1)
            self.assertIsNone(result['next_offset'])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_exact_documented_phrase_to_reviewed_title_walkthrough(self):
        root = Path(__file__).resolve().parents[1]
        doc = (root / 'docs' / 'EXPORT_INVENTORY.md').read_text(encoding='utf-8')
        section = doc.split('### From a phrase to a reviewed title', 1)[1].split(
            '## Pages, privacy and unchanged source bytes', 1)[0]
        # Tokenize fixed documentation BEFORE substituting platform-native paths.
        commands = [shlex.split(line) for line in section.splitlines()
                    if line.startswith(('python ', 'mkdir '))]
        self.assertEqual(len(commands), 8)
        scratch = self.root / 'synthetic walkthrough with spaces'
        db = scratch / 'archive.sqlite'
        fixture = root / 'examples' / 'title-focus-local.jsonl'
        raw = fixture.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(digest, '4bf9f45d8f22b79b4469002d62a4b3ef82a60fdceb340b0c2bfdd036f678209b')
        expected_title = 'Compare synthetic orchard watering schedules'
        def substitute(token):
            if token.startswith('examples/'):
                return str(root / token)
            prefix = '../recap-text-search-demo'
            if token == prefix or token.startswith(prefix + '/'):
                return str(scratch / token[len(prefix):].lstrip('/'))
            return token
        def archive_evidence():
            with closing(sqlite3.connect(db)) as connection:
                return {table: connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid').fetchall()
                        for table in ('messages', 'export_provenance', 'export_occurrences')}
        evidence = None
        before_apply = None
        for number, tokens in enumerate(commands):
            args = [substitute(token) for token in tokens[2:]]
            if tokens[0] == 'mkdir':
                self.assertEqual(number, 0)
                Path(substitute(tokens[1])).mkdir()
                continue
            result = self.cli(tokens[1], *args)
            if number == 1:
                item, = result['conversations']
                self.assertEqual(item['conversation'], 'synthetic-local-focus')
                self.assertEqual(item['matched_messages'], 1)
                self.assertEqual(item['matched_role_counts'], {'user': 1})
                self.assertEqual(item['extracted_messages'], 6)
                self.assertEqual(result['original_sha256'], digest)
                self.assertFalse(db.exists())
            elif number == 2:
                self.assertIn('--expected-export-sha256', args)
                self.assertEqual(args[args.index('--expected-export-sha256') + 1], digest)
                self.assertEqual(result['inserted'], 6)
                evidence = archive_evidence()
                before_apply = db.read_bytes()
            elif number == 3:
                self.assertEqual([m['message_id'] for m in result['messages']], ['focus-user'])
                self.assertEqual(result['messages'][0]['text'], expected_title)
            elif number in (4, 5):
                self.assertEqual(result['status'], 'SAVED')
                saved = Path(args[args.index('--output') + 1]).read_bytes()
                self.assertEqual(result['encoding'], 'UTF-8')
                self.assertEqual(result['bytes'], len(saved))
                self.assertEqual(result['sha256'], hashlib.sha256(saved).hexdigest())
                document = json.loads(saved.decode('utf-8'))
                proposal = document if number == 4 else document['proposal']
                self.assertEqual(proposal['title'], expected_title)
                self.assertEqual(proposal['evidence_message_ids'], ['focus-user'])
                if number == 5:
                    self.assertIn('--with-evidence', args)
            elif number == 6:
                self.assertEqual(result['display_title'], expected_title)
                self.assertGreater(result['revision'], 0)
            elif number == 7:
                self.assertEqual(result['total_matches'], 1)
            if 2 <= number <= 5:
                self.assertEqual(titles(db, 'local-search', 'synthetic-local-focus')['revision'], 0)
                self.assertEqual(db.read_bytes(), before_apply)
            if number >= 2:
                self.assertEqual(archive_evidence(), evidence)
            self.assertEqual(fixture.read_bytes(), raw)
        self.assertEqual(titles(db, 'local-search', 'synthetic-local-focus')['display_title'], expected_title)

    def test_selected_import_native_utf8_proposal_preview_and_explicit_apply(self):
        for kind in ('web', 'local', 'local-codex'):
            with self.subTest(kind=kind):
                db = self.root / (kind + '.sqlite')
                phrase = '합성 과수원 계획 🌱'
                if kind == 'web': self.web_file([self.web('a', 'Other'), self.web('opaque', phrase)])
                else: self.local_file([('a', [self.message('Other')]), ('opaque', [self.message(phrase)])])
                raw = self.path.read_bytes()
                inventory = list_export(self.path, kind, text_contains='과수원')
                item, = inventory['conversations']
                receipt = self.cli('recap.py', '--db', db, 'import', self.path, '--format', kind,
                    '--source', kind, '--conversation', item['conversation'],
                    '--expected-export-sha256', inventory['original_sha256'])
                self.assertEqual(receipt['inserted'], 1)
                self.assertEqual([r['conversation'] for r in conversations(db, kind)['conversations']], ['opaque'])
                before = db.read_bytes()
                proposal = self.root / (kind + '-proposal.json')
                reviewed = self.root / (kind + '-reviewed.json')
                self.cli('recap.py', '--db', db, 'suggest-title', '--source', kind,
                         '--conversation', 'opaque', '--output', proposal)
                proposal_doc = json.loads(proposal.read_text(encoding='utf-8'))
                self.assertEqual(proposal_doc['title'], phrase)
                self.assertIn(phrase.encode('utf-8'), proposal.read_bytes())
                self.cli('recap.py', '--db', db, 'preview-title', proposal, '--output', reviewed)
                review_doc = json.loads(reviewed.read_text(encoding='utf-8'))
                self.assertEqual(review_doc['proposal']['title'], phrase)
                self.assertIn(phrase.encode('utf-8'), reviewed.read_bytes())
                self.assertEqual(db.read_bytes(), before)
                applied = self.cli('recap.py', '--db', db, 'apply-title', reviewed)
                self.assertEqual(applied['display_title'], phrase)
                self.assertEqual(titles(db, kind, 'opaque')['display_title'], phrase)
                self.assertEqual(self.path.read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
