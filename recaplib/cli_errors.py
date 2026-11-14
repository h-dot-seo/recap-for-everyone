"""Fixed diagnostics for selected already-caught low-level CLI exceptions.

This does not catch exceptions, sanitize arbitrary application messages, or
change successful/result-level failure output. Application-owned messages and
adapter error codes retain their existing contracts.
"""
import json
import sqlite3


# Only exact code-authored messages, with no OS errno/path fields, retain their
# existing CLI contract. Arbitrary OSError messages remain suppressed.
_FIXED_OS_MESSAGES = frozenset((
    'output path already exists; choose a new file name',
    'incomplete recovery document write',
    'incomplete document write',
    'rebuilt database was published; receipt publication failed; database was preserved; '
    'inspect the requested new database before retrying',
))


def safe_diagnostic(error):
    """Classify observed exception kinds only; never guess a failing resource."""
    if isinstance(error, json.JSONDecodeError):
        return 'JSON decoding failed'
    if isinstance(error, UnicodeDecodeError):
        return 'Text decoding failed'
    if isinstance(error, sqlite3.Error):
        if error.args == ('read-only SQLite protections could not be enabled',):
            return 'read-only SQLite protections could not be enabled'
        return 'SQLite operation failed'
    if isinstance(error, OSError):
        if (error.errno is None and error.filename is None and error.filename2 is None and
                len(error.args) == 1 and isinstance(error.args[0], str) and error.args[0] in _FIXED_OS_MESSAGES):
            return error.args[0]
        return 'Filesystem operation failed'
    return str(error)
