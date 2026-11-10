"""Save one generated title JSON document without overwriting existing paths."""
import hashlib
import json
# Retain these module aliases for existing failure-injection test patch points.
# Both modules reference the same os/tempfile objects and Path class.
import os
from pathlib import Path
import tempfile
from recaplib.document_output import write_bytes


def add_output_argument(parser):
    parser.add_argument('--output', dest='title_output', metavar='NEW_JSON',
                        help='save UTF-8 JSON to a new file without overwriting; stdout contains a receipt only')


def write_title_json(value, output, kind):
    if kind not in ('proposal', 'preview', 'queue', 'request') or not isinstance(value, dict):
        raise ValueError('title output requires a document object and supported kind')
    try:
        raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError('title output must contain valid finite JSON data') from None
    staging = write_bytes(raw, output, '.recap-title-')
    return dict(schema='recap.saved-title-json.v1', status='SAVED', document_kind=kind,
                encoding='UTF-8', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                **staging,
                scope='new local JSON file only; no archive mutation or approval',
                warning=('PRIVATE REQUEST FILE. This receipt is not the request or permission to send data. Review the saved request before separately authorized use. Saving does not run a provider or transmit data. If staging cleanup failed, the complete output already exists; inspect the leftover file rather than blindly retrying.'
                         if kind == 'request' else
                         'PRIVATE FILE. Review the saved document, not this receipt, before a separate explicit apply. If staging cleanup failed, the complete output already exists; inspect the leftover file rather than blindly retrying.'))


def save_if_requested(value, args, kind):
    output = getattr(args, 'title_output', None)
    return value if output is None else write_title_json(value, output, kind)
