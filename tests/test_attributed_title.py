"""Public-safe synthetic producer-attribution and raw-archive binding checks."""
import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from recaplib.attributed_title import suggest_attributed
from recaplib.session_workflow import import_export, inspect_export, titles
from recaplib.title_proposal import apply_preview, preview, snapshot


_MISSING = object()


def text_part(text, kind='input_text'):
    return dict(type=kind, text=text)


def label(kind):
    return dict(provenance=dict(type=kind))


def message(parts, metadata=_MISSING, identity='u', role='user'):
    payload = dict(type='message', role=role, content=parts)
    if identity is not None:
        payload['id'] = identity
    if metadata is not _MISSING:
        payload['internal_chat_message_metadata_passthrough'] = dict(content_item_metadata=metadata)
    return dict(type='response_item', timestamp='2026-01-01T00:00:00Z', payload=payload)


class AttributedTitleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.jsonl'
        self.db = Path(self.tmp.name) / 'archive.sqlite'
        self.records = [dict(type='session_meta', payload=dict(id='synthetic')),
                        message([text_part('Harness setup'), text_part('Synthetic orchard plan')],
                                [dict(harness_injected=True), label('user')]),
                        message([text_part('Synthetic assistant response', 'output_text')],
                                identity='a', role='assistant')]

    def write(self, *, imported=True, source='local'):
        self.path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in self.records), encoding='utf-8')
        if imported:
            import_export(self.db, source, self.path, 'local-codex')

    def suggest(self, path=None, source='local', conversation='synthetic'):
        return suggest_attributed(self.db, source, conversation, path or self.path)

    def test_mixed_harness_and_user_only_selects_explicit_user_text(self):
        self.write()
        proposal = self.suggest()
        self.assertEqual(proposal['title'], 'Synthetic orchard plan')
        self.assertEqual(proposal['provider'], 'local-extractive')
        self.assertEqual(proposal['evidence_message_ids'], ['u'])
        context = proposal['attribution_context']
        self.assertEqual(context['schema'], 'recap.source-attributed-title.v1')
        self.assertEqual(context['original_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertIs(context['producer_attribution_authenticated'], False)
        self.assertEqual(context['evidence_parts'], [dict(message_id='u', origin_locator='line:2', content_indices=[1])])
        self.assertEqual(context['coverage'], dict(total_text_parts=2, selected_user_text_parts=1,
            excluded_text_parts=1, unknown_text_parts=0, non_user_text_parts=1, messages_with_selected_text=1))
        rows, digest = snapshot(self.db, 'local', 'synthetic')
        self.assertEqual(proposal['content_sha256'], digest)
        self.assertEqual(rows[0]['text'], 'Harness setup\nSynthetic orchard plan')
        self.assertEqual(len(rows), 2)
        report = inspect_export(self.path, 'local-codex')
        report.pop('mode')
        receipt = import_export(self.db, 'local', self.path, 'local-codex')
        self.assertEqual(receipt['coverage'], report)
        self.assertEqual(report['rollout_context']['content_attribution_records'], 1)
        self.assertTrue(any('raw imports do not filter' in warning and 'authenticated' in warning
                            for warning in report['warnings']))
        self.assertNotIn('Harness setup', json.dumps(report))
        self.assertNotIn('provenance', json.dumps(report))

    def test_media_alignment_uses_all_content_positions(self):
        self.records[1] = message([dict(type='input_image', image_url='synthetic-image'),
            text_part('Excluded setup'), dict(type='input_audio', audio_url='synthetic-audio'),
            text_part('Synthetic media plan', 'output_text')],
            [label('user'), dict(harness_injected=True), {}, label('user')])
        self.write()
        proposal = self.suggest()
        self.assertEqual(proposal['title'], 'Synthetic media plan')
        self.assertEqual(proposal['attribution_context']['evidence_parts'][0]['content_indices'], [3])
        self.assertEqual(proposal['attribution_context']['coverage']['total_text_parts'], 2)

    def test_missing_null_and_legacy_metadata_never_infers_user(self):
        variants = [_MISSING, None, [{ }], [None], [dict(provenance=None)],
                    [dict(harness_injected=False)], [dict(harness_injected=True)],
                    [dict(source_tool_namespace='synthetic-tool')]]
        for metadata in variants:
            with self.subTest(metadata=metadata):
                self.records[1] = message([text_part('Unattributed request')], metadata)
                self.write(imported=False)
                with patch('sqlite3.connect', side_effect=AssertionError('database accessed before candidate validation')):
                    with self.assertRaises(ValueError):
                        self.suggest()
        self.assertFalse(self.db.exists())
        for wrapper in (None, {}):
            self.records[1] = message([text_part('Unattributed request')])
            self.records[1]['payload']['internal_chat_message_metadata_passthrough'] = wrapper
            self.write(imported=False)
            with self.assertRaises(ValueError):
                self.suggest()

    def test_unknown_and_legacy_coverage_and_wrapper_extras(self):
        entries = [{}, dict(harness_injected=False), label('unknown'), label('user_configured'),
                   dict(harness_injected=True), dict(source_tool_namespace='synthetic'),
                   label('skills'), label('agents_md'), label('harness'),
                   dict(provenance=dict(type='harness', hook=True)), label('tool'),
                   dict(provenance=dict(type='tool', namespace=None)),
                   dict(provenance=dict(type='tool', namespace='synthetic')),
                   dict(provenance=dict(type='developer_instructions', from_additional_requirements=False)),
                   dict(provenance=dict(type='user'), harness_injected=None, source_tool_namespace=None)]
        parts = [text_part('Excluded text ' + str(i)) for i in range(len(entries)-1)] + [text_part('Synthetic selected plan')]
        self.records[1] = message(parts, entries)
        self.records[1]['payload']['internal_chat_message_metadata_passthrough']['unrelated_field'] = {'safe': True}
        self.write()
        proposal = self.suggest()
        self.assertEqual(proposal['title'], 'Synthetic selected plan')
        self.assertEqual(proposal['attribution_context']['coverage'], dict(total_text_parts=15, selected_user_text_parts=1,
            excluded_text_parts=14, unknown_text_parts=4, non_user_text_parts=10, messages_with_selected_text=1))

    def test_bad_metadata_lengths_and_container_types_fail_closed(self):
        for metadata in ([], [label('user'), label('user')], {}, 'user', True, 7):
            with self.subTest(metadata=metadata):
                self.records[1] = message([text_part('Synthetic request')], metadata)
                self.write(imported=False)
                with self.assertRaises(ValueError):
                    self.suggest()
        for wrapper in ([], 'metadata', 3, False):
            self.records[1] = message([text_part('Synthetic request')])
            self.records[1]['payload']['internal_chat_message_metadata_passthrough'] = wrapper
            self.write(imported=False)
            with self.assertRaises(ValueError):
                self.suggest()
        self.assertFalse(self.db.exists())

    def test_malformed_entries_provenance_and_mixed_legacy_fail_closed(self):
        invalid = ['user', 2, False, [], dict(unknown_field=True), dict(provenance='user'),
            dict(provenance={}), dict(provenance=dict(type='future_type')),
            dict(provenance=dict(type='user', unknown_field=True)),
            dict(provenance=dict(type='harness', hook='false')),
            dict(provenance=dict(type='tool', namespace=3)),
            dict(provenance=dict(type='developer_instructions')),
            dict(provenance=dict(type='developer_instructions', from_additional_requirements=1)),
            dict(harness_injected='false'), dict(harness_injected=0), dict(source_tool_namespace=3),
            dict(provenance=dict(type='user'), harness_injected=False),
            dict(provenance=dict(type='user'), source_tool_namespace='synthetic')]
        for entry in invalid:
            with self.subTest(entry=entry):
                self.records[1] = message([text_part('Malformed attribution'), text_part('Synthetic request')], [entry, label('user')])
                self.write(imported=False)
                with self.assertRaises(ValueError):
                    self.suggest()
        self.assertFalse(self.db.exists())
        # Malformed attribution is ordinary archived source data, not an import filter.
        self.records[1]['payload']['internal_chat_message_metadata_passthrough']['content_item_metadata'] = [
            dict(secret_fixture_marker='synthetic-only'), label('user')]
        self.write(imported=False)
        report = inspect_export(self.path, 'local-codex')
        report.pop('mode')
        receipt = import_export(self.db, 'local', self.path, 'local-codex')
        self.assertEqual(receipt['coverage'], report)
        self.assertEqual(report['rollout_context']['content_attribution_records'], 1)
        self.assertNotIn('secret_fixture_marker', json.dumps(report))
        self.assertEqual(snapshot(self.db, 'local', 'synthetic')[0][0]['text'],
                         'Malformed attribution\nSynthetic request')
        with self.assertRaises(ValueError):
            self.suggest()

    def test_read_once_no_original_or_archive_mutation(self):
        self.write()
        original, database = self.path.read_bytes(), self.db.read_bytes()
        read_bytes = Path.read_bytes
        reads = []
        def tracked(path):
            if path == self.path:
                reads.append(path)
            return read_bytes(path)
        with patch.object(Path, 'read_bytes', tracked):
            self.suggest()
        self.assertEqual(len(reads), 1)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.db.read_bytes(), database)

    def test_title_revision_and_unselected_raw_content_bind_apply(self):
        self.write()
        reviewed = preview(self.db, self.suggest())
        titles(self.db, 'local', 'synthetic', 'Other reviewed title', 0)
        with self.assertRaises(ValueError):
            apply_preview(self.db, reviewed)
        reviewed = preview(self.db, self.suggest())
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE messages SET text='Changed assistant text' WHERE message_id='a'")
        with self.assertRaises(ValueError):
            apply_preview(self.db, reviewed)

    def test_all_selected_conversation_messages_verify_text_role_timestamp(self):
        self.write()
        for field, value in [('text', 'Different assistant text'), ('role', 'system'), ('timestamp', 'changed')]:
            with self.subTest(field=field):
                with closing(sqlite3.connect(self.db)) as connection, connection:
                    old = connection.execute(f'SELECT {field} FROM messages WHERE message_id=?', ('a',)).fetchone()[0]
                    connection.execute(f'UPDATE messages SET {field}=? WHERE message_id=?', (value, 'a'))
                with self.assertRaises(ValueError):
                    self.suggest()
                with closing(sqlite3.connect(self.db)) as connection, connection:
                    connection.execute(f'UPDATE messages SET {field}=? WHERE message_id=?', (old, 'a'))

    def test_original_byte_and_metadata_changes_need_exact_import(self):
        self.write()
        original = self.path.read_bytes()
        self.path.write_bytes(original + b'\n')
        with self.assertRaises(ValueError):
            self.suggest()
        self.path.write_bytes(original)
        self.records[1]['payload']['internal_chat_message_metadata_passthrough']['content_item_metadata'] = [label('user'), {}]
        self.write(imported=False)
        with self.assertRaises(ValueError):
            self.suggest()

    def test_missing_physical_occurrence_and_explicit_identity_rejected(self):
        self.write()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            for table in ('export_provenance', 'export_occurrences'):
                connection.execute(f"UPDATE {table} SET locator='line:99' WHERE message='a'")
        with self.assertRaises(ValueError):
            self.suggest()
        with closing(sqlite3.connect(self.db)) as connection, connection:
            for table in ('export_provenance', 'export_occurrences'):
                connection.execute(f"UPDATE {table} SET locator='line:3' WHERE message='a'")
                connection.execute(f"UPDATE {table} SET message='altered' WHERE message='u'")
            connection.execute("UPDATE messages SET message_id='altered' WHERE message_id='u'")
        with self.assertRaises(ValueError):
            self.suggest()

    def test_renamed_basename_resolves_fallback_ids_from_provenance(self):
        self.records[1]['payload'].pop('id')
        self.write()
        other = self.path.with_name('renamed.jsonl')
        other.write_bytes(self.path.read_bytes())
        self.assertEqual(self.suggest(), self.suggest(other))
        archived_id = snapshot(self.db, 'local', 'synthetic')[0][0]['message_id']
        self.assertEqual(self.suggest(other)['evidence_message_ids'], [archived_id])

    def test_ambiguous_duplicate_fallback_identity_rejected(self):
        self.records[1]['payload'].pop('id')
        self.write()
        other = self.path.with_name('renamed.jsonl')
        other.write_bytes(self.path.read_bytes())
        import_export(self.db, 'local', other, 'local-codex')
        for path in (self.path, other):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.suggest(path)

    def test_duplicate_occurrences_keep_distinct_part_labels(self):
        parts = [text_part('Synthetic orchard plan'), text_part('Harness detail')]
        self.records = self.records[:1] + [message(parts, [label('user'), dict(harness_injected=True)]),
            message(copy.deepcopy(parts), [dict(harness_injected=True), dict(harness_injected=True)])]
        self.write()
        proposal = self.suggest()
        self.assertEqual(proposal['title'], 'Synthetic orchard plan')
        self.assertEqual(proposal['attribution_context']['evidence_parts'],
                         [dict(message_id='u', origin_locator='line:2', content_indices=[0])])
        self.assertEqual(proposal['attribution_context']['coverage']['total_text_parts'], 4)
        self.assertEqual(proposal['attribution_context']['coverage']['selected_user_text_parts'], 1)
        self.assertEqual(len(snapshot(self.db, 'local', 'synthetic')[0]), 1)

    def test_source_and_conversation_isolation(self):
        self.write(source='other')
        with self.assertRaises(ValueError):
            self.suggest()
        self.write()
        with self.assertRaises(ValueError):
            self.suggest(conversation='missing')
        with closing(sqlite3.connect(self.db)) as connection, connection:
            connection.execute("UPDATE messages SET text='Other-source changed text' WHERE source_id='other'")
        self.assertEqual(self.suggest()['title'], 'Synthetic orchard plan')

    def test_cli_ascii_preview_apply_search_preserves_raw_history(self):
        self.records[1]['payload']['content'][1]['text'] = '합성 과수원 계획'
        self.write()
        original = self.path.read_bytes()
        def call(script, *args, encoding='ascii'):
            env = dict(os.environ, PYTHONIOENCODING=encoding)
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / script), *map(str, args)],
                                    capture_output=True, env=env, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr.decode('ascii', errors='replace'))
            return json.loads(result.stdout.decode(encoding))
        identity = ('--source', 'local', '--conversation', 'synthetic')
        proposal = call('recap.py', '--db', self.db, 'suggest-attributed-title', self.path, *identity)
        self.assertEqual(proposal, call('attributed_title.py', '--db', self.db, *identity, self.path))
        self.assertEqual(proposal['title'], '합성 과수원 계획')
        saved = Path(self.tmp.name) / 'proposal.json'
        saved.write_text(json.dumps(proposal), encoding='utf-8')
        reviewed = call('title_proposal.py', '--db', self.db, 'preview', saved)
        saved.write_text(json.dumps(reviewed), encoding='utf-8')
        call('title_proposal.py', '--db', self.db, 'apply', saved)
        self.assertEqual(call('recap.py', '--db', self.db, 'list')['conversations'][0]['display_title'], '합성 과수원 계획')
        self.assertEqual(call('recap.py', '--db', self.db, 'find', 'Harness setup')['total_matches'], 1)
        self.assertEqual(self.path.read_bytes(), original)

    def test_documented_synthetic_example_selects_original_content_index(self):
        path = Path('examples/source-attributed-session.jsonl')
        original = path.read_bytes()
        import_export(self.db, 'demo', path, 'local-codex')
        before = self.db.read_bytes()
        proposal = suggest_attributed(self.db, 'demo', 'synthetic-attributed', path)
        self.assertEqual(proposal['title'], 'Design a synthetic lunar calendar')
        self.assertEqual(proposal['attribution_context']['evidence_parts'], [dict(
            message_id='synthetic-u1', origin_locator='line:2', content_indices=[2])])
        reviewed = preview(self.db, proposal)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(apply_preview(self.db, reviewed)['display_title'], proposal['title'])
        self.assertEqual(path.read_bytes(), original)
        self.assertIn('Synthetic environment setup instructions', snapshot(
            self.db, 'demo', 'synthetic-attributed')[0][0]['text'])

    def test_physical_line_locators_match_all_supported_newlines(self):
        for ending in ('\n', '\r\n', '\r', 'mixed'):
            with self.subTest(ending=ending):
                # U+2028 stays inside a string, never a physical record boundary.
                self.records[1]['payload']['content'][1]['text'] = 'Synthetic\u2028orchard plan'
                encoded = [json.dumps(record, ensure_ascii=False).encode('utf-8') for record in self.records]
                ends = [b'\r', b'\r\n', b'\n'] if ending == 'mixed' else [ending.encode()] * 3
                self.path.write_bytes(b''.join(line + end for line, end in zip(encoded, ends)))
                source = 'synthetic-' + repr(ending)
                import_export(self.db, source, self.path, 'local-codex')
                proposal = self.suggest(source=source)
                self.assertEqual(proposal['title'], 'Synthetic orchard plan')
                self.assertEqual(proposal['attribution_context']['evidence_parts'], [dict(
                    message_id='u', origin_locator='line:2', content_indices=[1])])

    def test_mixed_newlines_cannot_attribute_an_excluded_event_payload(self):
        raw_message = message([text_part('Harness-only archived text')], [label('harness')])
        excluded_event = message([text_part('Synthetic excluded event text')], [label('user')])
        excluded_event['type'] = 'event_msg'
        encoded = [json.dumps(record).encode() for record in
                   (self.records[0], raw_message, excluded_event)]
        self.path.write_bytes(encoded[0] + b'\r' + encoded[1] + b'\n' + encoded[2] + b'\n')
        import_export(self.db, 'local', self.path, 'local-codex')
        before = self.db.read_bytes()
        self.assertEqual(len(snapshot(self.db, 'local', 'synthetic')[0]), 1)
        with self.assertRaisesRegex(ValueError, 'no explicitly user-attributed text'):
            self.suggest()
        self.assertEqual(self.db.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
