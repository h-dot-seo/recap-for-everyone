"""Bounded same-handle ZIP validation, not an immutable snapshot guarantee."""
import hashlib
import io
from pathlib import Path
import tempfile
import re
import shlex
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile
from recaplib import prepare_web_export as p
from recaplib.errors import SourceChanged
from recaplib.inspect_web_zip import inspect_web_zip
from recaplib.zip_preflight import check_directory, check_directory_stream
from tests.test_zip_directory_preflight import archive_bytes, zip64


class TrackingStream(io.BytesIO):
    def __init__(self, raw):
        super().__init__(raw)
        self.read_sizes = []
    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class StreamingZipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic.zip'
        self.path.write_bytes(archive_bytes())
        self.output = Path(self.tmp.name) / 'output.json'

    def test_hash_reads_bounded_chunks_and_exact_digest(self):
        raw = b'x' * (3 * 1024 * 1024 + 7)
        stream = TrackingStream(raw)
        self.assertEqual(p._hash_archive_stream(stream), (hashlib.sha256(raw).hexdigest(), len(raw)))
        self.assertTrue(all(0 < n <= 1024 * 1024 for n in stream.read_sizes))

    def test_hash_ceiling_detects_one_extra_byte(self):
        stream = TrackingStream(b'x' * 18)
        with patch.object(p, 'MAX_ARCHIVE_BYTES', 17), self.assertRaises(ValueError):
            p._hash_archive_stream(stream)
        self.assertEqual(stream.tell(), 18)

    def test_same_handle_used_for_both_hashes_and_zipfile(self):
        original_hash = p._hash_archive_stream
        original_zip = zipfile.ZipFile
        hashes, handles = [], []
        def hashed(stream):
            hashes.append(stream)
            return original_hash(stream)
        def opened(stream, *args, **kwargs):
            handles.append(stream)
            return original_zip(stream, *args, **kwargs)
        for prepare in (False, True):
            hashes.clear(); handles.clear()
            with patch.object(p, 'archive_bytes', side_effect=AssertionError('whole archive allocation')), patch.object(p, '_hash_archive_stream', side_effect=hashed), patch.object(zipfile, 'ZipFile', side_effect=opened):
                if prepare:
                    p.prepare_web_export(self.path, 'conversations-0.json', self.output)
                else:
                    inspect_web_zip(self.path)
            self.assertEqual(len(hashes), 2)
            self.assertIs(hashes[0], hashes[1])
            self.assertIs(handles[0], hashes[0])
            self.assertTrue(hashes[0].closed)

    def test_expected_mismatch_precedes_directory_and_zip(self):
        with patch.object(p, 'check_directory_stream', side_effect=AssertionError('preflight')), patch.object(zipfile, 'ZipFile', side_effect=AssertionError('metadata')):
            with self.assertRaises(SourceChanged):
                p.prepare_web_export(self.path, 'conversations-0.json', self.output, '0' * 64)
        self.assertFalse(self.output.exists())

    def test_change_after_json_before_publish_fails_without_staging(self):
        original = p._normalize_bytes
        def normalize(*args, **kwargs):
            result = original(*args, **kwargs)
            self.path.write_bytes(b'changed after JSON')
            return result
        with patch.object(p, '_normalize_bytes', side_effect=normalize), patch.object(p.tempfile, 'mkstemp', side_effect=AssertionError('staging too early')):
            with self.assertRaises(SourceChanged):
                p.prepare_web_export(self.path, 'conversations-0.json', self.output)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [self.path])

    def test_final_growth_over_ceiling_is_source_changed(self):
        raw = self.path.read_bytes()
        with patch.object(p, 'MAX_ARCHIVE_BYTES', len(raw)):
            with self.assertRaises(SourceChanged):
                with p.checked_archive(self.path) as (stream, _, _):
                    self.path.write_bytes(raw + b'x')
        self.assertTrue(stream.closed)

    def test_parse_failure_closes_handle_and_does_not_stage(self):
        self.path.write_bytes(archive_bytes(content=b'not json'))
        handles = []
        original = p._hash_archive_stream
        def hashed(stream):
            handles.append(stream)
            return original(stream)
        with patch.object(p, '_hash_archive_stream', side_effect=hashed), patch.object(p.tempfile, 'mkstemp', side_effect=AssertionError('staging too early')):
            with self.assertRaisesRegex(ValueError, 'supported web export'):
                p.prepare_web_export(self.path, 'conversations-0.json', self.output)
        self.assertEqual(len(handles), 1)  # No success/final digest claimed after parsing failure.
        self.assertTrue(handles[0].closed)
        self.assertFalse(self.output.exists())

    def test_equal_hashes_are_not_an_immutable_snapshot(self):
        raw = self.path.read_bytes()
        with p.checked_archive(self.path) as (stream, digest, size):
            self.path.write_bytes(b'y' * len(raw))
            stream.seek(0)
            self.assertNotEqual(stream.read(), raw)
            self.path.write_bytes(raw)
        self.assertEqual((digest, size), (hashlib.sha256(raw).hexdigest(), len(raw)))
        self.assertTrue(stream.closed)

    def test_stream_directory_matches_bytes_and_bounds_reads(self):
        raw = archive_bytes()
        variants = [raw, archive_bytes(0), b'prefix' + raw, zip64(raw), b'prefix' + zip64(raw), raw[:-1], b'not zip']
        for data in variants:
            with self.subTest(length=len(data)):
                stream = TrackingStream(data)
                try:
                    expected = check_directory(data, 1000)
                except Exception as error:
                    with self.assertRaises(type(error)):
                        check_directory_stream(stream, len(data), 1000)
                else:
                    self.assertEqual(check_directory_stream(stream, len(data), 1000), expected)
                self.assertTrue(all(0 <= n <= 65557 for n in stream.read_sizes))

    def test_stream_truncation_fails_closed(self):
        raw = archive_bytes()
        with self.assertRaises(zipfile.BadZipFile):
            check_directory_stream(io.BytesIO(raw[:-10]), len(raw), 1000)

    def test_published_streaming_guide(self):
        blocks = re.findall(r'```sh\n(.*?)```', Path('docs/ZIP_STREAMING.md').read_text(), re.S)
        self.assertEqual(len(blocks), 1)
        for line in blocks[0].strip().splitlines():
            args = shlex.split(line)
            args[0] = sys.executable
            result = subprocess.run(args, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
