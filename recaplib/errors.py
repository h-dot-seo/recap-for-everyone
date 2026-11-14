"""Explicit domain errors and an opt-in unified CLI envelope, not diagnosis."""
import sqlite3
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
