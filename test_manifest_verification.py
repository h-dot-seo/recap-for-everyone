import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from verify_manifest import verify


class ManifestVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'code.py').write_text('print("Synthetic example")\n')
        raw = (self.root / 'code.py').read_bytes()
        self.row = dict(path='code.py', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        self.manifest = self.root / 'PUBLICATION_MANIFEST.json'
        self.write([self.row])

    def write(self, rows):
        self.manifest.write_text(json.dumps(dict(files=rows, file_count=len(rows))))

    def test_exact_inventory_and_generated_bytecode(self):
        cache = self.root / '__pycache__'; cache.mkdir()
        (cache / 'code.cpython-test.pyc').write_bytes(b'synthetic bytecode placeholder')
        git = self.root / '.git'; git.mkdir(); (git / 'config').write_text('synthetic metadata')
        self.assertEqual(verify(self.root), [])
        (cache / 'notes.txt').write_text('Synthetic unexpected notes')
        self.assertTrue(any('unexpected file' in error for error in verify(self.root)))

    def test_unlisted_text_and_hidden_files_are_not_silently_accepted(self):
        for name in ('unexpected.txt', '.unexpected'):
            path = self.root / name; path.write_text('Synthetic only')
            self.assertTrue(any(name + ': unexpected' in error for error in verify(self.root)))
            path.unlink()

    def test_changed_and_missing_bytes(self):
        (self.root / 'code.py').write_text('Changed synthetic content')
        self.assertTrue(any('size/hash mismatch' in error for error in verify(self.root)))
        (self.root / 'code.py').unlink()
        self.assertTrue(any('missing' in error for error in verify(self.root)))

    def test_unsafe_and_alias_paths(self):
        for name in ('../outside', '/absolute', 'C:\\outside', 'folder\\file', '.git/config',
                     '__pycache__/file.pyc', 'PUBLICATION_MANIFEST.json', 'folder//file',
                     '.', 'CON', 'NUL.txt', 'folder/LPT1.py', 'COM¹.txt', 'trailing.',
                     'trailing ', 'has?question', 'has*star', 'has|pipe'):
            with self.subTest(name=name):
                self.write([dict(self.row, path=name)])
                self.assertIn('unsafe manifest path', verify(self.root))
        self.write([self.row, dict(self.row, path='CODE.PY')])
        self.assertIn('duplicate manifest path', verify(self.root))

    def test_invalid_schema_and_entry_metadata(self):
        for value in (None, [], {'files': {}, 'file_count': 0}, {'files': [], 'file_count': True}):
            self.manifest.write_text(json.dumps(value))
            self.assertEqual(verify(self.root), ['invalid manifest structure'])
        self.write([dict(self.row, bytes=True), None])
        errors = verify(self.root)
        self.assertTrue(any('invalid size/hash' in error for error in errors))
        self.assertIn('invalid manifest entry', errors)

    def test_broken_manifest_is_a_clean_validation_error(self):
        self.manifest.write_text('{broken')
        self.assertEqual(verify(self.root), ['manifest is missing, unreadable or invalid JSON'])
        self.manifest.unlink()
        self.assertEqual(verify(self.root), ['manifest is missing, unreadable or invalid JSON'])

    def test_duplicate_manifest_metadata_is_rejected(self):
        self.manifest.write_text('{"file_count":0,"file_count":1,"files":[]}')
        self.assertEqual(verify(self.root), ['manifest is missing, unreadable or invalid JSON'])

    def test_manifest_symlink_is_rejected_before_loading(self):
        self.manifest.unlink()
        try:
            self.manifest.symlink_to(self.root / 'code.py')
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable on this platform')
        self.assertEqual(verify(self.root), ['manifest symlink not allowed'])

    def test_symlink_rejected_without_following_it(self):
        target = self.root / 'link.py'
        try:
            target.symlink_to(self.root / 'code.py')
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable on this platform')
        self.assertTrue(any('symlink not allowed' in error for error in verify(self.root)))
