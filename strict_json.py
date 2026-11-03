"""JSON decoding that refuses ambiguous duplicate object members."""
import json


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            # Do not echo potentially private key names or values in diagnostics.
            raise ValueError('duplicate JSON object key')
        result[key] = value
    return result


def loads(text):
    return json.loads(text, object_pairs_hook=_unique_object)
