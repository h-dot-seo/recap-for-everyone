#!/usr/bin/env python3
"""Local-only archive import, inspection, search and checked title workflows."""
import sqlite3
from recaplib.archive import SCHEMA, _validate_source, ingest, ingest_bytes, readonly, search, validate_normalized
from recaplib.cli import build_parser, _run


def main(prog=None):
    """Checkout compatibility entry point with live archive re-exports."""
    return _run(prog, (ingest, search, readonly))


if __name__ == '__main__':
    main()
