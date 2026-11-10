"""Synthetic adversarial read-only view checks; no private conversation data."""
import base64
import hashlib
from html.parser import HTMLParser
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


class Parsed(HTMLParser):
    def __init__(self, raw):
        super().__init__()
        self.tags = []
        self.text = []
        self.feed(raw.decode('utf-8'))

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, text):
        self.text.append(text)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        self.input = ROOT / 'examples/render-adversarial.jsonl'
        ingest(self.db, 'synthetic', self.input)
        self.output = self.root / 'view.html'

    def view(self, **kwargs):
        return conversation(self.db, 'synthetic', 'fictional', **kwargs)

    def save(self, **kwargs):
        return render.render_conversation(self.db, 'synthetic', 'fictional', self.output, **kwargs)

    def test_html_inert_unicode_policy_and_csp(self):
        raw = render.render_html(self.view())
        parsed = Parsed(raw)
        self.assertFalse({'script', 'form', 'a', 'img', 'iframe', 'link'} & {t for t, a in parsed.tags})
        for tag, attrs in parsed.tags:
            self.assertFalse({'src', 'href', 'action'} & attrs.keys())
            self.assertFalse(any(key.startswith('on') for key in attrs))
        text = ''.join(parsed.text)
        for value in ('합성 한국어', '</pre><script>', '[x](https://example.invalid)', '# Forged', '```', '\\u202e', '\\u001b', '\\u000d', '\\u007f', '\\u2028', '\\u2029'):
            self.assertIn(value, text)
        for char in ('\u202e', '\x1b', '\r', '\x7f', '\u2028', '\u2029'):
            self.assertNotIn(char, raw.decode())
        self.assertIn('\u200c\u200d', raw.decode())
        style = re.search(rb'<style>(.*?)</style>', raw).group(1)
        expected = base64.b64encode(hashlib.sha256(style).digest()).decode()
        csp = next(a['content'] for t, a in parsed.tags if a.get('http-equiv') == 'Content-Security-Policy')
        self.assertIn("style-src 'sha256-" + expected + "'", csp)
        for rule in ("default-src 'none'", "base-uri 'none'", "form-action 'none'", "object-src 'none'", "frame-src 'none'"):
            self.assertIn(rule, csp)
        self.assertIn(('meta', {'name': 'referrer', 'content': 'no-referrer'}), parsed.tags)

    def test_snapshot_selection_provenance_and_hash(self):
        before = self.db.read_bytes()
        for kwargs in ({}, {'limit': 1, 'offset': 1}, {'message_id': 'one'},
                       {'around_message_id': 'two', 'before': 1, 'after': 0}, {'limit': 1, 'offset': 99}):
            with self.subTest(kwargs=kwargs):
                view = self.view(**kwargs)
                raw = render.render_html(view)
                self.assertEqual(raw, render.render_html(self.view(**kwargs)))
                parsed = Parsed(raw)
                text = ''.join(parsed.text)
                self.assertIn(render.view_sha256(view), text)
                self.assertEqual(render.view_sha256(view), hashlib.sha256(json.dumps(view, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('ascii')).hexdigest())
                for field in ('message_order', 'branch_scope', 'scope', 'source_sha256', 'source_line'):
                    if view['messages'] or not field.startswith('source_'):
                        self.assertIn(field, text)
                if 'selection' in view:
                    self.assertIn('selection', text)
                self.assertNotIn(str(self.db), text)
        self.assertEqual(self.db.read_bytes(), before)

    def test_every_supplied_metadata_value_is_inert_and_snapshot_read_once(self):
        view = self.view(limit=1)
        attack = '</bdi></pre><img src=x onerror=x>\u202e'
        for key in ('source', 'conversation', 'original_title', 'display_title'):
            view[key] = attack
        for key in ('message_id', 'role', 'timestamp', 'original_title'):
            view['messages'][0][key] = attack
        view['messages'][0]['export_provenance'] = [dict(original_sha256='a' * 64,
                                                       locator=attack, parent_id=attack)]
        with patch.object(render, 'conversation', return_value=view) as read:
            self.save(limit=1)
        read.assert_called_once_with(self.db, 'synthetic', 'fictional', 1, 0, None, None, None, None)
        parsed = Parsed(self.output.read_bytes())
        self.assertNotIn('img', {tag for tag, attrs in parsed.tags})
        self.assertIn('export_provenance', ''.join(parsed.text))
        self.assertIn('parent_id', ''.join(parsed.text))
        self.assertEqual([attrs['id'] for tag, attrs in parsed.tags if 'id' in attrs], ['m-0001'])

    def test_receipt_exclusive_write_and_cleanup(self):
        receipt = self.save()
        raw = self.output.read_bytes()
        self.assertEqual(receipt['schema'], 'recap.saved-view.v1')
        self.assertEqual(receipt['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(receipt['bytes'], len(raw))
        for private in (str(self.output), 'fictional', '합성 한국어'):
            self.assertNotIn(private, json.dumps(receipt, ensure_ascii=False))
        with self.assertRaises(FileExistsError): self.save()
        self.assertEqual(self.output.read_bytes(), raw)
        self.assertEqual(list(self.root.glob('.recap-view-*')), [])

    def test_cap_and_invalid_selection_publish_nothing(self):
        with patch.object(render, 'MAX_OUTPUT_BYTES', 100), self.assertRaisesRegex(ValueError, 'narrow the message selection'):
            self.save()
        for kwargs in ({'limit': 0}, {'offset': 1}, {'message_id': 'missing'},
                       {'message_id': 'one', 'limit': 1}, {'before': 1},
                       {'around_message_id': 'one', 'after': 51}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.save(**kwargs)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.recap-view-*')), [])

    def test_encoded_cap_exact_boundary_and_surrogates(self):
        view = self.view()
        view['messages'][0]['text'] += '\ud800'
        raw = render.render_html(view)
        self.assertIn(b'\\ud800', raw)
        with patch.object(render, 'MAX_OUTPUT_BYTES', len(raw)):
            self.assertEqual(render.render_html(view), raw)
        with patch.object(render, 'MAX_OUTPUT_BYTES', len(raw) - 1), self.assertRaises(ValueError):
            render.render_html(view)

    def test_saved_cleanup_failure_and_link_failure(self):
        unlink = Path.unlink
        def fail_stage(path, *args, **kwargs):
            if path.name.startswith('.recap-view-'): raise OSError('synthetic failure')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_stage): receipt = self.save()
        self.assertFalse(receipt['staging_cleanup_complete'])
        self.assertEqual((self.root / receipt['remaining_staging_file']).read_bytes(), self.output.read_bytes())
        self.output.unlink()
        with patch('recaplib.document_output.os.link', side_effect=OSError('synthetic failure')), self.assertRaises(OSError): self.save()
        self.assertFalse(self.output.exists())

    def test_guide_commands_and_show_unchanged(self):
        guide = (ROOT / 'docs/RENDER_VIEWS.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', guide, re.S)
        self.assertEqual(len(blocks), 1)
        output = self.root / 'guide'; output.mkdir()
        receipts = []
        for line in blocks[0].strip().splitlines():
            tokens = shlex.split(line)
            self.assertEqual(tokens[:2], ['python', 'recap.py'])
            self.assertIn('OUTPUT', line)
            result = subprocess.run([sys.executable] + [t.replace('OUTPUT', str(output)) for t in tokens[1:]], cwd=ROOT,
                                    capture_output=True, env=dict(os.environ, PYTHONIOENCODING='ascii'), timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b'')
            receipts.append(json.loads(result.stdout.decode('ascii')))
        self.assertEqual(receipts[-1]['schema'], 'recap.saved-view.v1')
        result = subprocess.run([sys.executable, 'recap.py', '--db', str(self.db), 'show', '--source', 'synthetic', '--conversation', 'fictional'], cwd=ROOT, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), self.view())


if __name__ == '__main__':
    unittest.main()
