"""Synthetic saved-queue rendering; no private data or online services."""
import base64
import copy
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
from recaplib.title_batch import review_queue
from recaplib import render_queue as render
from tests.test_render_view import Parsed

ROOT = Path(__file__).resolve().parents[1]


class QueueViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'archive.sqlite'
        ingest(self.db, 'synthetic', ROOT / 'examples/render-adversarial.jsonl')
        self.queue = review_queue(self.db, 'synthetic')
        self.input = self.root / 'queue.json'
        self.output = self.root / 'queue.html'

    def save_input(self, value=None):
        self.input.write_bytes((json.dumps(self.queue if value is None else value, ensure_ascii=False) + '\n').encode())

    def test_inert_deterministic_original_file_binding(self):
        attack = '</pre><script>synthetic</script> ``` # Forged [x](https://example.invalid) 합성 한국어\u202e\x1b\r\x7f\u2028\u2029\u200c\u200d'
        self.queue['items'][0]['proposal']['synthetic_metadata'] = {attack: attack}
        self.save_input()
        before = self.input.read_bytes(), self.db.read_bytes()
        receipt = render.render_queue(self.input, self.output)
        raw = self.output.read_bytes()
        other = self.root / 'other.html'
        self.assertEqual(receipt, render.render_queue(self.input, other))
        self.assertEqual(raw, other.read_bytes())
        self.assertEqual(before, (self.input.read_bytes(), self.db.read_bytes()))
        parsed = Parsed(raw)
        text = ''.join(parsed.text)
        self.assertIn(hashlib.sha256(before[0]).hexdigest(), text)
        self.assertIn('Absence of flags is not privacy clearance.', text)
        self.assertIn('합성 한국어', text)
        self.assertIn('</pre><script>', text)
        for value in ('\\u202e', '\\u001b', '\\r', '\\u007f', '\\u2028', '\\u2029'):
            self.assertIn(value, text)
        for value in ('\u202e', '\x1b', '\r', '\x7f', '\u2028', '\u2029'):
            self.assertNotIn(value, raw.decode())
        self.assertIn('\u200c\u200d', raw.decode())
        self.assertFalse({'script', 'form', 'a', 'img', 'iframe', 'link', 'button'} & {t for t, a in parsed.tags})
        for tag, attrs in parsed.tags:
            self.assertFalse({'href', 'src', 'action'} & attrs.keys())
            self.assertFalse(any(key.startswith('on') for key in attrs))
        style = re.search(rb'<style>(.*?)</style>', raw).group(1)
        policy = next(a['content'] for t, a in parsed.tags if a.get('http-equiv') == 'Content-Security-Policy')
        self.assertIn(base64.b64encode(hashlib.sha256(style).digest()).decode(), policy)
        for part in ("default-src 'none'", "base-uri 'none'", "form-action 'none'", "object-src 'none'", "frame-src 'none'"):
            self.assertIn(part, policy)
        self.assertEqual(receipt['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertNotIn(str(self.root), json.dumps(receipt))
        self.assertNotIn('synthetic_metadata', json.dumps(receipt))

    def test_empty_unavailable_supplied_and_order(self):
        for queue in (review_queue(self.db, 'empty'), review_queue(self.db, 'synthetic', supplied_proposals=[]),
                      review_queue(self.db, 'synthetic', supplied_proposals=[], supplied_only=True)):
            render.validate_queue(queue)
        queue = review_queue(self.db, 'synthetic', supplied_proposals=[])
        self.save_input(queue)
        render.render_queue(self.input, self.output)
        self.assertIn('NO_SUPPLIED_PROPOSAL', self.output.read_text())
        item = copy.deepcopy(self.queue['items'][0])
        item['conversation'] = item['proposal']['conversation'] = 'second'
        self.queue['items'].insert(0, item)
        self.queue.update(total_conversations=2, source_total_conversations=2, ready_count=2)
        self.save_input()
        render.render_queue(self.input, self.root / 'order.html')
        text = ''.join(Parsed((self.root / 'order.html').read_bytes()).text)
        self.assertLess(text.index('second'), text.index('fictional'))

    def test_reject_malformed_private_json(self):
        for raw in (b'{"private":', b'{"schema":1,"schema":2}', b'"\\ud800"', b'\xff', b'{}',
                    b'{"private":NaN}', b'{"private":1e999}', b'[' * 1500):
            self.input.write_bytes(raw)
            with self.subTest(raw=raw[:20]), self.assertRaisesRegex(ValueError, '^' + render.ERROR + '$'):
                render.render_queue(self.input, self.output)
            self.assertFalse(self.output.exists())

    def test_schema_types_counts_identities_and_variants(self):
        mutations = [lambda q: q.update(limit=True), lambda q: q.update(ready_count=0),
                     lambda q: q.update(next_offset=False), lambda q: q.update(extra='private'),
                     lambda q: q.update(remote_mutation=True), lambda q: q.update(items={}),
                     lambda q: q['items'][0].update(status='APPLIED'),
                     lambda q: q['items'][0].update(current_revision=True),
                     lambda q: q['items'][0]['proposal'].update(conversation='other'),
                     lambda q: q['items'][0]['collisions'].update(existing_title_count=-1),
                     lambda q: q['items'][0]['title_advisory'].update(privacy_flags='none'),
                     lambda q: q['items'][0]['review_state'].update(expected_content_sha256='bad'),
                     lambda q: q.update(supplied_only=True),
                     lambda q: q.update(items=q['items'] * 2, total_conversations=2, source_total_conversations=2, ready_count=2)]
        for change in mutations:
            queue = copy.deepcopy(self.queue)
            change(queue)
            self.save_input(queue)
            with self.assertRaisesRegex(ValueError, render.ERROR):
                render.render_queue(self.input, self.output)
            self.assertFalse(self.output.exists())

    def test_bom_hash_and_caps(self):
        self.save_input()
        self.input.write_bytes(b'\xef\xbb\xbf' + self.input.read_bytes())
        render.render_queue(self.input, self.output)
        self.assertIn(hashlib.sha256(self.input.read_bytes()).hexdigest(), self.output.read_text())
        for constant in ('MAX_INPUT_BYTES', 'MAX_OUTPUT_BYTES'):
            with patch.object(render, constant, 32), self.assertRaisesRegex(ValueError, '16 MiB'):
                render.render_queue(self.input, self.root / 'too-big.html')
            self.assertFalse((self.root / 'too-big.html').exists())

    def test_exclusive_outputs_and_failed_publication(self):
        self.save_input()
        for path in (self.input, self.root):
            with self.assertRaises(OSError):
                render.render_queue(self.input, path)
        link = self.root / 'dangling'
        try:
            link.symlink_to(self.root / 'missing')
        except OSError:
            pass
        else:
            with self.assertRaises(OSError):
                render.render_queue(self.input, link)
        with patch('recaplib.document_output.os.link', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):
                render.render_queue(self.input, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.recap-view-*')), [])

    def test_cli_no_database_ascii_receipt_and_rejections(self):
        self.save_input()
        self.db.unlink()
        env = dict(os.environ, PYTHONIOENCODING='ascii')
        args = [sys.executable, str(ROOT / 'recap.py')]
        result = subprocess.run(args + ['render-queue', str(self.input), '--output', str(self.output)], env=env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.decode('ascii'))['schema'], 'recap.saved-view.v1')
        self.assertFalse(self.db.exists())
        for extra in (['--db', str(self.db)],):
            result = subprocess.run(args + extra + ['render-queue', str(self.input), '--output', str(self.root / 'no.html')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.db.exists())
        result = subprocess.run(args + ['render-queue', str(self.input)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_supplied_proposal_variants_and_page_metadata(self):
        proposal = self.queue['items'][0]['proposal']
        for kwargs in ({'supplied_proposals': [proposal]},
                       {'supplied_proposals': [proposal], 'supplied_only': True},
                       {'offset': 99}, {'limit': 1}, {'review_state_filter': 'open'},
                       {'unrenamed_only': True}):
            queue = review_queue(self.db, 'synthetic', **kwargs)
            render.validate_queue(queue)

    def test_exact_output_limit_and_expansion(self):
        self.save_input()
        render.render_queue(self.input, self.output)
        size = self.output.stat().st_size
        with patch.object(render, 'MAX_OUTPUT_BYTES', size):
            render.render_queue(self.input, self.root / 'exact.html')
        with patch.object(render, 'MAX_OUTPUT_BYTES', size - 1):
            with self.assertRaisesRegex(ValueError, '16 MiB'):
                render.render_queue(self.input, self.root / 'over.html')
        self.assertFalse((self.root / 'over.html').exists())
        self.assertEqual(list(self.root.glob('.recap-view-*')), [])

    def test_post_publication_cleanup_failure_receipt(self):
        self.save_input()
        original = Path.unlink
        def failed_stage(path, *args, **kwargs):
            if path.name.startswith('.recap-view-'):
                raise OSError('synthetic cleanup failure')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', failed_stage):
            receipt = render.render_queue(self.input, self.output)
        self.assertEqual(receipt['status'], 'SAVED')
        self.assertFalse(receipt['staging_cleanup_complete'])
        stage = self.root / receipt['remaining_staging_file']
        self.assertEqual(stage.read_bytes(), self.output.read_bytes())

    def test_documented_guide(self):
        guide = (ROOT / 'docs/RENDER_QUEUE.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', guide, re.S)
        self.assertEqual(len(blocks), 1)
        folder = self.root / 'guide'
        folder.mkdir()
        for line in blocks[0].strip().splitlines():
            self.assertNotIn('>', line)
            args = shlex.split(line)
            args[0] = sys.executable
            args = [arg.replace('OUTPUT', str(folder)) for arg in args]
            result = subprocess.run(args, cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING='ascii'), capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout.decode('ascii'))
        self.assertEqual(value['schema'], 'recap.saved-view.v1')
        self.assertTrue((folder / 'queue.html').exists())
