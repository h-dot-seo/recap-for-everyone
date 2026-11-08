"""Synthetic, offline tests for private no-overwrite title JSON publication."""
import errno
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from recaplib import title_document_output as output
from recap import ingest
from recaplib.session_workflow import import_export
from tests.test_branch_title import fixture as branch_fixture
from tests.test_replay_local import turn


class TitleDocumentOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.destination = self.root / 'private-target.json'
        self.document = dict(title='합성 과수원 🌱', source='private-source-label',
                             body='private synthetic body', nested={'values': [None, True, 3]})

    def stages(self):
        return list(self.root.glob('.recap-title-*'))

    def test_utf8_shape_hash_newline_private_mode_and_metadata_only_receipt(self):
        for kind in ('proposal', 'preview', 'queue'):
            with self.subTest(kind=kind):
                path = self.root / (kind + '.json')
                receipt = output.write_title_json(self.document, path, kind)
                raw = path.read_bytes()
                self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
                self.assertTrue(raw.endswith(b'\n')); self.assertFalse(raw.endswith(b'\n\n'))
                self.assertIn('합성 과수원 🌱'.encode('utf-8'), raw)
                self.assertEqual(json.loads(raw), self.document)
                self.assertEqual(receipt['schema'], 'recap.saved-title-json.v1')
                self.assertEqual(receipt['status'], 'SAVED'); self.assertEqual(receipt['document_kind'], kind)
                self.assertEqual(receipt['bytes'], len(raw))
                self.assertEqual(receipt['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertTrue(receipt['staging_cleanup_complete'])
                self.assertIsNone(receipt['remaining_staging_file'])
                rendered = json.dumps(receipt, ensure_ascii=False)
                for secret in (self.document['title'], self.document['body'], self.document['source'], str(path)):
                    self.assertNotIn(secret, rendered)
                if os.name == 'posix':
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(self.stages(), [])

    def test_invalid_serialization_rejects_before_any_staging(self):
        cycle = {}; cycle['cycle'] = cycle
        cases = [(None, 'proposal'), ([], 'proposal'), ({}, 'invalid'),
                 ({'x': object()}, 'proposal'), ({'x': {1}}, 'proposal'),
                 ({'x': float('nan')}, 'proposal'), ({'x': float('inf')}, 'proposal'),
                 ({'x': -float('inf')}, 'proposal'), ({'x': '\ud800'}, 'proposal'),
                 ({'\udfff': 'x'}, 'proposal'), (cycle, 'proposal')]
        with patch.object(output.tempfile, 'NamedTemporaryFile', side_effect=AssertionError('must not stage')):
            for value, kind in cases:
                with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                    output.write_title_json(value, self.destination, kind)
        self.assertFalse(self.destination.exists()); self.assertEqual(self.stages(), [])

    def test_existing_file_directory_symlink_dangling_symlink_never_overwritten(self):
        original = self.root / 'original'; original.write_bytes(b'KEEP ORIGINAL')
        existing = self.root / 'existing'; existing.write_bytes(b'KEEP EXISTING')
        directory = self.root / 'directory'; directory.mkdir()
        candidates = [existing, directory]
        if hasattr(os, 'symlink'):
            for name, target in [('link', original), ('dangling', self.root / 'absent')]:
                link = self.root / name
                try: link.symlink_to(target)
                except OSError: continue
                candidates.append(link)
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(OSError):
                output.write_title_json(self.document, candidate, 'proposal')
            self.assertEqual(self.stages(), [])
        self.assertEqual(original.read_bytes(), b'KEEP ORIGINAL')
        self.assertEqual(existing.read_bytes(), b'KEEP EXISTING'); self.assertTrue(directory.is_dir())
        self.assertFalse((self.root / 'absent').exists())
        for candidate in candidates[2:]: self.assertTrue(candidate.is_symlink())

    def test_simultaneous_writers_publish_exactly_one_complete_document(self):
        barrier = threading.Barrier(2)
        def attempt(number):
            value = dict(self.document, writer=number)
            barrier.wait(timeout=10)
            try: return ('saved', number, output.write_title_json(value, self.destination, 'proposal'))
            except FileExistsError: return ('exists', number, None)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, range(2)))
        self.assertEqual(sorted(row[0] for row in results), ['exists', 'saved'])
        winner = next(row for row in results if row[0] == 'saved')
        self.assertEqual(json.loads(self.destination.read_bytes()), dict(self.document, writer=winner[1]))
        self.assertEqual(self.stages(), [])

    def test_missing_parent_is_not_created(self):
        path = self.root / 'missing' / 'output.json'
        with self.assertRaises(FileNotFoundError): output.write_title_json(self.document, path, 'proposal')
        self.assertFalse(path.parent.exists()); self.assertEqual(self.stages(), [])

    def test_write_flush_fsync_and_link_failures_leave_no_output_or_stage(self):
        factory = output.tempfile.NamedTemporaryFile
        for phase in ('write', 'flush', 'fsync', 'link'):
            with self.subTest(phase=phase):
                def staged(*args, **kwargs):
                    stream = factory(*args, **kwargs)
                    setattr(stream, phase, lambda *a, **k: (_ for _ in ()).throw(OSError('injected ' + phase)))
                    return stream
                if phase in ('write', 'flush'):
                    context = patch.object(output.tempfile, 'NamedTemporaryFile', side_effect=staged)
                else:
                    context = patch.object(output.os, phase, side_effect=OSError(errno.ENOTSUP, 'injected ' + phase))
                with context, \
                     patch.object(output.os, 'replace', side_effect=AssertionError('no replacement fallback')), \
                     patch.object(output.os, 'rename', side_effect=AssertionError('no rename fallback')), \
                     self.assertRaises(OSError):
                    output.write_title_json(self.document, self.destination, 'proposal')
                self.assertFalse(self.destination.exists()); self.assertEqual(self.stages(), [])

    def test_short_write_is_rejected_and_stage_removed(self):
        factory = output.tempfile.NamedTemporaryFile
        def staged(*args, **kwargs):
            stream = factory(*args, **kwargs)
            stream.write = lambda raw: len(raw) - 1
            return stream
        with patch.object(output.tempfile, 'NamedTemporaryFile', side_effect=staged), \
             patch.object(output.os, 'link', side_effect=AssertionError('must not publish')), \
             self.assertRaises(OSError):
            output.write_title_json(self.document, self.destination, 'proposal')
        self.assertFalse(self.destination.exists()); self.assertEqual(self.stages(), [])

    def test_closed_private_same_parent_stage_and_no_replace_fallback(self):
        actual_link = output.os.link
        factory = output.tempfile.NamedTemporaryFile; streams = []
        nested = self.root / 'nested'; nested.mkdir()
        # A lexical alias exercises the identity check on every OS. Windows
        # TemporaryDirectory can independently use an 8.3 parent alias.
        destinations = [self.destination, nested / '..' / 'aliased-target.json']
        def staged(*args, **kwargs):
            stream = factory(*args, **kwargs); streams.append(stream); return stream
        def checked_link(source, destination):
            self.assertTrue(streams[-1].closed)
            self.assertTrue(Path(source).parent.samefile(expected.parent))
            self.assertTrue(Path(destination).parent.samefile(expected.parent))
            self.assertEqual(Path(destination).name, expected.name)
            if os.name == 'posix': self.assertEqual(stat.S_IMODE(Path(source).stat().st_mode), 0o600)
            return actual_link(source, destination)
        for expected in destinations:
            with self.subTest(destination=expected), \
                 patch.object(output.tempfile, 'NamedTemporaryFile', side_effect=staged), \
                 patch.object(output.os, 'link', side_effect=checked_link), \
                 patch.object(output.os, 'replace', side_effect=AssertionError('must never replace')), \
                 patch.object(output.os, 'rename', side_effect=AssertionError('must never rename')):
                output.write_title_json(self.document, expected, 'proposal')
            self.assertEqual(json.loads(expected.read_bytes()), self.document)
            self.assertEqual(self.stages(), [])

    def test_post_publication_cleanup_failure_reports_saved_and_private_leftover(self):
        unlink = Path.unlink
        def fail_stage(path, *args, **kwargs):
            if path.name.startswith('.recap-title-'): raise OSError('injected cleanup failure')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_stage):
            receipt = output.write_title_json(self.document, self.destination, 'preview')
        self.assertEqual(receipt['status'], 'SAVED'); self.assertFalse(receipt['staging_cleanup_complete'])
        self.assertEqual(len(self.stages()), 1)
        self.assertEqual(receipt['remaining_staging_file'], self.stages()[0].name)
        self.assertEqual(self.stages()[0].read_bytes(), self.destination.read_bytes())
        self.assertEqual(json.loads(self.destination.read_bytes()), self.document)
        self.assertNotIn(str(self.root), json.dumps(receipt))

    def test_before_publication_cleanup_failure_raises_without_output(self):
        with patch.object(output.os, 'link', side_effect=OSError('link failed')), \
             patch.object(Path, 'unlink', side_effect=OSError('cleanup failed')), \
             self.assertRaisesRegex(OSError, 'cleanup failed'):
            output.write_title_json(self.document, self.destination, 'proposal')
        self.assertFalse(self.destination.exists()); self.assertEqual(len(self.stages()), 1)
        if os.name == 'posix': self.assertEqual(stat.S_IMODE(self.stages()[0].stat().st_mode), 0o600)


class TitleDocumentOutputCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root / 'archive.sqlite'
        self.normalized = self.root / 'normalized.jsonl'
        rows = [dict(conversation_id='synthetic', message_id='u', role='user', timestamp='synthetic',
                     title='원래 제목', text='합성 과수원 계획 🌱')]
        self.normalized.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows), encoding='utf-8')
        ingest(self.db, 'demo', self.normalized)
        self.web = self.root / 'web.json'; self.web.write_text(json.dumps(branch_fixture()), encoding='utf-8')
        import_export(self.db, 'web', self.web, 'web')
        self.local = self.root / 'local.jsonl'
        records = [dict(type='session_meta', payload=dict(id='synthetic')), *turn('retained')]
        self.local.write_text(''.join(json.dumps(row)+'\n' for row in records), encoding='utf-8')
        import_export(self.db, 'local', self.local, 'local-codex')
        self.attributed = self.root / 'attributed.jsonl'
        for record in records:
            payload = record.get('payload', {})
            if payload.get('type') == 'message' and payload.get('role') == 'user':
                payload['internal_chat_message_metadata_passthrough'] = dict(content_item_metadata=[dict(provenance=dict(type='user'))])
        self.attributed.write_text(''.join(json.dumps(row)+'\n' for row in records), encoding='utf-8')
        import_export(self.db, 'attributed', self.attributed, 'local-codex')

    def call(self, *args, script='recap.py', success=True, db=None):
        result = subprocess.run([sys.executable, script, '--db', str(db or self.db), *map(str, args)],
                                capture_output=True, env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=30)
        self.assertEqual(result.returncode == 0, success, result.stderr.decode('ascii', errors='replace'))
        self.assertNotIn(b'Traceback', result.stderr)
        result.stdout.decode('ascii')
        return json.loads(result.stdout) if success else result

    def identity(self, source='demo'):
        return ('--source', source, '--conversation', 'synthetic')

    def test_all_suggestion_commands_and_standalones_preserve_old_shape(self):
        before = {path: path.read_bytes() for path in (self.db, self.normalized, self.web, self.local, self.attributed)}
        cases = [('suggest-title', 'title_suggestion.py', self.identity()),
                 ('suggest-title', 'title_suggestion.py', (*self.identity(), '--message', 'u')),
                 ('suggest-branch-title', 'branch_title.py', (self.web, *self.identity('web'))),
                 ('suggest-replay-title', 'replay_title.py', (self.local, *self.identity('local'))),
                 ('suggest-attributed-title', 'attributed_title.py', (self.attributed, *self.identity('attributed')))]
        for index, (command, script, args) in enumerate(cases):
            with self.subTest(command=command, index=index):
                plain = self.call(command, *args)
                self.assertEqual(plain, self.call(*args, script=script))
                for entry, prefix in [('unified', (command,)), ('standalone', ())]:
                    target = self.root / f'{index}-{entry}.json'
                    receipt = self.call(*prefix, *args, '--output', target, script='recap.py' if prefix else script)
                    self.assertEqual(json.loads(target.read_bytes()), plain)
                    self.assertEqual(receipt['schema'], 'recap.saved-title-json.v1')
                    self.assertNotIn(plain['title'], json.dumps(receipt, ensure_ascii=False))
                    self.assertNotIn(str(target), json.dumps(receipt))
        for path, raw in before.items(): self.assertEqual(path.read_bytes(), raw)

    def test_saved_proposal_queue_preview_standalone_parity_and_explicit_apply(self):
        before = self.db.read_bytes(); original = self.normalized.read_bytes()
        proposal = self.root / 'proposal.json'; queue = self.root / 'queue.json'; preview = self.root / 'preview.json'
        self.call('suggest-title', *self.identity(), '--message', 'u', '--output', proposal)
        args = ('review-titles', '--source', 'demo', '--proposal', proposal, '--supplied-only')
        plain_queue = self.call(*args)
        self.assertEqual(self.call(*args, '--output', queue)['document_kind'], 'queue')
        self.assertEqual(json.loads(queue.read_bytes()), plain_queue)
        args = ('preview-title', queue, '--conversation', 'synthetic', '--title', '검토한 제목 🌱', '--with-evidence')
        plain = self.call(*args)
        self.assertEqual(self.call(*args, '--output', preview)['document_kind'], 'preview')
        self.assertEqual(json.loads(preview.read_bytes()), plain)
        self.assertEqual(plain['proposal']['provider'], 'operator')
        self.assertIn('review_evidence', plain)
        standalone = self.root / 'standalone-preview.json'
        standalone_args = ('preview', proposal, '--title', '검토한 제목 🌱', '--with-evidence')
        self.assertEqual(self.call(*standalone_args, script='title_proposal.py'), plain)
        self.call(*standalone_args, '--output', standalone, script='title_proposal.py')
        self.assertEqual(json.loads(standalone.read_bytes()), plain)
        self.assertEqual(self.db.read_bytes(), before)
        applied = self.call('apply-title', preview)
        self.assertEqual(applied['display_title'], '검토한 제목 🌱')
        after = self.db.read_bytes()
        self.call('apply-title', preview, success=False)
        self.assertEqual(self.db.read_bytes(), after)
        self.assertEqual(self.normalized.read_bytes(), original)

    def test_unicode_space_hash_percent_paths_round_trip_and_refuse_existing(self):
        proposal = self.root / '합성 제안 #%.json'
        reviewed = self.root / '검토 결과 #%.json'
        before = self.db.read_bytes()
        self.call('suggest-title', *self.identity(), '--output', proposal)
        proposal_bytes = proposal.read_bytes()
        self.call('preview-title', proposal, '--output', reviewed)
        reviewed_bytes = reviewed.read_bytes()
        failed = self.call('preview-title', proposal, '--output', reviewed, success=False)
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(failed.stdout, b'')
        self.assertEqual(proposal.read_bytes(), proposal_bytes)
        self.assertEqual(reviewed.read_bytes(), reviewed_bytes)
        self.assertEqual(self.db.read_bytes(), before)
        result = self.call('apply-title', reviewed)
        self.assertEqual(result['display_title'], '합성 과수원 계획 🌱')
        self.assertEqual(proposal.read_bytes(), proposal_bytes)
        self.assertEqual(reviewed.read_bytes(), reviewed_bytes)

    def test_receipts_are_not_proposals_or_apply_authority(self):
        proposal = self.root / 'proposal.json'; reviewed = self.root / 'reviewed.json'
        proposal_receipt = self.call('suggest-title', *self.identity(), '--output', proposal)
        preview_receipt = self.call('preview-title', proposal, '--output', reviewed)
        before = self.db.read_bytes()
        for kind, receipt in [('proposal', proposal_receipt), ('preview', preview_receipt)]:
            path = self.root / (kind + '-receipt.json')
            path.write_text(json.dumps(receipt), encoding='utf-8')
            for command in ('preview-title', 'apply-title'):
                with self.subTest(kind=kind, command=command):
                    self.call(command, path, success=False)
        self.assertEqual(self.db.read_bytes(), before)

    def test_existing_input_database_hardlink_and_symlink_aliases_are_not_overwritten(self):
        before = {path: path.read_bytes() for path in (self.db, self.normalized, self.web)}
        targets = [self.db, self.normalized, self.web]
        for path in (self.db, self.web):
            alias = self.root / (path.name + '.hardlink'); os.link(path, alias); targets.append(alias)
            alias = self.root / (path.name + '.symlink')
            try: alias.symlink_to(path)
            except OSError: continue
            targets.append(alias)
        for target in targets:
            with self.subTest(target=target):
                self.call('suggest-branch-title', self.web, *self.identity('web'), '--output', target, success=False)
        for path, raw in before.items(): self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(list(self.root.glob('.recap-title-*')), [])

    def test_source_validation_and_missing_database_create_no_output(self):
        destination = self.root / 'must-not-exist.json'
        for command, path, source in [('suggest-branch-title', self.web, 'web'),
                                      ('suggest-replay-title', self.local, 'local'),
                                      ('suggest-attributed-title', self.attributed, 'attributed')]:
            with self.subTest(command=command):
                path.write_bytes(path.read_bytes() + b'\n')
                self.call(command, path, *self.identity(source), '--output', destination, success=False)
                self.assertFalse(destination.exists())
        missing = self.root / 'missing.sqlite'
        self.call('suggest-title', *self.identity(), '--output', destination, db=missing, success=False)
        self.assertFalse(missing.exists()); self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob('.recap-title-*')), [])

    def test_mutating_commands_and_adapter_reject_output_before_any_action(self):
        proposal = self.root / 'proposal.json'
        self.call('suggest-title', *self.identity(), '--output', proposal)
        preview = self.root / 'preview.json'; self.call('preview-title', proposal, '--output', preview)
        before = self.db.read_bytes(); destination = self.root / 'not-created.json'
        cases = [('title', *self.identity(), '--set', 'Do not apply', '--expected-revision', '0'),
                 ('apply-title', preview),
                 ('review-state', *self.identity(), '--set', 'skipped', '--expected-state-revision', '0'),
                 ('import', self.web, '--source', 'other', '--format', 'web'),
                 ('ingest', self.normalized, '--source', 'other'),
                 ('title-adapter-dry-run', 'missing', 'missing', 'missing'),
                 ('title-adapter-simulate', 'missing', 'missing', 'missing', 'missing')]
        for args in cases:
            with self.subTest(command=args[0]):
                result = self.call(*args, '--output', destination, success=False)
                self.assertEqual(result.returncode, 2); self.assertIn(b'unrecognized arguments: --output', result.stderr)
        result = self.call('apply', preview, '--output', destination, script='title_proposal.py', success=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.db.read_bytes(), before); self.assertFalse(destination.exists())

    def test_prepare_web_export_keeps_its_existing_output_semantics(self):
        archive = self.root / 'synthetic.zip'; destination = self.root / 'prepared.json'
        with zipfile.ZipFile(archive, 'w') as stream: stream.writestr('conversations.json', self.web.read_bytes())
        before = self.db.read_bytes()
        receipt = self.call('prepare-web-export', archive, '--member', 'conversations.json', '--output', destination)
        self.assertNotEqual(receipt.get('schema'), 'recap.saved-title-json.v1')
        self.assertEqual(receipt['prepared_sha256'], hashlib.sha256(self.web.read_bytes()).hexdigest())
        self.assertEqual(destination.read_bytes(), self.web.read_bytes()); self.assertEqual(self.db.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
