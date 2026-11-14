"""Explicit domain errors and opt-in CLI envelopes, not diagnosis."""
import sqlite3
import json
from recaplib.cli_errors import safe_diagnostic


class RecapError(ValueError):
    code = 'UNCLASSIFIED'


class SourceChanged(RecapError):
    code = 'SOURCE_CHANGED'


class Stale(RecapError):
    code = 'STALE'


class UnknownIdentity(RecapError):
    code = 'UNKNOWN_IDENTITY'


class ConflictingIdentity(RecapError):
    code = 'CONFLICTING_IDENTITY'


class PathUnavailable(RecapError):
    code = 'PATH_UNAVAILABLE'


class CurrentNodeUnavailable(RecapError):
    code = 'CURRENT_NODE_UNAVAILABLE'


def error_document(error):
    """Describe only explicit exception types at the existing caught boundary."""
    if isinstance(error, RecapError):
        code = error.code
    elif isinstance(error, FileExistsError):
        code = 'OUTPUT_EXISTS'
    elif isinstance(error, OSError):
        code = 'FILE_ERROR'
    elif isinstance(error, sqlite3.Error):
        code = 'ARCHIVE_ERROR'
    else:
        code = 'UNCLASSIFIED'
    return dict(schema='recap.error.v1', code=code,
                message=safe_diagnostic(error), exit_status=1)


def add_json_errors_argument(parser):
    """Opt in only at existing execution-error boundaries, never argparse usage."""
    parser.add_argument('--json-errors', action='store_true',
                        help='emit structured stderr for caught execution failures only; usage and result failures are unchanged')


def exit_error(parser, args, error):
    """Preserve legacy diagnostics unless explicitly requested otherwise."""
    message=json.dumps(error_document(error),ensure_ascii=True) if args.json_errors else safe_diagnostic(error)
    parser.exit(1,message+'\n')


def exit_adapter_error(parser, args, code):
    """Adapter's existing symbolic code is its whole diagnostic, not a cause."""
    message=json.dumps(dict(schema='recap.error.v1',code=code,message=code,exit_status=1),
                       ensure_ascii=True) if args.json_errors else code
    parser.exit(1,message+'\n')
