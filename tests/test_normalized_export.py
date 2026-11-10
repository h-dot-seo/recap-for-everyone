"""Synthetic normalized export, publication and portability boundaries."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

from recaplib.archive import ingest, ingest_bytes
from recaplib.normalized_export import export_normalized
from recaplib.recovery import _publish_new_chunks
from recaplib.session_workflow import import_export, titles

ROOT = Path(__file__).resolve().parents[1]


class NormalizedExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'archive.sqlite'
        self.out = self.root / 'copy.jsonl'

    def seed(self):
        return ingest(self.db, 'synthetic', ROOT / 'examples/conversations.jsonl')

    def test_golden_and_receipt(self):
        original = self.seed()
        before = self.db.read_bytes()
        receipt = export_normalized(self.db, 'synthetic', self.out)
        raw = self.out.read_bytes()
        self.assertEqual(raw, (ROOT / 'examples/conversations.jsonl').read_bytes())
        self.assertEqual(receipt['sha256'], original['source_sha256'])
        self.assertEqual(receipt['bytes'], len(raw))
        self.assertEqual(receipt['records'], 2)
        self.assertEqual(receipt['conversations'], 1)
        self.assertEqual(receipt['omitted_export_occurrences'], 0)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertFalse(receipt['receipt_contains_message_text'])
        self.assertTrue(receipt['contains_message_text'])
        self.assertNotIn('Synthetic orchard example', json.dumps(receipt))
        self.assertTrue(receipt['staging_cleanup_complete'])

    def test_roundtrip_interleaving_unicode_and_original_titles(self):
        rows = [dict(conversation_id=c, message_id=str(i), role='user', timestamp='synthetic',
                     title='' if i == 1 else 'Fictional title ' + str(i),
                     text='Synthetic\r\n\u2028\u0085\x00 한글 🦉')
                for i, c in enumerate(('z', 'a', 'z'))]
        ingest_bytes(self.db, 'synthetic', ('\n'.join(json.dumps(r) for r in rows)).encode())
        titles(self.db, 'synthetic', 'z', 'Local display title', 0)
        before = self.db.read_bytes()
        export_normalized(self.db, 'synthetic', self.out)
        raw = self.out.read_bytes()
        self.assertNotIn(b'\r', raw)
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        self.assertEqual([json.loads(line) for line in raw.split(b'\n') if line], rows)
        other = self.root / 'other.sqlite'
        self.assertEqual(ingest(other, 'moved', self.out)['inserted'], 3)
        self.assertEqual(ingest(other, 'moved', self.out)['inserted'], 0)
        second = self.root / 'second.jsonl'
        export_normalized(other, 'moved', second)
        self.assertEqual(raw, second.read_bytes())
        selected = self.root / 'selected.jsonl'
        r = export_normalized(self.db, 'synthetic', selected, 'z')
        self.assertEqual((r['records'], r['conversations']), (2, 1))
        self.assertEqual(self.db.read_bytes(), before)

    def test_provenance_union_and_legacy_only(self):
        import_export(self.db, 'synthetic', ROOT / 'examples/web-export.json', 'web')
        with sqlite3.connect(self.db) as c:
            count = c.execute('SELECT COUNT(*) FROM export_occurrences').fetchone()[0]
        first = export_normalized(self.db, 'synthetic', self.out)
        self.assertEqual(first['omitted_export_occurrences'], count)
        with sqlite3.connect(self.db) as c:
            c.execute('DROP TABLE export_occurrences')
        second = self.root / 'legacy.jsonl'
        receipt = export_normalized(self.db, 'synthetic', second)
        self.assertEqual(receipt['omitted_export_occurrences'], count)
        self.assertEqual(second.read_bytes(), self.out.read_bytes())
        other = self.root / 'other.sqlite'
        ingest(other, 'moved', self.out)
        with sqlite3.connect(other) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'export_%'").fetchone()[0], 0)

    def test_duplicate_occurrences_are_counted_not_exported(self):
        self.seed()
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE export_provenance (source,conversation,message,original_hash,locator,parent)')
            c.execute('CREATE TABLE export_occurrences (source,conversation,message,original_hash,locator,parent)')
            row = ('synthetic', 'demo-conversation', 'demo-user', 'a'*64, 'line:1', None)
            c.execute('INSERT INTO export_provenance VALUES(?,?,?,?,?,?)', row)
            c.executemany('INSERT INTO export_occurrences VALUES(?,?,?,?,?,?)', [row, (*row[:4], 'line:2', None)])
        r = export_normalized(self.db, 'synthetic', self.out)
        self.assertEqual((r['records'], r['omitted_export_occurrences']), (2, 2))

    def test_reject_existing_and_dangling_link(self):
        self.seed()
        self.out.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            export_normalized(self.db, 'synthetic', self.out)
        self.assertEqual(self.out.read_bytes(), b'existing')
        self.out.unlink()
        try:
            self.out.symlink_to(self.root / 'absent')
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaises(FileExistsError):
            export_normalized(self.db, 'synthetic', self.out)

    def test_invalid_and_missing_selection_never_stages(self):
        self.seed()
        for source, conversation in [('missing', None), ('synthetic', 'missing'), ('', None), ('synthetic', ''), ('synthetic', '\ud800')]:
            with self.subTest(source=source, conversation=conversation):
                with self.assertRaises(ValueError):
                    export_normalized(self.db, source, self.out, conversation)
        absent = self.root / 'absent.sqlite'
        with self.assertRaises(sqlite3.Error):
            export_normalized(absent, 'synthetic', self.out)
        self.assertFalse(absent.exists())
        self.assertEqual(list(self.root.iterdir()), [self.db])

    def test_staging_failure_and_publication_race(self):
        self.seed()
        with patch('recaplib.recovery.os.fsync', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):
                export_normalized(self.db, 'synthetic', self.out)
        self.assertEqual(list(self.root.iterdir()), [self.db])
        real_link = os.link
        def race(src, dst):
            Path(dst).write_bytes(b'other writer')
            real_link(src, dst)
        with patch('recaplib.recovery.os.link', side_effect=race):
            with self.assertRaises(FileExistsError):
                export_normalized(self.db, 'synthetic', self.out)
        self.assertEqual(self.out.read_bytes(), b'other writer')
        self.assertFalse(list(self.root.glob('.recap-*')))

    def test_invalid_archive_row_does_not_publish_partial_file(self):
        self.seed()
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE messages SET role='unsupported' WHERE message_id='demo-assistant'")
        with self.assertRaises(ValueError):
            export_normalized(self.db, 'synthetic', self.out)
        self.assertEqual(list(self.root.iterdir()), [self.db])

    def test_postpublication_cleanup_failure_is_reported(self):
        self.seed()
        unlink = Path.unlink
        def fail_staging(path, *args, **kwargs):
            if path.name.startswith('.recap-normalized-export-'):
                raise OSError('synthetic cleanup failure')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_staging):
            r = export_normalized(self.db, 'synthetic', self.out)
        self.assertFalse(r['staging_cleanup_complete'])
        staging = self.root / r['remaining_staging_file']
        self.assertEqual(staging.read_bytes(), self.out.read_bytes())
        staging.unlink()

    def test_one_snapshot_under_concurrent_write(self):
        self.seed()
        with sqlite3.connect(self.db) as c:
            c.execute('PRAGMA journal_mode=WAL')
        def concurrent(output, chunks, prefix):
            row = dict(conversation_id='late', message_id='late', role='user', timestamp='synthetic', text='Late fictional message')
            ingest_bytes(self.db, 'synthetic', json.dumps(row).encode())
            return _publish_new_chunks(output, chunks, prefix)
        with patch('recaplib.normalized_export._publish_new_chunks', side_effect=concurrent):
            r = export_normalized(self.db, 'synthetic', self.out)
        self.assertEqual(r['records'], 2)
        self.assertEqual(r['conversations'], 1)
        self.assertEqual(self.out.read_bytes(), (ROOT / 'examples/conversations.jsonl').read_bytes())

    def test_streaming_memory(self):
        self.seed()
        with sqlite3.connect(self.db) as c:
            c.executemany('INSERT INTO messages(source_id,conversation_id,message_id,role,timestamp,title,text,source_sha256,source_line) VALUES(?,?,?,?,?,?,?,?,?)',
                (('synthetic', 'many', str(i), 'user', 'synthetic', '', 'x'*4096, 'a'*64, i+1) for i in range(4000)))
        tracemalloc.start()
        try:
            r = export_normalized(self.db, 'synthetic', self.out)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertEqual(r['records'], 4002)
        self.assertLess(peak, 2 * 1024 * 1024)
        self.assertGreater(self.out.stat().st_size, 16 * 1024 * 1024)

    def test_documented_commands_ascii_and_cli_requirements(self):
        document = (ROOT / 'docs/EXPORT_NORMALIZED.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', document, re.S)
        self.assertEqual(len(blocks), 1)
        outputs = []
        for line in blocks[0].strip().splitlines():
            tokens = shlex.split(line)
            self.assertEqual(tokens[:2], ['python', 'recap.py'])
            self.assertIn('OUTPUT', line)
            r = subprocess.run([sys.executable] + [t.replace('OUTPUT', str(self.root)) for t in tokens[1:]],
                cwd=ROOT, capture_output=True, env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0'), timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.isascii())
            outputs.append(json.loads(r.stdout))
        self.assertGreater(outputs[2]['omitted_export_occurrences'], 0)
        self.assertEqual(outputs[-2]['messages'], outputs[-1]['messages'])
        for args in [('export-normalized', '--source', 'synthetic', '--output', str(self.out)),
                     ('--db', str(self.db), 'export-normalized', '--output', str(self.out))]:
            r = subprocess.run([sys.executable, 'recap.py', *args], cwd=ROOT, capture_output=True)
            self.assertNotEqual(r.returncode, 0)


if __name__ == '__main__':
    unittest.main()
