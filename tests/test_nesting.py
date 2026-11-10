"""Synthetic tests of the bounded test-only nesting probe."""
import json
import sys
import unittest
from unittest.mock import patch

from tests import _nesting
from recaplib.title_batch import MAX_SUPPLIED_BYTES


class NestingProbeTests(unittest.TestCase):
    def setUp(self):
        _nesting.decoder_failure_depth.cache_clear()
        self.addCleanup(_nesting.decoder_failure_depth.cache_clear)

    def test_fixture_is_valid_json_at_shallow_depth(self):
        self.assertEqual(json.loads(_nesting.nested(2)), [['SYNTHETIC_PRIVATE_VALUE']])

    def test_failure_is_doubled_and_cached_without_changing_recursion_limit(self):
        before = sys.getrecursionlimit()
        with patch.object(_nesting.json, 'loads', side_effect=RecursionError) as read:
            self.assertEqual(_nesting.decoder_failure_depth(), 20000)
            self.assertEqual(_nesting.decoder_failure_depth(), 20000)
            self.assertEqual(read.call_count, 1)
        self.assertEqual(sys.getrecursionlimit(), before)

    def test_accepted_cap_skips_only_the_runtime_dependent_fixture(self):
        with patch.object(_nesting.json, 'loads', return_value=None) as read:
            with self.assertRaisesRegex(unittest.SkipTest, 'up to the byte limit'):
                _nesting.decoder_failure_depth()
        sizes = [len(call.args[0].encode()) for call in read.call_args_list]
        self.assertEqual(sizes, sorted(set(sizes)))
        self.assertLess(max(sizes) * 2, MAX_SUPPLIED_BYTES)

    def test_failure_at_probe_cap_still_leaves_room_for_wrappers_and_bom(self):
        def decode(text):
            if len(text) >= len(_nesting.nested(_nesting.MAX_DEPTH // 2)):
                raise RecursionError
        with patch.object(_nesting.json, 'loads', side_effect=decode):
            fixture = _nesting.deep_json()
        self.assertLess(len(fixture.encode()) + 2048, MAX_SUPPLIED_BYTES)
