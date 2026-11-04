"""Synthetic role-scoped pre-import discovery regressions."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from export_inventory import list_export


class InventoryRoleFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.json'

    def write(self, kind, rows):
        if kind == 'web':
            data = [dict(id=identity, mapping={str(i): dict(message=dict(
                author=dict(role=role), content=dict(parts=[text])))
                for i, (role, text) in enumerate(messages)}) for identity, messages in rows]
            text = json.dumps(data)
        else:
            records = []
            for identity, messages in rows:
                records.append(dict(type='session_meta', payload=dict(id=identity)))
                records.extend(dict(type='response_item', payload=dict(type='message',
                    id=str(i), role=role, content=[dict(type='input_text', text=text)]))
                    for i, (role, text) in enumerate(messages))
            text = '\n'.join(map(json.dumps, records))
        self.path.write_text(text, encoding='utf-8')

    def test_role_discovery_preserves_whole_export_counts_and_bytes(self):
        for kind in ('web', 'local', 'local-codex'):
            with self.subTest(kind=kind):
                self.write(kind, [('assistant-only', [('assistant', 'orchard')]),
                    ('request', [('user', 'orchard orchard'), ('assistant', 'orchard'), ('user', 'other')])])
                raw = self.path.read_bytes()
                result = list_export(self.path, kind, text_contains='ORCHARD', text_role='user')
                self.assertEqual(result['total_conversations'], 2)
                self.assertEqual(result['selectable_conversations'], 2)
                item, = result['conversations']
                self.assertEqual(item['conversation'], 'request')
                self.assertEqual(item['role_counts'], {'assistant': 1, 'user': 2})
                self.assertEqual(item['matched_role_counts'], {'user': 1})
                self.assertEqual(item['extracted_messages'], 3)
                self.assertEqual(result['filter']['matched_messages'], 1)
                self.assertEqual(result['filter']['text_role'], 'user')
                self.assertFalse(result['contains_message_text'])
                self.assertEqual(self.path.read_bytes(), raw)
                self.assertEqual(result['original_sha256'], hashlib.sha256(raw).hexdigest())

    def test_all_web_roles_and_unselected_branch(self):
        for role in ('user', 'assistant', 'system', 'tool'):
            with self.subTest(role=role):
                self.write('web', [(r, [(r, 'orchard')]) for r in ('user', 'assistant', 'system', 'tool')])
                result = list_export(self.path, 'web', text_contains='orchard', text_role=role)
                self.assertEqual([x['conversation'] for x in result['conversations']], [role])
        data = json.loads(self.path.read_text())
        data[0]['current_node'] = '0'
        data[0]['mapping']['alternate'] = dict(parent='0', message=dict(author=dict(role='assistant'), content=dict(parts=['branch-only'])))
        self.path.write_text(json.dumps(data))
        self.assertEqual(list_export(self.path, 'web', text_contains='branch-only', text_role='assistant')['filter']['matched_messages'], 1)

    def test_local_roles_are_not_invented(self):
        for kind in ('local', 'local-codex'):
            self.write(kind, [('request', [('user', 'orchard'), ('tool', 'orchard')])])
            result = list_export(self.path, kind, text_contains='orchard', text_role='tool')
            self.assertEqual(result['conversations'], [])
            self.assertEqual(result['filter']['matched_messages'], 0)
            self.assertEqual(result['coverage']['extracted_messages'], 1)

    def test_filtered_pagination_and_hash_lease(self):
        self.write('web', [('a', [('assistant', 'orchard')]), ('b', [('user', 'orchard')]), ('c', [('user', 'orchard')])])
        first = list_export(self.path, 'web', limit=1, text_contains='orchard', text_role='user')
        self.assertEqual(first['next_offset'], 1)
        second = list_export(self.path, 'web', limit=1, offset=1, text_contains='orchard', text_role='user', expected_export_sha256=first['original_sha256'])
        self.assertEqual(second['conversations'][0]['conversation'], 'c')
        self.assertIsNone(second['next_offset'])
        self.path.write_text('[]')
        with self.assertRaises(ValueError):
            list_export(self.path, 'web', text_contains='orchard', text_role='user', expected_export_sha256=first['original_sha256'])

    def test_canonical_unicode_and_literal_matching(self):
        self.write('web', [('match', [('user', 'cafe\u0301 *[a]')]), ('echo', [('assistant', 'café *[a]')])])
        self.assertEqual(list_export(self.path, 'web', text_contains='CAFÉ *[a]', text_role='user')['conversations'], [])
        result = list_export(self.path, 'web', text_contains='CAFÉ *[a]', text_role='user', canonical_unicode=True)
        self.assertEqual(result['conversations'][0]['conversation'], 'match')

    def test_invalid_options_fail_before_read(self):
        with patch('export_inventory._read_export_bytes', side_effect=AssertionError('must not read')):
            for role in ('', 'USER', ' user', 'developer', [], {}, 1, False, '\ud800'):
                with self.subTest(role=repr(role)), self.assertRaisesRegex(ValueError, 'text_role'):
                    list_export(self.path, 'web', text_contains='orchard', text_role=role)
            for options in ({}, {'contains': 'orchard'}):
                with self.assertRaisesRegex(ValueError, 'text_role requires text_contains'):
                    list_export(self.path, 'web', text_role='user', **options)

    def test_unmatched_malformed_records_still_reject(self):
        for kind in ('web', 'local', 'local-codex'):
            self.write(kind, [('request', [('user', 'orchard')]), ('bad', [('assistant', 'other')])])
            raw = self.path.read_text().replace('"assistant"', '{}')
            self.path.write_text(raw)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                list_export(self.path, kind, text_contains='orchard', text_role='user')

    def test_no_selector_retains_identical_output(self):
        self.write('web', [('a', [('assistant', 'orchard'), ('user', 'orchard')])])
        self.assertEqual(list_export(self.path, 'web', text_contains='orchard'),
                         list_export(self.path, 'web', text_contains='orchard', text_role=None))
        self.assertNotIn('text_role', list_export(self.path, 'web', text_contains='orchard')['filter'])

    def test_both_cli_entry_points(self):
        self.write('web', [('echo', [('assistant', 'orchard')]), ('request', [('user', 'orchard')])])
        for script, prefix in (('recap.py', ['list-export']), ('export_inventory.py', [])):
            base = [sys.executable, str(Path(__file__).parent / script), *prefix, str(self.path), '--format', 'web']
            result = subprocess.run(base + ['--text-contains', 'orchard', '--text-role', 'user'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['conversations'][0]['conversation'], 'request')
            for args in (['--text-role', 'user'], ['--text-contains', 'orchard', '--text-role', 'developer']):
                failed = subprocess.run(base + args, capture_output=True, text=True)
                self.assertNotEqual(failed.returncode, 0)
                self.assertNotIn('Traceback', failed.stderr)


if __name__ == '__main__':
    unittest.main()
