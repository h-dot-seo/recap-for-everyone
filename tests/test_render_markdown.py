"""Fictional Markdown views: fenced data, read-only selection and publication."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from recaplib.archive import ingest
from recaplib.conversation_view import conversation
from recaplib import render_view as render

ROOT = Path(__file__).resolve().parents[1]


class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        ingest(self.db, 'synthetic', ROOT / 'examples/render-adversarial.jsonl')
        self.output = self.root / 'view.md'

    def view(self, **kwargs):
        return conversation(self.db, 'synthetic', 'fictional', **kwargs)

    def save(self, **kwargs):
        return render.render_conversation(self.db, 'synthetic', 'fictional', self.output,
                                          format='markdown', **kwargs)

    def blocks(self, raw):
        """Check the restricted generated dialect, including CommonMark closers."""
        outside, blocks, content = [], [], []
        fence = None
        for line in raw.decode('utf-8').split('\n'):
            if fence is None:
                opening = re.fullmatch(r'(`{3,})text', line)
                if opening:
                    fence = opening.group(1)
                else:
                    outside.append(line)
            else:
                closing = re.fullmatch(r' {0,3}(`{3,})[ \t]*', line)
                if closing and len(closing.group(1)) >= len(fence):
                    self.assertEqual(line, fence)
                    body = '\n'.join(content)
                    self.assertGreater(len(fence), max((len(run) for run in re.findall(r'`+', body)), default=0))
                    blocks.append(body)
                    fence = None
                    content = []
                else:
                    content.append(line)
        self.assertIsNone(fence, 'unclosed generated fence')
        return '\n'.join(outside), blocks

    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, 'recap.py', *map(str, args)], cwd=ROOT,
                                capture_output=True, timeout=60,
                                env=dict(os.environ, PYTHONIOENCODING='ascii'))
        self.assertEqual(result.returncode, expected, result.stderr)
        result.stdout.decode('ascii')
        return result

    def test_hostile_body_has_fixed_headings_and_visible_controls(self):
        view = self.view(limit=1)
        body = ('Synthetic 합성 🧪\n```text\n## Forged\n   ````   \n~~~~~~~\n'
                '</pre><script>x</script><img src=x>\n![x](https://example.invalid)\n'
                '\x00\x1b\r\x7f\u202e\u2028\u2029\ud800\u200c\u200d')
        view['messages'][0]['text'] = body
        raw = render.render_markdown(view)
        outside, blocks = self.blocks(raw)
        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[-1], ''.join(render._plain_display_chunks(body)))
        self.assertNotIn('Forged', outside)
        self.assertNotIn('example.invalid', outside)
        self.assertIn('합성 🧪', blocks[-1])
        for escape in ('\\u0000', '\\u001b', '\\u000d', '\\u007f', '\\u202e', '\\u2028', '\\u2029', '\\ud800'):
            self.assertIn(escape, blocks[-1])
        self.assertIn('\u200c\u200d', blocks[-1])
        headings = [line for line in outside.splitlines() if line.startswith('#')]
        self.assertEqual(headings, ['# Local conversation view', '## View metadata',
                                   '## Message 1', '### Metadata', '### Body', '## Boundary'])
        self.assertEqual(outside.count('PRIVATE MESSAGE TEXT'), 2)
        self.assertIn('not all Markdown viewers are guaranteed safe', outside)

    def test_every_metadata_scalar_is_fenced_and_provenance_retained(self):
        view = self.view(limit=1)
        attack = 'Synthetic supplied\n## Forged\n' + '`' * 40 + '~~~<img src=x>![](x)\u202e'
        for key in ('source', 'conversation', 'original_title', 'display_title', 'revision',
                    'message_count', 'message_order', 'branch_scope', 'scope'):
            view[key] = attack
        view['selection'] = dict(mode=attack, warning=attack, next_offset=attack)
        message = view['messages'][0]
        for key in ('message_id', 'role', 'timestamp', 'original_title', 'source_sha256', 'source_line'):
            message[key] = attack
        message['export_provenance'] = [dict(original_sha256=attack, locator=attack, parent_id=attack)]
        raw = render.render_markdown(view)
        outside, blocks = self.blocks(raw)
        self.assertNotIn('supplied', outside.replace('exact supplied evidence', ''))
        self.assertNotIn('Forged', outside)
        metadata = json.loads(blocks[0])
        self.assertEqual(metadata['selection'], view['selection'])
        for key in view.keys() - {'messages'}:
            self.assertEqual(metadata[key], view[key])
        self.assertEqual(json.loads(blocks[1]), {k: v for k, v in message.items() if k != 'text'})
        self.assertIn('`' * 41 + 'text', raw.decode())

    def test_long_fences_cross_chunk_boundaries_and_empty_or_trailing_bodies(self):
        for body in ('', 'Fictional\n', '\n', '`' * 9000, 'x' * 4095 + '`' * 5000 + '\n~~~'):
            with self.subTest(length=len(body)):
                view = self.view(limit=1)
                view['messages'][0]['text'] = body
                _, blocks = self.blocks(render.render_markdown(view))
                self.assertEqual(blocks[-1], body)

    def test_all_selection_modes_determinism_hash_and_no_mutation(self):
        before = self.db.read_bytes()
        for kwargs in ({}, {'limit': 1, 'offset': 1}, {'message_id': 'one'},
                       {'around_message_id': 'two', 'before': 1, 'after': 0}, {'limit': 1, 'offset': 99}):
            with self.subTest(kwargs=kwargs):
                view = self.view(**kwargs)
                raw = render.render_markdown(view)
                self.assertEqual(raw, render.render_markdown(self.view(**kwargs)))
                outside, blocks = self.blocks(raw)
                metadata = json.loads(blocks[0])
                self.assertEqual(metadata['view_sha256'], render.view_sha256(view))
                self.assertEqual(metadata['format'], 'markdown')
                self.assertEqual(metadata['schema'], 'recap.render.v1')
                self.assertEqual({k: metadata[k] for k in view if k != 'messages'},
                                 {k: v for k, v in view.items() if k != 'messages'})
                self.assertEqual(len(blocks), 1 + 2 * len(view['messages']))
                for index, message in enumerate(view['messages']):
                    self.assertEqual(json.loads(blocks[1 + index * 2]),
                                     {k: v for k, v in message.items() if k != 'text'})
                self.assertEqual('Selection: full conversation;' in outside, not kwargs)
                self.assertNotIn(str(self.db), raw.decode())
        self.assertEqual(self.db.read_bytes(), before)

    def test_reads_once_and_receipt_does_not_disclose_supplied_values(self):
        view = self.view(limit=1)
        with patch.object(render, 'conversation', return_value=view) as read:
            receipt = self.save(limit=1)
        read.assert_called_once_with(self.db, 'synthetic', 'fictional', 1, 0, None, None, None, None)
        raw = self.output.read_bytes()
        self.assertEqual(receipt['schema'], 'recap.saved-view.v1')
        self.assertEqual(receipt['document_kind'], 'markdown')
        self.assertEqual(receipt['encoding'], 'UTF-8')
        self.assertEqual(receipt['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt['bytes'], len(raw))
        self.assertTrue(receipt['staging_cleanup_complete'])
        for private in (str(self.output), str(self.db), 'fictional', '합성 한국어', 'Synthetic timestamp'):
            self.assertNotIn(private, json.dumps(receipt, ensure_ascii=False))
        with self.assertRaises(FileExistsError): self.save()
        self.assertEqual(raw, self.output.read_bytes())
        self.assertEqual(list(self.root.glob('.recap-view-*')), [])

    def test_refuses_directory_missing_parent_and_symlinks(self):
        self.output.mkdir()
        with self.assertRaises(OSError): self.save()
        self.output.rmdir()
        with self.assertRaises(FileNotFoundError):
            render.render_conversation(self.db, 'synthetic', 'fictional', self.root / 'missing' / 'view.md', format='markdown')
        target = self.root / 'target'
        target.write_bytes(b'Fictional preserved bytes')
        try:
            self.output.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('symlink creation is unavailable')
        with self.assertRaises(FileExistsError): self.save()
        self.assertEqual(target.read_bytes(), b'Fictional preserved bytes')
        self.output.unlink()
        self.output.symlink_to(self.root / 'absent')
        with self.assertRaises(FileExistsError): self.save()
        self.assertFalse((self.root / 'absent').exists())
        self.assertEqual(list(self.root.glob('.recap-view-*')), [])

    def test_limit_is_encoded_bytes_and_counts_fences_before_publication(self):
        view = self.view(limit=1)
        view['messages'][0]['text'] = '합성 🧪' + '`' * 5000
        raw = render.render_markdown(view)
        with patch.object(render, 'MAX_OUTPUT_BYTES', len(raw)):
            self.assertEqual(raw, render.render_markdown(view))
        with patch.object(render, 'MAX_OUTPUT_BYTES', len(raw) - 1), self.assertRaises(ValueError):
            render.render_markdown(view)
        document = render._Document()
        with patch.object(render, 'MAX_OUTPUT_BYTES', 20), self.assertRaises(ValueError):
            render._markdown_value(document, '`' * 10)
        self.assertEqual(document.raw, b'')
        with patch.object(render, 'MAX_OUTPUT_BYTES', 100), self.assertRaisesRegex(ValueError, 'narrow the message selection'):
            self.save()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.recap-view-*')), [])

    def test_invalid_selection_and_format_do_not_publish(self):
        for kwargs in ({'limit': 0}, {'offset': 1}, {'message_id': 'missing'},
                       {'message_id': 'one', 'limit': 1}, {'before': 1},
                       {'around_message_id': 'one', 'after': 51}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.save(**kwargs)
        with patch.object(render, 'conversation') as read, self.assertRaisesRegex(ValueError, 'format'):
            render.render_conversation(self.db, 'synthetic', 'fictional', self.output, format='text')
        read.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.recap-view-*')), [])

    def test_cleanup_and_link_failure_match_existing_contract(self):
        unlink = Path.unlink
        def fail_stage(path, *args, **kwargs):
            if path.name.startswith('.recap-view-'): raise OSError('synthetic failure')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_stage): receipt = self.save()
        self.assertEqual(receipt['status'], 'SAVED')
        self.assertFalse(receipt['staging_cleanup_complete'])
        stage = self.root / receipt['remaining_staging_file']
        self.assertEqual(stage.read_bytes(), self.output.read_bytes())
        self.output.unlink(); stage.unlink()
        with patch('recaplib.document_output.os.link', side_effect=OSError('synthetic failure')), self.assertRaises(OSError):
            self.save()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.recap-view-*')), [])

    def test_html_bytes_and_show_stdout_remain_compatible(self):
        raw = render.render_html(self.view())
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '51e16d1e0ee8f73c19b08b1279a0dbe25e706223a42ec7039ba8a0f4b6f04416')
        result = self.cli('--db', self.db, 'show', '--source', 'synthetic', '--conversation', 'fictional')
        # show still uses the native text stream: CRLF on Windows, LF on POSIX.
        expected = (json.dumps(self.view(), ensure_ascii=True, indent=2) + '\n')
        self.assertEqual(result.stdout, expected.replace('\n', os.linesep).encode('ascii'))

    def test_show_stdout_preserves_json_with_explicit_lf_and_crlf_streams(self):
        before = self.db.read_bytes()
        view = self.view()
        expected = json.dumps(view, ensure_ascii=True, indent=2) + '\n'
        argv = ['recap.py', '--db', str(self.db), 'show', '--source', 'synthetic',
                '--conversation', 'fictional']
        for newline in ('\n', '\r\n'):
            with self.subTest(newline=repr(newline)):
                # Exercise real text-stream translation on every platform,
                # rather than changing production output or normalizing evidence.
                code = ('import runpy, sys; sys.stdout.reconfigure(newline=' + repr(newline) +
                        '); sys.argv = ' + repr(argv) +
                        '; runpy.run_path("recap.py", run_name="__main__")')
                result = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                                        capture_output=True, timeout=60,
                                        env=dict(os.environ, PYTHONIOENCODING='ascii'))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, b'')
                self.assertEqual(result.stdout, expected.replace('\n', newline).encode('ascii'))
                self.assertEqual(json.loads(result.stdout.decode('ascii')), view)
        self.assertEqual(self.db.read_bytes(), before)

    def test_documented_markdown_commands_ascii_receipts_and_rerun_refusal(self):
        guide = (ROOT / 'docs/RENDER_MARKDOWN.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', guide, re.S)
        self.assertEqual(len(blocks), 1)
        output = self.root / 'guide'; output.mkdir()
        before = None
        commands = []
        for line in blocks[0].strip().splitlines():
            tokens = shlex.split(line)
            self.assertEqual(tokens[:2], ['python', 'recap.py'])
            self.assertIn('OUTPUT', line)
            args = [t.replace('OUTPUT', str(output)) for t in tokens[2:]]
            commands.append(args)
            result = self.cli(*args)
            self.assertEqual(result.stderr, b'')
            receipt = json.loads(result.stdout)
            if 'render' in args:
                self.assertEqual(receipt['document_kind'], 'markdown')
                self.assertEqual((output / 'archive.sqlite').read_bytes(), before)
                raw = Path(args[args.index('--output') + 1]).read_bytes()
                self.assertIn('합성 한국어', raw.decode())
                self.assertNotIn('합성 한국어', result.stdout.decode())
            else:
                before = (output / 'archive.sqlite').read_bytes()
        result = self.cli(*commands[-1], expected=1)
        self.assertEqual(result.stdout, b'')
        self.assertEqual((output / 'archive.sqlite').read_bytes(), before)
        self.cli('--db', self.db, 'render', '--source', 'synthetic', '--conversation', 'fictional',
                 '--format', 'markdown', expected=2)

    def test_incomplete_synthetic_rollout_import_and_render_preserve_known_scope(self):
        # Syntactically complete records, but the assistant turn has no end marker.
        # No completeness metadata is invented by import or render.
        source = self.root / 'incomplete.jsonl'
        records = [dict(type='session_meta', payload=dict(id='synthetic-incomplete')),
                   dict(type='response_item', payload=dict(type='message', id='synthetic-user', role='user',
                        content=[dict(type='input_text', text='Fictional request 합성')])),
                   dict(type='response_item', payload=dict(type='message', id='synthetic-assistant', role='assistant',
                        content=[dict(type='output_text', text='Fictional unfinished answer\n```\n## Not a heading')]))]
        source.write_bytes(('\n'.join(json.dumps(row) for row in records) + '\n').encode('utf-8'))
        db = self.root / 'incomplete.sqlite'
        receipt = json.loads(self.cli('--db', db, 'import', source, '--format', 'local-codex', '--source', 'synthetic').stdout)
        self.assertEqual(receipt['inserted'], 2)
        before = db.read_bytes()
        view = json.loads(self.cli('--db', db, 'show', '--source', 'synthetic', '--conversation', 'synthetic-incomplete').stdout)
        rendered = self.root / 'incomplete.md'
        self.cli('--db', db, 'render', '--source', 'synthetic', '--conversation', 'synthetic-incomplete',
                 '--format', 'markdown', '--output', rendered)
        outside, blocks = self.blocks(rendered.read_bytes())
        self.assertEqual(len(blocks), 5)
        self.assertEqual(json.loads(blocks[0])['branch_scope'], view['branch_scope'])
        self.assertEqual(json.loads(blocks[0])['message_count'], 2)
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        for index, message in enumerate(view['messages']):
            metadata = json.loads(blocks[1 + index * 2])
            self.assertEqual(metadata['export_provenance'], message['export_provenance'])
            self.assertEqual(metadata['export_provenance'][0]['original_sha256'], original_hash)
            self.assertEqual(metadata['export_provenance'][0]['locator'], 'line:%d' % (index + 2))
            self.assertEqual(blocks[2 + index * 2], message['text'])
        self.assertNotIn('complete', json.loads(blocks[0]))
        self.assertNotIn('Not a heading', outside)
        self.assertEqual(db.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
