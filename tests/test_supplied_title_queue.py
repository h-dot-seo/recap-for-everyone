"""Synthetic supplied-candidate review queues; never contact a model or private source."""
import copy
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

from recaplib.attributed_title import suggest_attributed
from recaplib.branch_title import suggest_branch
from recap import ingest
from recaplib.session_workflow import import_export, titles
from recaplib.title_batch import load_supplied_proposals, review_queue, select_proposal
from recaplib.title_proposal import apply_preview, preview, snapshot
from recaplib.title_review_state import review_state_from_queue


def documented_arguments(line, scratch):
    # Parse the published relative-path command first. Substituting Windows
    # paths before POSIX shlex parsing would consume backslashes and spaces.
    return [part.replace('../recap-supplied-demo', str(scratch)) for part in shlex.split(line)]


class SuppliedTitleQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root / 'archive.sqlite'
        records = [dict(conversation_id=cid, message_id=cid+'-u', role='user',
                        timestamp='synthetic', text='Raw '+cid+' request', title=title)
                   for cid, title in [('a', 'Old A'), ('b', 'Old B'), ('c', 'Shared title')]]
        path = self.root / 'input.jsonl'
        path.write_text(''.join(json.dumps(row)+'\n' for row in records), encoding='utf-8')
        ingest(self.db, 'mixed', path)

    def proposal(self, cid='a', **changes):
        value = dict(source='mixed', conversation=cid, content_sha256=snapshot(self.db, 'mixed', cid)[1],
                     title='Supplied '+cid, evidence_message_ids=[cid+'-u'], provider='operator')
        value.update(changes); return value

    def queue(self, proposals, **kwargs):
        return review_queue(self.db, 'mixed', supplied_proposals=proposals, **kwargs)

    def save(self, value, name='proposal.json'):
        path = self.root / name; path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8'); return path

    def cli(self, *args, success=True, db=None, ascii_only=False):
        env = dict(os.environ)
        if ascii_only: env['PYTHONIOENCODING'] = 'ascii'
        result = subprocess.run([sys.executable, 'recap.py', '--db', str(db or self.db), *map(str, args)],
                                capture_output=True, env=env, timeout=20)
        self.assertEqual(result.returncode, 0 if success else 1, result.stderr.decode('utf-8', errors='replace'))
        self.assertNotIn(b'Traceback', result.stderr)
        return json.loads(result.stdout) if success else result

    def test_default_none_preserves_shape_and_raw_excerpt_behavior(self):
        plain = review_queue(self.db, 'mixed')
        self.assertEqual(plain, self.queue(None))
        self.assertNotIn('proposal_mode', plain); self.assertNotIn('supplied_proposals', plain)
        self.assertEqual(plain['items'][0]['proposal']['title'], 'Raw a request')
        empty = self.queue([])
        self.assertEqual(empty['ready_count'], 0)
        self.assertTrue(all(i['reason_code'] == 'NO_SUPPLIED_PROPOSAL' for i in empty['items']))

    def test_provider_labels_metadata_deepcopy_and_no_writes(self):
        for provider in ('operator', 'synthetic-mock', 'external-adapter', 'local-extractive'):
            with self.subTest(provider=provider):
                candidate = self.proposal(provider=provider, private_context={'nested': ['Synthetic private note']})
                before = self.db.read_bytes()
                with patch('recaplib.title_batch.excerpt', side_effect=AssertionError('no fallback')):
                    queue = self.queue([candidate])
                self.assertEqual(self.db.read_bytes(), before)
                self.assertEqual(queue['items'][0]['proposal'], candidate)
                self.assertEqual(queue['execution_status'], 'NOT_EXECUTED')
                self.assertFalse(queue['remote_mutation']); self.assertEqual(queue['semantic_validation'], 'NOT_PERFORMED')
                self.assertIn('PRIVATE', queue['warning']); self.assertIn('unsigned', queue['warning'])
                queue['items'][0]['proposal']['private_context']['nested'].append('Changed')
                self.assertEqual(candidate['private_context']['nested'], ['Synthetic private note'])

    def test_missing_stale_and_invalid_are_unavailable_without_fallback(self):
        stale = self.proposal('a', content_sha256='0'*64)
        invalid = self.proposal('b', evidence_message_ids=['a-u'])
        with patch('recaplib.title_batch.excerpt', side_effect=AssertionError('no fallback')):
            queue = self.queue([stale, invalid])
        self.assertEqual([i['reason_code'] for i in queue['items']],
                         ['SUPPLIED_PROPOSAL_STALE', 'SUPPLIED_PROPOSAL_INVALID', 'NO_SUPPLIED_PROPOSAL'])
        self.assertTrue(all('proposal' not in i and 'collisions' not in i for i in queue['items']))
        for changes in ({'title': ''}, {'provider': 'unverified-model'}, {'evidence_message_ids': []},
                        {'evidence_message_ids': [False]}, {'title': []}, {'provider': {}}):
            with self.subTest(changes=changes):
                self.assertEqual(self.queue([self.proposal(**changes)])['items'][0]['reason_code'], 'SUPPLIED_PROPOSAL_INVALID')
        missing_title = self.proposal(); del missing_title['title']
        self.assertEqual(self.queue([missing_title])['items'][0]['reason_code'], 'SUPPLIED_PROPOSAL_INVALID')

    def test_identity_shape_duplicate_source_and_count_reject_before_database(self):
        valid = self.proposal()
        bad_values = [(), {}, [None], [1], [dict(valid, source='other')], [dict(valid, source=[])],
                      [dict(valid, conversation='')], [dict(valid, conversation=1)], [dict(valid, conversation=None)],
                      [valid, copy.deepcopy(valid)], [valid]*1001,
                      [dict(valid, extra=float('nan'))], [dict(valid, extra='x'*(1024*1024))]]
        with patch('recaplib.title_batch.readonly', side_effect=AssertionError('must reject before DB')):
            for bad in bad_values:
                with self.subTest(value=str(bad)[:80]), self.assertRaises(ValueError):
                    self.queue(bad)

    def test_page_counts_and_off_page_invalid_candidate_deferred(self):
        candidates = [self.proposal(), self.proposal('b', title=''),
                      dict(source='mixed', conversation='not-imported', arbitrary='unvalidated')]
        first = self.queue(candidates, limit=1)
        self.assertEqual(first['proposal_mode'], 'supplied')
        self.assertEqual({k:first['supplied_proposals'][k] for k in ('total', 'on_page', 'not_on_page')},
                         dict(total=3, on_page=1, not_on_page=2))
        self.assertEqual(first['items'][0]['status'], 'READY')
        second = self.queue(candidates, limit=1, offset=1)
        self.assertEqual(second['items'][0]['reason_code'], 'SUPPLIED_PROPOSAL_INVALID')
        last = self.queue(candidates, offset=99)
        self.assertEqual(last['items'], []); self.assertEqual(last['supplied_proposals']['not_on_page'], 3)

    def test_state_and_unrenamed_filters_keep_supplied_selection_and_counts(self):
        candidates = [self.proposal(cid) for cid in 'abc']
        titles(self.db, 'mixed', 'a', 'Reviewed A', 0)
        queue = self.queue(candidates)
        review_state_from_queue(self.db, 'mixed', 'b', 'deferred', queue)
        before = self.db.read_bytes()
        filtered = self.queue(candidates, unrenamed_only=True, review_state_filter='deferred')
        self.assertEqual([i['conversation'] for i in filtered['items']], ['b'])
        self.assertEqual(filtered['items'][0]['review_state']['state'], 'deferred')
        self.assertEqual(filtered['excluded_renamed_conversations'], 1)
        self.assertEqual(filtered['excluded_review_state_conversations'], 1)
        self.assertEqual(filtered['supplied_proposals']['not_on_page'], 2)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(queue['items'][0]['current_title'], 'Reviewed A')
        self.assertGreater(queue['items'][0]['current_revision'], 0)

    def test_supplied_collisions_use_titles_not_raw_excerpts(self):
        queue = self.queue([self.proposal('a', title='Shared title'), self.proposal('b', title='Ｓｈａｒｅｄ  TITLE')])
        for item in queue['items'][:2]:
            self.assertEqual(item['collisions']['page_proposal_count'], 1)
            self.assertEqual(item['collisions']['existing_title_conversations'], ['c'])
        one = self.queue([self.proposal('a', title='Shared title')], limit=1)
        self.assertEqual(one['items'][0]['collisions']['page_proposal_count'], 0)
        unchanged = self.queue([self.proposal('c', title='Shared title')])['items'][2]
        self.assertEqual(unchanged['action'], 'no_change'); self.assertEqual(unchanged['collisions']['existing_title_count'], 0)

    def test_concurrent_metadata_change_uses_single_read_snapshot(self):
        from recaplib import title_batch
        with closing(sqlite3.connect(self.db)) as conn: conn.execute('PRAGMA journal_mode=WAL')
        original = title_batch._inventory
        candidate = self.proposal(title='Shared title')
        def change(connection, *args, **kwargs):
            rows = original(connection, *args, **kwargs)
            titles(self.db, 'mixed', 'c', 'Changed C', 0)
            return rows
        with patch.object(title_batch, '_inventory', change):
            queue = self.queue([candidate])
        self.assertEqual(queue['items'][0]['collisions']['existing_title_conversations'], ['c'])
        self.assertEqual(queue['items'][2]['current_title'], 'Shared title')
        self.assertEqual(self.queue([candidate])['items'][0]['collisions']['existing_title_count'], 0)

    def test_loader_reads_each_explicit_file_once_and_never_discovers_wildcards(self):
        first = self.save(self.proposal()); second = self.save(self.proposal('b'), 'second.json')
        original = Path.open; opened = []
        def tracking(path, *args, **kwargs):
            opened.append(path); return original(path, *args, **kwargs)
        with patch.object(Path, 'open', tracking):
            result = load_supplied_proposals([first, second])
        self.assertEqual(opened, [first, second]); self.assertEqual(len(result), 2)
        self.assertEqual(load_supplied_proposals([]), [])
        with self.assertRaises(OSError): load_supplied_proposals([self.root/'*.json'])

    def test_loader_strict_json_types_encoding_and_combined_bounds(self):
        bad = self.root/'bad.json'
        for content in (b'[]', b'null', b'1', b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}', b'{}{}', b'\xff', b'{"a":"\\ud800"}'):
            with self.subTest(content=content):
                bad.write_bytes(content)
                with self.assertRaises(ValueError): load_supplied_proposals([bad])
        with patch.object(Path, 'open', side_effect=AssertionError('must count first')):
            with self.assertRaises(ValueError): load_supplied_proposals([bad]*1001)
        # Boundary is measured across raw files, including whitespace.
        first = self.root/'large-one.json'; second = self.root/'large-two.json'
        first.write_bytes(b'{}'+b' '*(524288-2)); second.write_bytes(first.read_bytes())
        self.assertEqual(load_supplied_proposals([first, second]), [{}, {}])
        second.write_bytes(second.read_bytes()+b' ')
        with self.assertRaises(ValueError): load_supplied_proposals([first, second])

    def test_cli_repeat_files_ascii_and_clean_errors_are_read_only(self):
        first = self.save(self.proposal(title='합성 과수원 계획')); second = self.save(self.proposal('b'), 'second.json')
        before = self.db.read_bytes()
        queue = self.cli('review-titles', '--source', 'mixed', '--proposal', first, '--proposal', second, ascii_only=True)
        self.assertEqual(queue['items'][0]['proposal']['title'], '합성 과수원 계획')
        self.assertEqual(queue['ready_count'], 2)
        for args in (('--proposal', first, '--proposal', first), ('--proposal', self.root/'missing.json')):
            self.cli('review-titles', '--source', 'mixed', *args, success=False)
        bad = self.root/'bad.json'; bad.write_text('[]')
        self.cli('review-titles', '--source', 'mixed', '--proposal', bad, success=False)
        self.assertEqual(before, self.db.read_bytes())

    def test_saved_queue_still_requires_one_fresh_strict_preview_then_apply(self):
        queue = self.queue([self.proposal(), self.proposal('b')]); path = self.save(queue, 'queue.json')
        self.cli('apply-title', path, success=False)
        reviewed = self.cli('preview-title', path, '--conversation', 'a')
        path = self.save(reviewed, 'reviewed.json'); self.cli('apply-title', path)
        self.assertEqual(titles(self.db, 'mixed', 'a')['display_title'], 'Supplied a')
        self.assertEqual(titles(self.db, 'mixed', 'b')['revision'], 0)
        self.cli('apply-title', path, success=False)
        tampered = copy.deepcopy(queue); tampered['items'][1]['proposal']['evidence_message_ids'] = ['a-u']
        path = self.save(tampered, 'tampered.json')
        self.cli('preview-title', path, '--conversation', 'b', success=False)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE messages SET text='Changed' WHERE conversation_id='b'"); conn.commit()
        with self.assertRaises(ValueError): preview(self.db, select_proposal(queue, 'b'))

    def test_branch_alternate_and_excluded_attribution_content_bind_full_snapshot(self):
        db = self.root/'contexts.sqlite'; web = self.root/'branches.json'
        def node(parent, text):
            return dict(parent=parent, message=dict(author=dict(role='user'), content=dict(parts=[text])))
        data = [dict(id='branched', title='Old', current_node='selected', mapping={
            'root': dict(parent=None), 'selected': node('root', 'Selected orchard'),
            'alternate': node('root', 'Abandoned orchard')})]
        web.write_text(json.dumps(data), encoding='utf-8')
        local = Path('examples/source-attributed-session.jsonl')
        import_export(db, 'mixed', web, 'web'); import_export(db, 'mixed', local, 'local-codex')
        branch = suggest_branch(db, 'mixed', 'branched', web)
        attributed = suggest_attributed(db, 'mixed', 'synthetic-attributed', local)
        queue = review_queue(db, 'mixed', supplied_proposals=[branch, attributed])
        self.assertEqual(queue['ready_count'], 2)
        self.assertEqual(branch['evidence_message_ids'], ['selected'])
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("UPDATE messages SET text='Changed off-branch text' WHERE conversation_id='branched' AND message_id='alternate'")
            conn.execute("UPDATE messages SET text=replace(text,'Synthetic environment setup instructions','Changed excluded setup') WHERE conversation_id='synthetic-attributed' AND message_id='synthetic-u1'")
            self.assertEqual(conn.total_changes, 2); conn.commit()
        stale = review_queue(db, 'mixed', supplied_proposals=[branch, attributed])
        self.assertTrue(all(item['reason_code'] == 'SUPPLIED_PROPOSAL_STALE' for item in stale['items']))
        for candidate in (branch, attributed):
            with self.assertRaises(ValueError): preview(db, candidate)

    def test_content_change_after_inventory_does_not_mix_snapshot_validation(self):
        from recaplib import title_batch
        with closing(sqlite3.connect(self.db)) as conn: conn.execute('PRAGMA journal_mode=WAL')
        candidate = self.proposal(); original = title_batch._inventory
        def change(connection, *args, **kwargs):
            result = original(connection, *args, **kwargs)
            with closing(sqlite3.connect(self.db)) as conn:
                conn.execute("UPDATE messages SET text='Later content' WHERE conversation_id='a'"); conn.commit()
            return result
        with patch.object(title_batch, '_inventory', change):
            queue = self.queue([candidate])
        self.assertEqual(queue['items'][0]['status'], 'READY')
        self.assertEqual(queue['items'][0]['review_state']['expected_content_sha256'], candidate['content_sha256'])
        self.assertEqual(self.queue([candidate])['items'][0]['reason_code'], 'SUPPLIED_PROPOSAL_STALE')

    def test_documented_path_substitution_preserves_windows_separators_and_spaces(self):
        for scratch in (r'C:\Synthetic Work\review', '/tmp/synthetic review'):
            with self.subTest(scratch=scratch):
                self.assertEqual(documented_arguments('mkdir ../recap-supplied-demo', scratch),
                                 ['mkdir', scratch])
                args = documented_arguments('python recap.py --db ../recap-supplied-demo/archive.sqlite '
                    'find "lunar calendar" > ../recap-supplied-demo/result.json', scratch)
                self.assertEqual(args[3], scratch + '/archive.sqlite')
                self.assertEqual(args[5], 'lunar calendar')
                self.assertEqual(args[-1], scratch + '/result.json')

    def test_documented_supplied_workflow_exact_commands_and_explicit_review(self):
        document = Path('docs/SUPPLIED_TITLE_REVIEW.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', document, re.S)
        self.assertEqual(len(blocks), 3)
        scratch = self.root/'documented-demo'
        originals = {path: Path(path).read_bytes() for path in
                     ('examples/web-export.json', 'examples/source-attributed-session.jsonl')}
        review_checked = False; applied = False
        for line in '\n'.join(blocks).splitlines():
            if not line.strip(): continue
            args = documented_arguments(line, scratch)
            if args[0] == 'mkdir':
                self.assertEqual(args, ['mkdir', str(scratch)]); scratch.mkdir(); continue
            self.assertEqual(args[:2], ['python', 'recap.py'])
            args[0] = sys.executable
            target = None
            self.assertNotIn('>', args)
            if '--output' in args:
                position = args.index('--output'); self.assertEqual(len(args), position+2)
                target = Path(args[position+1])
                self.assertFalse(target.exists())
            if 'apply-title' in args:
                reviewed = json.loads((scratch/'reviewed.json').read_text(encoding='utf-8'))
                self.assertEqual(reviewed['proposal']['source'], 'demo')
                self.assertEqual(reviewed['proposal']['conversation'], 'synthetic-attributed')
                self.assertEqual(reviewed['proposal']['title'], 'Design a synthetic lunar calendar')
                self.assertEqual(reviewed['previous_title'], '')
                self.assertEqual(reviewed['expected_revision'], 0)
                self.assertEqual(titles(scratch/'archive.sqlite', 'demo', 'synthetic-chat')['revision'], 0)
                self.assertEqual(titles(scratch/'archive.sqlite', 'demo', 'synthetic-attributed')['revision'], 0)
                review_checked = True
            result = subprocess.run(args, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            if target is not None:
                self.assertEqual(value['schema'], 'recap.saved-title-json.v1')
                self.assertEqual(value['status'], 'SAVED')
                raw = target.read_bytes()
                self.assertEqual(value['bytes'], len(raw))
                self.assertEqual(value['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertTrue(value['staging_cleanup_complete'])
                self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
                value = json.loads(raw)
            if 'review-titles' in args:
                self.assertEqual(value['ready_count'], 2)
                local = select_proposal(value, 'synthetic-attributed')
                self.assertEqual(local['attribution_context']['evidence_parts'][0]['content_indices'], [2])
            if 'apply-title' in args:
                self.assertTrue(review_checked); applied = True
                self.assertEqual(value['display_title'], 'Design a synthetic lunar calendar')
            if 'find' in args:
                self.assertTrue(applied); self.assertGreaterEqual(value['total_matches'], 1)
        self.assertTrue(review_checked); self.assertTrue(applied)
        self.assertEqual(titles(scratch/'archive.sqlite', 'demo', 'synthetic-chat')['revision'], 0)
        for path, before in originals.items(): self.assertEqual(Path(path).read_bytes(), before)

    def test_actual_mixed_web_and_attributed_examples_preserve_verified_context(self):
        db = self.root/'examples.sqlite'
        web = Path('examples/web-export.json'); local = Path('examples/source-attributed-session.jsonl')
        import_export(db, 'mixed', web, 'web'); import_export(db, 'mixed', local, 'local-codex')
        with closing(sqlite3.connect(db)) as conn:
            ids = [r[0] for r in conn.execute('SELECT DISTINCT conversation_id FROM messages')]
        web_id = 'synthetic-chat'; local_id = next(cid for cid in ids if cid != web_id)
        branch = suggest_branch(db, 'mixed', web_id, web, 'm2')
        attributed = suggest_attributed(db, 'mixed', local_id, local)
        before = db.read_bytes()
        paths = [self.save(branch, 'branch.json'), self.save(attributed, 'attributed.json')]
        queue = self.cli('review-titles', '--source', 'mixed', '--proposal', paths[0], '--proposal', paths[1], db=db)
        self.assertEqual(queue['ready_count'], 2); self.assertEqual(before, db.read_bytes())
        for proposal in (branch, attributed):
            selected = select_proposal(queue, proposal['conversation'])
            self.assertEqual(selected, proposal)
            self.assertEqual(selected['content_sha256'], snapshot(db, 'mixed', proposal['conversation'])[1])
        self.assertEqual(attributed['attribution_context']['original_sha256'], hashlib.sha256(local.read_bytes()).hexdigest())
        self.assertFalse(attributed['attribution_context']['producer_attribution_authenticated'])
        self.assertIn('branch_context', select_proposal(queue, web_id))
        # Even an excluded/non-evidence row belongs to the fingerprint contract.
        with closing(sqlite3.connect(db)) as conn:
            conn.execute("UPDATE messages SET text=text||' changed' WHERE source_id='mixed' AND conversation_id=? AND message_id NOT IN (%s)" % ','.join('?' for _ in branch['evidence_message_ids']), [web_id]+branch['evidence_message_ids'])
            self.assertGreater(conn.total_changes, 0); conn.commit()
        stale = review_queue(db, 'mixed', supplied_proposals=[branch, attributed])
        web_item = next(i for i in stale['items'] if i['conversation'] == web_id)
        self.assertEqual(web_item['reason_code'], 'SUPPLIED_PROPOSAL_STALE')
        apply_preview(db, preview(db, select_proposal(queue, local_id)))
        self.assertEqual(titles(db, 'mixed', web_id)['revision'], 0)


if __name__ == '__main__':
    unittest.main()
