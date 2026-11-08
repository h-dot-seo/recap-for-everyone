"""Synthetic explicit-proposal subsets: selection precedes pagination and states."""
import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from recaplib import title_batch
from recap import ingest
from recaplib.session_workflow import titles
from recaplib.title_batch import review_queue, select_proposal
from recaplib.title_proposal import snapshot
from recaplib.title_review_state import review_state


class SuppliedQueueSubsetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root / 'archive.sqlite'
        self.add_records('demo', [f'chat-{i:03}' for i in range(30)])

    def add_records(self, source, ids):
        path = self.root / 'input.jsonl'
        path.write_text(''.join(json.dumps(dict(conversation_id=cid, message_id=cid+'-u',
            role='user', timestamp='synthetic', text='Synthetic request '+cid,
            title='Original '+cid))+'\n' for cid in ids), encoding='utf-8')
        ingest(self.db, source, path)

    def proposal(self, cid='chat-029', source='demo', **changes):
        value = dict(source=source, conversation=cid, content_sha256=snapshot(self.db, source, cid)[1],
                     title='Suggested '+cid, provider='operator', evidence_message_ids=[cid+'-u'])
        value.update(changes); return value

    def queue(self, supplied, **kwargs):
        return review_queue(self.db, 'demo', supplied_proposals=supplied, supplied_only=True, **kwargs)

    def decide(self, cid, state):
        lease = review_state(self.db, 'demo', cid)
        return review_state(self.db, 'demo', cid, state, lease['state_revision'],
                            lease['expected_title_revision'], lease['expected_content_sha256'])

    def counts(self, queue, total, renamed, unsupplied, state):
        self.assertEqual(queue['total_conversations'], total)
        self.assertEqual(queue['excluded_renamed_conversations'], renamed)
        self.assertEqual(queue['excluded_unsupplied_conversations'], unsupplied)
        self.assertEqual(queue['excluded_review_state_conversations'], state)
        self.assertEqual(total+renamed+unsupplied+state, queue['source_total_conversations'])
        self.assertIs(queue['supplied_only'], True)

    def cli(self, *args, success=True):
        result = subprocess.run([sys.executable, 'recap.py', '--db', str(self.db), *map(str, args)],
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr.decode(errors='replace'))
        self.assertNotIn(b'Traceback', result.stderr)
        return json.loads(result.stdout) if success else result

    def save(self, obj, name):
        path = self.root/name; path.write_text(json.dumps(obj), encoding='utf-8'); return path

    def test_late_identity_not_hidden_by_default_first_twenty(self):
        proposals = [self.proposal()]
        default = review_queue(self.db, 'demo', supplied_proposals=proposals)
        self.assertEqual(default['ready_count'], 0); self.assertEqual(len(default['items']), 20)
        before = self.db.read_bytes()
        subset = self.queue(proposals)
        self.assertEqual([i['conversation'] for i in subset['items']], ['chat-029'])
        self.assertEqual(subset['ready_count'], 1); self.assertIsNone(subset['next_offset'])
        self.counts(subset, 1, 0, 29, 0)
        self.assertEqual(subset['supplied_proposals']['on_page'], 1)
        self.assertEqual(before, self.db.read_bytes())

    def test_default_false_exactly_preserves_shape_and_behavior(self):
        for proposals in (None, [], [self.proposal()]):
            for state in (None, 'open', 'deferred'):
                with self.subTest(proposals=proposals, state=state):
                    args = dict(supplied_proposals=proposals, review_state_filter=state, offset=2, limit=4)
                    default = review_queue(self.db, 'demo', **args)
                    explicit = review_queue(self.db, 'demo', supplied_only=False, **args)
                    self.assertEqual(default, explicit)
                    self.assertNotIn('supplied_only', explicit)
                    self.assertNotIn('excluded_unsupplied_conversations', explicit)

    def test_strict_bool_and_required_proposals_validated_before_open(self):
        with patch.object(title_batch, 'readonly', side_effect=AssertionError('must validate before DB')):
            for value in (None, 0, 1, '', 'true', [], {}):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    review_queue(self.db, 'demo', supplied_proposals=[], supplied_only=value)
            with self.assertRaises(ValueError): review_queue(self.db, 'demo', supplied_only=True)

    def test_empty_unknown_and_missing_source_have_no_invented_items(self):
        for proposals in ([], [dict(source='demo', conversation='not-imported')]):
            queue = self.queue(proposals)
            self.assertEqual(queue['items'], []); self.counts(queue, 0, 0, 30, 0)
            self.assertEqual(queue['supplied_proposals']['on_page'], 0)
            self.assertEqual(queue['supplied_proposals']['not_on_page'], len(proposals))
        missing = review_queue(self.db, 'missing', supplied_only=True,
                               supplied_proposals=[dict(source='missing', conversation='chat-029')])
        self.assertEqual(missing['items'], []); self.counts(missing, 0, 0, 0, 0)

    def test_stale_and_invalid_candidates_remain_selected_without_fallback(self):
        proposals = [self.proposal('chat-027', content_sha256='0'*64),
                     self.proposal('chat-028', title=''), self.proposal('chat-029')]
        with patch.object(title_batch, 'excerpt', side_effect=AssertionError('no fallback')):
            queue = self.queue(proposals)
        self.counts(queue, 3, 0, 27, 0)
        self.assertEqual([i.get('reason_code') for i in queue['items']],
                         ['SUPPLIED_PROPOSAL_STALE', 'SUPPLIED_PROPOSAL_INVALID', None])
        self.assertEqual(queue['unavailable_count'], 2)
        self.assertEqual(queue['supplied_proposals']['on_page'], 3)

    def test_database_order_before_pagination_not_file_order(self):
        extra = ['Z-late', 'a-late', 'é-late', '한글-late']; self.add_records('demo', extra)
        ids = ['chat-029', 'chat-025'] + extra
        proposals = [self.proposal(cid) for cid in reversed(ids)]
        expected = [i['conversation'] for i in review_queue(self.db, 'demo', limit=100)['items']
                    if i['conversation'] in ids]
        actual = []; offset = 0
        while True:
            queue = self.queue(proposals, limit=2, offset=offset)
            actual.extend(i['conversation'] for i in queue['items'])
            self.assertEqual(queue['supplied_proposals']['on_page'], len(queue['items']))
            self.assertEqual(queue['supplied_proposals']['not_on_page'], len(ids)-len(queue['items']))
            if queue['next_offset'] is None: break
            offset = queue['next_offset']
        self.assertEqual(actual, expected)
        self.assertEqual(self.queue(proposals, offset=2**63-1)['items'], [])

    def test_combined_exclusions_have_disjoint_counts_before_pagination(self):
        titles(self.db, 'demo', 'chat-000', 'Renamed unsupplied', 0)
        titles(self.db, 'demo', 'chat-025', 'Renamed supplied', 0)
        self.decide('chat-001', 'deferred')
        self.decide('chat-027', 'deferred'); self.decide('chat-028', 'deferred')
        self.decide('chat-029', 'skipped')
        proposals = [self.proposal(f'chat-{i:03}') for i in range(25, 30)]
        queue = self.queue(proposals, unrenamed_only=True, review_state_filter='deferred', limit=1, offset=1)
        self.counts(queue, 2, 2, 24, 2)
        self.assertEqual([i['conversation'] for i in queue['items']], ['chat-028'])
        self.assertEqual(queue['supplied_proposals']['not_on_page'], 4)
        self.assertIsNone(queue['next_offset'])

    def test_source_isolation_and_collision_checks_outside_subset(self):
        self.add_records('other', ['chat-029', 'only-other'])
        titles(self.db, 'demo', 'chat-000', 'Collision title', 0)
        titles(self.db, 'other', 'chat-029', 'Collision title', 0)
        self.decide('chat-000', 'skipped')
        proposals = [self.proposal(title='COLLISION  TITLE'), dict(source='demo', conversation='only-other')]
        queue = self.queue(proposals, unrenamed_only=True, review_state_filter='open')
        self.counts(queue, 1, 1, 28, 0)
        self.assertEqual(queue['items'][0]['collisions']['existing_title_conversations'], ['chat-000'])
        self.assertEqual(queue['items'][0]['collisions']['existing_title_count'], 1)
        self.assertEqual(queue['supplied_proposals']['not_on_page'], 1)
        with self.assertRaises(ValueError): self.queue([self.proposal(source='other')])

    def test_collision_peers_only_selected_page_and_deep_copy(self):
        proposals = [self.proposal(cid, title='Shared synthetic title', context={'notes': ['original']})
                     for cid in ('chat-028', 'chat-029')]
        both = self.queue(proposals)
        self.assertEqual([i['collisions']['page_proposal_count'] for i in both['items']], [1, 1])
        one = self.queue(proposals, limit=1)
        self.assertEqual(one['items'][0]['collisions']['page_proposal_count'], 0)
        one['items'][0]['proposal']['context']['notes'].append('changed')
        self.assertEqual(proposals[0]['context']['notes'], ['original'])

    def test_content_changes_reopen_decisions_but_make_supplied_candidate_stale(self):
        candidate = self.proposal(); self.decide('chat-029', 'deferred')
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE messages SET text='Updated synthetic request' WHERE source_id='demo' AND conversation_id='chat-029'")
            conn.commit()
        before = self.db.read_bytes()
        self.counts(self.queue([candidate], review_state_filter='deferred'), 0, 0, 29, 1)
        queue = self.queue([candidate], review_state_filter='open')
        self.counts(queue, 1, 0, 29, 0)
        self.assertTrue(queue['items'][0]['review_state']['stale_decision'])
        self.assertEqual(queue['items'][0]['reason_code'], 'SUPPLIED_PROPOSAL_STALE')
        self.assertEqual(before, self.db.read_bytes())

    def test_title_changes_use_current_metadata_and_effective_state(self):
        candidate = self.proposal(); self.decide('chat-029', 'skipped')
        titles(self.db, 'demo', 'chat-029', 'Current reviewed title', 0)
        queue = self.queue([candidate], review_state_filter='open')
        self.assertEqual(queue['items'][0]['current_title'], 'Current reviewed title')
        self.assertEqual(queue['items'][0]['current_revision'], 1)
        self.assertEqual(queue['items'][0]['status'], 'READY')
        self.assertTrue(queue['items'][0]['review_state']['stale_decision'])
        self.counts(self.queue([candidate], unrenamed_only=True), 0, 1, 29, 0)

    def test_excluded_unsupplied_bodies_are_never_loaded_even_for_state_filter(self):
        proposals = [self.proposal()]; original = title_batch.readonly
        for state in (None, 'open'):
            statements = []
            def traced(db):
                conn = original(db); conn.set_trace_callback(statements.append); return conn
            with patch.object(title_batch, 'readonly', traced):
                queue = self.queue(proposals, review_state_filter=state)
            self.assertEqual(queue['ready_count'], 1)
            body_queries = [q for q in statements if q.lstrip().upper().startswith('SELECT MESSAGE_ID,ROLE,TEXT')]
            self.assertTrue(body_queries)
            self.assertTrue(all("conversation_id='chat-029'" in q for q in body_queries), body_queries)

    def test_chunk_boundary_selection_is_complete(self):
        self.add_records('demo', [f'z-{i:03}' for i in range(181)])
        candidates = [self.proposal('z-180'), self.proposal('z-100'), self.proposal('chat-029')]
        self.decide('z-100', 'deferred'); self.decide('z-180', 'deferred')
        queue = self.queue(candidates, review_state_filter='deferred', limit=1, offset=1)
        self.counts(queue, 2, 0, 208, 1)
        self.assertEqual(queue['items'][0]['conversation'], 'z-180')
        self.assertIsNone(queue['next_offset'])

    def test_single_snapshot_during_concurrent_content_state_and_title_changes(self):
        candidate = self.proposal(title='Original chat-000'); self.decide('chat-029', 'deferred')
        with closing(sqlite3.connect(self.db)) as conn: conn.execute('PRAGMA journal_mode=WAL')
        original = title_batch._inventory; changed = []
        def mutate(connection, *args, **kwargs):
            records = original(connection, *args, **kwargs)
            if not changed:
                changed.append(True)
                titles(self.db, 'demo', 'chat-000', 'Changed collision target', 0)
                self.decide('chat-029', 'open')
                with closing(sqlite3.connect(self.db)) as conn:
                    conn.execute("UPDATE messages SET text='New text' WHERE source_id='demo' AND conversation_id='chat-029'")
                    conn.commit()
            return records
        with patch.object(title_batch, '_inventory', mutate):
            queue = self.queue([candidate], review_state_filter='deferred')
        self.assertTrue(changed)
        self.assertEqual(queue['ready_count'], 1)
        self.assertEqual(queue['items'][0]['review_state']['state'], 'deferred')
        self.assertEqual(queue['items'][0]['collisions']['existing_title_conversations'], ['chat-000'])
        self.assertEqual(self.queue([candidate], review_state_filter='deferred')['items'], [])
        self.assertEqual(self.queue([candidate])['items'][0]['reason_code'], 'SUPPLIED_PROPOSAL_STALE')

    def test_cli_subset_and_explicit_fresh_preview_apply_workflow(self):
        candidate = self.proposal(); path = self.save(candidate, 'proposal.json')
        before = self.db.read_bytes()
        queue = self.cli('review-titles', '--source', 'demo', '--proposal', path, '--supplied-only')
        self.assertEqual([i['conversation'] for i in queue['items']], ['chat-029'])
        self.assertEqual(before, self.db.read_bytes())
        self.cli('review-titles', '--source', 'demo', '--supplied-only', success=False)
        saved = self.save(queue, 'queue.json')
        self.cli('apply-title', saved, success=False)
        reviewed = self.cli('preview-title', saved, '--conversation', 'chat-029')
        self.assertEqual(before, self.db.read_bytes())
        self.cli('apply-title', self.save(reviewed, 'reviewed.json'))
        self.assertEqual(titles(self.db, 'demo', 'chat-029')['display_title'], candidate['title'])
        self.assertEqual(titles(self.db, 'demo', 'chat-000')['revision'], 0)
        filtered = self.cli('review-titles', '--source', 'demo', '--proposal', path, '--supplied-only', '--unrenamed-only')
        self.assertEqual(filtered['items'], [])

    def test_sparse_keyset_scan_advances_by_identity_without_growing_offsets(self):
        ids = [f'item-{i:03}' for i in range(211)]
        # With the existing thirty chat IDs, these are exact chunk boundaries.
        ids[69] += "'quoted"
        ids[169] += '-é-한글'
        self.add_records('demo', ids)
        selected = [ids[69], ids[169], ids[-1]]
        candidates = [self.proposal(cid, title='Original chat-000') for cid in reversed(selected)]
        for cid in selected: self.decide(cid, 'deferred')
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            expected = [r[0] for r in conn.execute(
                "SELECT DISTINCT conversation_id FROM messages WHERE source_id='demo' ORDER BY conversation_id COLLATE BINARY")]
        original_inventory = title_batch._inventory
        original_readonly = title_batch.readonly
        scans = []; queries = []; mutated = []
        def traced(db):
            conn = original_readonly(db); conn.set_trace_callback(queries.append); return conn
        def scan(connection, *args, **kwargs):
            rows = original_inventory(connection, *args, **kwargs)
            scans.append((dict(kwargs), [row['conversation'] for row in rows]))
            if not mutated:
                mutated.append(True)
                # Changes after the first metadata chunk must not affect later chunks.
                self.decide(selected[-1], 'open')
                titles(self.db, 'demo', 'chat-000', 'Changed collision title', 0)
                with closing(sqlite3.connect(self.db)) as writer:
                    writer.execute("UPDATE messages SET text='Later synthetic text' WHERE source_id='demo' AND conversation_id=?", (selected[-1],))
                    writer.commit()
            return rows
        with patch.object(title_batch, 'readonly', traced), patch.object(title_batch, '_inventory', scan):
            queue = self.queue(candidates, review_state_filter='deferred', limit=2, offset=1)
        self.counts(queue, 3, 0, 238, 0)
        self.assertEqual([i['conversation'] for i in queue['items']], selected[1:])
        self.assertEqual(queue['ready_count'], 2)
        self.assertEqual(queue['supplied_proposals']['on_page'], 2)
        self.assertIsNone(queue['next_offset'])
        for item in queue['items']:
            self.assertEqual(item['review_state']['state'], 'deferred')
            self.assertEqual(item['collisions']['existing_title_conversations'], ['chat-000'])
        self.assertGreaterEqual(len(scans), 3)
        self.assertEqual([cid for _, rows in scans for cid in rows], expected)
        previous = None
        for kwargs, rows in scans:
            self.assertEqual(kwargs.get('offset', 0), 0)
            self.assertEqual(kwargs.get('after_conversation'), previous)
            if rows:
                if previous is not None: self.assertGreater(rows[0], previous)
                previous = rows[-1]
        self.assertEqual(scans[1][0]['after_conversation'], selected[0])
        self.assertEqual(scans[2][0]['after_conversation'], selected[1])
        body_queries = [q for q in queries if q.lstrip().upper().startswith('SELECT MESSAGE_ID,ROLE,TEXT')]
        self.assertTrue(body_queries)
        for query in body_queries:
            self.assertTrue(any("conversation_id='"+cid.replace("'", "''")+"'" in query for cid in selected), query)
        current = self.queue(candidates, review_state_filter='deferred')
        self.assertEqual([i['conversation'] for i in current['items']], selected[:2])


if __name__ == '__main__': unittest.main()
