"""Save one generated title JSON document without overwriting existing paths."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


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
    destination = Path(output)
    parent = destination.parent.resolve(strict=True)
    destination = parent / destination.name
    temporary = None
    published = False
    cleanup_complete = True
    try:
        # Close the private same-directory staging file before linking on Windows.
        # Hard-link publication is atomic and refuses files, directories and
        # symlinks already at the destination. Never fall back to replacement.
        with tempfile.NamedTemporaryFile(prefix='.recap-title-', dir=parent, delete=False) as stream:
            temporary = Path(stream.name)
            if stream.write(raw) != len(raw):
                raise OSError('incomplete title document write')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        published = True
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                if not published:
                    raise
                cleanup_complete = False
    return dict(schema='recap.saved-title-json.v1', status='SAVED', document_kind=kind,
                encoding='UTF-8', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                staging_cleanup_complete=cleanup_complete,
                remaining_staging_file=temporary.name if not cleanup_complete else None,
                scope='new local JSON file only; no archive mutation or approval',
                warning=('PRIVATE REQUEST FILE. This receipt is not the request or permission to send data. Review the saved request before separately authorized use. Saving does not run a provider or transmit data. If staging cleanup failed, the complete output already exists; inspect the leftover file rather than blindly retrying.'
                         if kind == 'request' else
                         'PRIVATE FILE. Review the saved document, not this receipt, before a separate explicit apply. If staging cleanup failed, the complete output already exists; inspect the leftover file rather than blindly retrying.'))


def save_if_requested(value, args, kind):
    output = getattr(args, 'title_output', None)
    return value if output is None else write_title_json(value, output, kind)
