"""Synthetic parent-path selection, independent of export insertion order."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from web_branch import branch_view
from session_workflow import normalize


def fixture():
    def node(parent, text=None):
        return dict(parent=parent, message=None if text is None else dict(
            author=dict(role='user'), content=dict(parts=[text])))
    return [dict(id='synthetic', title='New chat', current_node='active', mapping={
        'active': node('question', 'Synthetic selected orchard'),
        'old': node('question', 'Synthetic abandoned peach'),
        'root': node(None), 'question': node('root', 'Synthetic fruit plan')})]


class BranchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'web.json'
        self.data = fixture(); self.write()

    def write(self):
        self.path.write_text(json.dumps(self.data), encoding='utf-8')

    def test_current_path_is_root_to_tip_and_preserves_origin(self):
        raw = self.path.read_bytes()
        view = branch_view(self.path, 'synthetic')
        self.assertEqual(view['node_ids'], ['root', 'question', 'active'])
        self.assertEqual([m['message_id'] for m in view['messages']], ['question', 'active'])
        self.assertEqual(view['selected_nodes_without_text'], 1)
        self.assertEqual(view['excluded_nodes'], 1)
        self.assertEqual(view['leaf_nodes'], ['active', 'old'])
        self.assertEqual(view['original_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(view['messages'][1]['origin_locator'], 'mapping:active')
        self.assertEqual(view['forks'], [dict(node='question', children=['active', 'old'])])
        self.assertNotIn('abandoned', json.dumps(view))
        self.assertEqual(raw, self.path.read_bytes())

    def test_explicit_alternate_and_interior_node(self):
        self.assertEqual(branch_view(self.path, 'synthetic', 'old')['node_ids'], ['root', 'question', 'old'])
        interior = branch_view(self.path, 'synthetic', 'question')
        self.assertFalse(interior['selected_node_is_leaf'])
        self.assertEqual(interior['continuations'], ['active', 'old'])
        self.assertEqual(interior['excluded_nodes'], 2)
        root = branch_view(self.path, 'synthetic', 'root')
        self.assertEqual(root['messages'], [])

    def test_invalid_current_node_never_guesses_latest_leaf(self):
        for invalid in (None, '', [], 'missing'):
            self.data[0]['current_node'] = invalid; self.write()
            with self.assertRaises(ValueError): branch_view(self.path, 'synthetic')
            self.assertEqual(branch_view(self.path, 'synthetic', 'old')['selected_node'], 'old')

    def test_ambiguous_conversation_and_bad_off_path_graph_rejected(self):
        self.data.append(self.data[0]); self.write()
        with self.assertRaises(ValueError): branch_view(self.path, 'synthetic')
        self.data = fixture(); self.data[0]['mapping']['old']['parent'] = 'old'; self.write()
        with self.assertRaises(ValueError): branch_view(self.path, 'synthetic')

    def test_default_import_normalization_is_unchanged(self):
        self.assertEqual([r['message_id'] for r in normalize(self.path, 'web')], ['active', 'old', 'question'])
        branch_view(self.path, 'synthetic')
        self.assertEqual([r['message_id'] for r in normalize(self.path, 'web')], ['active', 'old', 'question'])

    def test_cli_equivalence_and_no_database_creation(self):
        db = Path(self.tmp.name) / 'never-open.sqlite'
        outputs = []
        for args in [('web_branch.py', self.path, '--conversation', 'synthetic'),
                     ('recap.py', '--db', db, 'web-branch', self.path, '--conversation', 'synthetic')]:
            result = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(json.loads(result.stdout))
        self.assertEqual(outputs[0], outputs[1]); self.assertFalse(db.exists())
        result = subprocess.run([sys.executable, 'recap.py', 'web-branch', str(self.path),
                                 '--conversation', 'synthetic', '--node', 'absent'],
                                capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0); self.assertNotIn('Traceback', result.stderr)

    def test_both_entrypoints_escape_unicode_on_ascii_stdout(self):
        self.data[0]['mapping']['active']['message']['content']['parts'] = ['한글 🌱']
        self.write()
        results = []
        for prefix in [('web_branch.py',), ('recap.py', 'web-branch')]:
            result = subprocess.run([sys.executable, *prefix, str(self.path), '--conversation', 'synthetic'],
                                    capture_output=True, text=True, timeout=20,
                                    env=dict(os.environ, PYTHONIOENCODING='ascii'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            results.append(json.loads(result.stdout))
        self.assertEqual(results[0], results[1])

    def test_both_branch_entrypoints_reject_unpaired_surrogates(self):
        self.data[0]['mapping']['active']['message']['content']['parts'] = ['PRIVATE_SYNTHETIC\ud800']
        self.write()
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'unpaired surrogates'):
            branch_view(self.path, 'synthetic')
        for prefix in [('web_branch.py',), ('recap.py', 'web-branch')]:
            result = subprocess.run([sys.executable, *prefix, str(self.path), '--conversation', 'synthetic'],
                                    capture_output=True, text=True, timeout=20,
                                    env=dict(os.environ, PYTHONIOENCODING='ascii'))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unpaired surrogates', result.stderr)
            self.assertNotIn('PRIVATE_SYNTHETIC', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(self.path.read_bytes(), original)

    def test_long_path_is_iterative(self):
        self.data[0]['mapping'] = {str(i): dict(parent=str(i-1) if i else None) for i in range(4000)}
        self.data[0]['current_node'] = '3999'; self.write()
        self.assertEqual(branch_view(self.path, 'synthetic')['selected_nodes'], 4000)
