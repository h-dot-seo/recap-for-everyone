"""JSON decoding that refuses duplicate members and non-Unicode string data."""
import json
import re


_SURROGATE = re.compile(r'[\ud800-\udfff]')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            # Do not echo potentially private key names or values in diagnostics.
            raise ValueError('duplicate JSON object key')
        result[key] = value
    return result


def loads(text):
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
    except RecursionError:
        # Let existing ValueError boundaries report a clean source error. Do not
        # echo JSON fragments or raise the interpreter's recursion limit.
        raise ValueError('JSON nesting is too deep') from None
    # json.loads already joins valid escaped UTF-16 pairs. Any remaining
    # surrogate is not a Unicode scalar and cannot be stored safely as UTF-8.
    # Check all keys/values before callers create an archive or report inspection
    # success. Use an iterative walk rather than adding another recursion limit.
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if _SURROGATE.search(current):
                raise ValueError('JSON strings must not contain unpaired surrogates')
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return value
