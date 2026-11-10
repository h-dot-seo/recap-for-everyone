"""Bounded synthetic nesting probes, never a production input limit."""
import json
import unittest
from functools import lru_cache

from recaplib.title_batch import MAX_SUPPLIED_BYTES

# Leave room for synthetic record wrappers, BOMs and metadata. A doubled failing
# depth must still fit the smallest reader budget exercised by these fixtures.
MAX_DEPTH = (MAX_SUPPLIED_BYTES - 4096) // 2


def nested(depth):
    return '[' * depth + '"SYNTHETIC_PRIVATE_VALUE"' + ']' * depth


@lru_cache(maxsize=1)
def decoder_failure_depth():
    depth = min(10000, MAX_DEPTH // 2)
    while True:
        try:
            json.loads(nested(depth))
        except RecursionError:
            return 2 * depth
        if depth == MAX_DEPTH // 2:
            raise unittest.SkipTest('decoder accepted every probed depth up to the byte limit')
        depth = min(2 * depth, MAX_DEPTH // 2)


def deep_json():
    return nested(decoder_failure_depth())
