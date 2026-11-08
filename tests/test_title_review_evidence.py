"""Independent synthetic coverage for opt-in, bounded title-review evidence."""
import copy
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

from recaplib import title_proposal
from recap import ingest
from recaplib.session_workflow import titles
from recaplib.title_proposal import apply_preview, preview, snapshot


class TitleReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.texts = {f'u{i}': f'Synthetic user evidence {i}' for i in range(7)}
        self.texts['u0'] = '\x00Harness text\n  🌱 기전\t' + 'ß' * 2100 + ' Actual selected request'
        records = [dict(conversation_id='chat', message_id=mid, role='user',
                        text=text, timestamp='synthetic', title='Original synthetic title')
                   for mid, text in self.texts.items()]
        records.append(dict(conversation_id='chat', message_id='a0', role='assistant',
                            text='Synthetic assistant secret', timestamp='synthetic', title='Original synthetic title'))
        source = self.root / 'synthetic.jsonl'
        source.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
        self.imported = ingest(self.db, 'demo', source)
        _, digest = snapshot(self.db, 'demo', 'chat')
        self.proposal = dict(source='demo', conversation='chat', title='Synthetic chosen title',
                             provider='operator', content_sha256=digest,
                             evidence_message_ids=['u0'])

    def evidence(self, proposal=None):
        return preview(self.db, proposal or self.proposal, with_evidence=True)['review_evidence']

    def provenance(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            for table in ('export_provenance', 'export_occurrences'):
                c.execute(f'CREATE TABLE {table} (source TEXT, conversation TEXT, message TEXT, original_hash TEXT, locator TEXT, parent TEXT)')
            rows = [('demo', 'chat', 'u0', f'hash{i}', f'line:{i}', None) for i in range(5)]
            c.executemany('INSERT INTO export_provenance VALUES(?,?,?,?,?,?)', rows[:2])
            c.executemany('INSERT INTO export_occurrences VALUES(?,?,?,?,?,?)', rows)
            c.execute('INSERT INTO export_occurrences VALUES(?,?,?,?,?,?)', ('other', 'chat', 'u0', 'private-other-source', 'line:9', None))
            c.execute('INSERT INTO export_occurrences VALUES(?,?,?,?,?,?)', ('demo', 'other', 'u0', 'private-other-chat', 'line:9', None))

    def test_default_shape_and_opt_in_read_only(self):
        before = self.db.read_bytes()
        ordinary = preview(self.db, self.proposal)
        self.assertEqual(set(ordinary), {'proposal', 'title_advisory', 'previous_title', 'expected_revision', 'semantic_validation', 'remote_mutation'})
        self.assertEqual(ordinary, preview(self.db, self.proposal, with_evidence=False))
        richer = preview(self.db, self.proposal, with_evidence=True)
        self.assertEqual(ordinary, {k: v for k, v in richer.items() if k != 'review_evidence'})
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(titles(self.db, 'demo', 'chat')['revision'], 0)

    def test_fixed_caps_dedup_selection_and_exact_raw_unicode_slice(self):
        proposal = dict(self.proposal, evidence_message_ids=['u0', 'u0', 'u6', 'u2', 'u3', 'u4', 'u5', 'u1', 'u6'])
        result = self.evidence(proposal)
        self.assertEqual(result['schema'], 'recap.title-review-evidence.v1')
        self.assertEqual(result['content_sha256'], proposal['content_sha256'])
        for key, expected in dict(total_references=9, distinct_messages=7, duplicate_references=2,
                                  returned_messages=5, omitted_messages=2, max_messages=5,
                                  max_excerpt_characters=2000, max_provenance_occurrences=3).items():
            self.assertEqual(result[key], expected, key)
        self.assertIs(result['contains_message_text'], True)
        self.assertTrue(result['scope']); self.assertTrue(result['warning'])
        self.assertEqual([m['message_id'] for m in result['messages']], ['u0', 'u6', 'u2', 'u3', 'u4'])
        for message in result['messages']:
            text = self.texts[message['message_id']]
            self.assertEqual(message['role'], 'user')
            self.assertEqual(message['text_excerpt'], text[:2000])
            self.assertEqual(message['excerpt_start'], 0)
            self.assertEqual(message['excerpt_end'], min(len(text), 2000))
            self.assertEqual(message['text_characters'], len(text))
            self.assertEqual(message['text_truncated'], len(text) > 2000)
            self.assertEqual(message['source_sha256'], self.imported['source_sha256'])
            self.assertEqual(message['source_line'], int(message['message_id'][1:]) + 1)
            self.assertEqual(message['export_provenance'], [])
            self.assertEqual(message['export_provenance_count'], 0)
            self.assertFalse(message['export_provenance_truncated'])

    def test_raw_scoped_metadata_cannot_substitute_excerpt(self):
        proposal = dict(self.proposal, attribution_context={'evidence_parts': [{'text': 'Forged selected text'}]},
                        branch_context={'messages': [{'text': 'Forged branch text'}]},
                        projection_context={'text': 'Forged projection text'})
        original = copy.deepcopy(proposal)
        evidence = self.evidence(proposal)
        self.assertEqual(evidence['messages'][0]['text_excerpt'], self.texts['u0'][:2000])
        self.assertEqual(proposal, original)
        self.assertNotIn('Synthetic assistant secret', json.dumps(evidence))
        evidence['messages'][0]['text_excerpt'] = 'Only changed returned display'
        self.assertEqual(self.evidence(proposal)['messages'][0]['text_excerpt'], self.texts['u0'][:2000])

    def test_provenance_sorted_union_exact_count_and_scope(self):
        self.provenance()
        before = self.db.read_bytes()
        message = self.evidence()['messages'][0]
        self.assertEqual(message['export_provenance_count'], 5)
        self.assertTrue(message['export_provenance_truncated'])
        self.assertEqual(message['export_provenance'], [dict(original_sha256=f'hash{i}', locator=f'line:{i}', parent_id=None) for i in range(3)])
        self.assertEqual(self.db.read_bytes(), before)

    def test_legacy_only_and_additive_only_provenance(self):
        self.provenance()
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('DROP TABLE export_occurrences')
        message = self.evidence()['messages'][0]
        self.assertEqual(message['export_provenance_count'], 2)
        self.assertFalse(message['export_provenance_truncated'])
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('ALTER TABLE export_provenance RENAME TO export_occurrences')
        self.assertEqual(self.evidence()['messages'][0], message)

    def test_options_and_nonfinite_documents_fail_before_database_access(self):
        for invalid in (None, 0, 1, '', 'true', [], {}):
            with self.subTest(invalid=invalid), patch.object(title_proposal, 'readonly') as read:
                with self.assertRaises(ValueError):
                    preview(self.db, self.proposal, with_evidence=invalid)
                read.assert_not_called()
        with patch.object(title_proposal, 'readonly') as read:
            with self.assertRaises(ValueError):
                preview(self.db, dict(self.proposal, metadata=float('nan')), with_evidence=True)
            read.assert_not_called()

    def test_invalid_or_stale_evidence_is_rejected_not_silently_omitted(self):
        for change in ({'evidence_message_ids': ['a0']}, {'evidence_message_ids': ['missing']},
                       {'evidence_message_ids': ['u0', 'missing']}, {'content_sha256': 'stale'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.evidence(dict(self.proposal, **change))

    def test_replacement_and_descriptive_evidence_do_not_authorize_apply(self):
        reviewed = preview(self.db, self.proposal, 'Explicit synthetic replacement', with_evidence=True)
        self.assertEqual(reviewed['proposal']['provider'], 'operator')
        self.assertEqual(reviewed['review_evidence']['messages'][0]['text_excerpt'], self.texts['u0'][:2000])
        reviewed['review_evidence'] = {'caller_edited': 'Not an approval token'}
        self.assertEqual(titles(self.db, 'demo', 'chat')['revision'], 0)
        applied = apply_preview(self.db, reviewed)
        self.assertEqual(applied['display_title'], 'Explicit synthetic replacement')
        before = self.db.read_bytes()
        with self.assertRaises(ValueError):
            apply_preview(self.db, reviewed)
        self.assertEqual(self.db.read_bytes(), before)

    def test_both_clis_ascii_output_and_apply_rejects_preview_only_flag(self):
        path = self.root / 'proposal.json'
        path.write_text(json.dumps(self.proposal), encoding='utf-8')
        expected = preview(self.db, self.proposal, with_evidence=True)
        for script, command, apply_command in [('recap.py', 'preview-title', 'apply-title'), ('title_proposal.py', 'preview', 'apply')]:
            result = subprocess.run([sys.executable, script, '--db', str(self.db), command, str(path), '--with-evidence'],
                                    capture_output=True, env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.decode('ascii')), expected)
            invalid = subprocess.run([sys.executable, script, '--db', str(self.db), apply_command, str(path), '--with-evidence'],
                                     capture_output=True, timeout=20)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertNotIn(b'Traceback', invalid.stderr)

    def test_default_does_not_fetch_evidence_and_missing_database_stays_missing(self):
        with patch.object(title_proposal, 'review_evidence') as helper:
            preview(self.db, self.proposal)
            helper.assert_not_called()
        missing = self.root / 'does-not-exist.sqlite'
        with self.assertRaises(sqlite3.Error):
            preview(missing, self.proposal, with_evidence=True)
        self.assertFalse(missing.exists())

    def test_exact_excerpt_boundary_and_empty_legacy_text(self):
        # Empty legacy text can be present in an existing archive even though
        # current normalized ingestion rejects empty bodies. Never invent text.
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("UPDATE messages SET text=? WHERE message_id='u0'", ('🌱' * 2000,))
            c.execute("UPDATE messages SET text='' WHERE message_id='u1'")
        _, digest = snapshot(self.db, 'demo', 'chat')
        result = self.evidence(dict(self.proposal, content_sha256=digest, evidence_message_ids=['u0', 'u1']))
        first, second = result['messages']
        self.assertEqual(first['text_excerpt'], '🌱' * 2000)
        self.assertFalse(first['text_truncated'])
        self.assertEqual(first['excerpt_end'], 2000)
        self.assertEqual(second['text_excerpt'], '')
        self.assertEqual(second['text_characters'], 0)
        self.assertEqual(second['excerpt_end'], 0)
        self.assertFalse(second['text_truncated'])

    def test_shipped_branch_and_attributed_import_preview_apply_search(self):
        from recaplib.attributed_title import suggest_attributed
        from recaplib.branch_title import suggest_branch
        from recaplib.conversation_search import find
        from recaplib.conversation_view import conversation
        from recaplib.session_workflow import import_export
        cases = [
            ('web-export.json', 'web', 'web-demo', 'synthetic-chat',
             'Design a synthetic orchard experiment', 'orchard',
             lambda db, source, cid, path: suggest_branch(db, source, cid, path, 'm2')),
            ('source-attributed-session.jsonl', 'local-codex', 'local-demo', 'synthetic-attributed',
             'Design a synthetic lunar calendar', 'lunar', suggest_attributed),
        ]
        for filename, kind, source, cid, expected_title, query, suggest in cases:
            with self.subTest(kind=kind):
                path = Path('examples') / filename
                original_bytes = path.read_bytes()
                db = self.root / (kind + '-walkthrough.sqlite')
                import_export(db, source, path, kind)
                proposal = suggest(db, source, cid, path)
                self.assertEqual(proposal['title'], expected_title)
                archive = conversation(db, source, cid)
                by_id = {row['message_id']: row for row in archive['messages']}
                before = db.read_bytes()
                reviewed = preview(db, proposal, with_evidence=True)
                self.assertEqual(db.read_bytes(), before)
                self.assertEqual(reviewed['expected_revision'], 0)
                evidence = reviewed['review_evidence']
                self.assertEqual(evidence['omitted_messages'], 0)
                self.assertEqual([m['message_id'] for m in evidence['messages']], proposal['evidence_message_ids'])
                for message in evidence['messages']:
                    raw = by_id[message['message_id']]
                    self.assertEqual(raw['role'], 'user')
                    self.assertEqual(message['text_excerpt'], raw['text'])
                    self.assertFalse(message['text_truncated'])
                    self.assertEqual(message['source_sha256'], raw['source_sha256'])
                    self.assertEqual(message['source_line'], raw['source_line'])
                    self.assertEqual(message['export_provenance'], raw['export_provenance'])
                    self.assertEqual(message['export_provenance_count'], len(raw['export_provenance']))
                    self.assertGreater(message['export_provenance_count'], 0)
                if kind == 'local-codex':
                    raw_excerpt = evidence['messages'][0]['text_excerpt']
                    self.assertTrue(raw_excerpt.startswith('Synthetic environment setup instructions'))
                    self.assertIn(expected_title, raw_excerpt)
                    self.assertNotIn('environment', proposal['title'])
                applied = apply_preview(db, reviewed)
                self.assertGreater(applied['revision'], 0)
                self.assertEqual(titles(db, source, cid)['display_title'], expected_title)
                result = find(db, query, source=source)
                matching = [row for row in result['matches'] if row['conversation_id'] == cid]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0]['display_title'], expected_title)
                self.assertEqual(path.read_bytes(), original_bytes)

    def test_single_connection_snapshot_survives_concurrent_wal_changes(self):
        self.provenance()
        prior = titles(self.db, 'demo', 'chat', 'Old reviewed synthetic title', 0)
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual(c.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        real_rows = title_proposal._snapshot_rows
        real_readonly = title_proposal.readonly
        def mutate_after_rows(connection, source, conversation):
            result = real_rows(connection, source, conversation)
            with closing(sqlite3.connect(self.db)) as c, c:
                c.execute("UPDATE messages SET text='Changed synthetic content',source_line=999 WHERE source_id='demo' AND conversation_id='chat' AND message_id='u0'")
                c.execute("INSERT INTO title_history(source,conversation,previous,title) VALUES('demo','chat','Old reviewed synthetic title','Concurrent synthetic title')")
                c.execute("INSERT INTO export_occurrences VALUES('demo','chat','u0','hash9','line:9',NULL)")
            return result
        with patch.object(title_proposal, '_snapshot_rows', mutate_after_rows), patch.object(title_proposal, 'readonly', wraps=real_readonly) as opened:
            reviewed = preview(self.db, self.proposal, with_evidence=True)
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(reviewed['previous_title'], 'Old reviewed synthetic title')
        self.assertEqual(reviewed['expected_revision'], prior['revision'])
        message = reviewed['review_evidence']['messages'][0]
        self.assertEqual(message['text_excerpt'], self.texts['u0'][:2000])
        self.assertEqual(message['source_line'], 1)
        self.assertEqual(message['export_provenance_count'], 5)
        with self.assertRaises(ValueError):
            preview(self.db, self.proposal, with_evidence=True)
        with self.assertRaises(ValueError):
            apply_preview(self.db, reviewed)
        self.assertEqual(titles(self.db, 'demo', 'chat')['display_title'], 'Concurrent synthetic title')


if __name__ == '__main__':
    unittest.main()
