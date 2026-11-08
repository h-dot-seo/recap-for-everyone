"""Check Python and in-memory SQLite FTS5 without opening exports or archives."""
import argparse
from contextlib import closing
import importlib
import json
import sys


MINIMUM_PYTHON = (3, 10)


def check_runtime():
    version = tuple(sys.version_info[:3])
    result = dict(schema='recap.runtime-check.v1', status='UNSUPPORTED_RUNTIME',
        python=dict(version='.'.join(map(str, version)), minimum='3.10',
                    supported=version[:2] >= MINIMUM_PYTHON),
        sqlite=dict(available=None, version=None, fts5_probe='NOT_RUN'),
        reason_codes=[], archive_access=False, network_access=False,
        scope='this interpreter and one synthetic in-memory FTS5 round trip only',
        limitations='Not a full test suite, checkout verification, shell-encoding check, filesystem-permission check or export-compatibility guarantee.')
    if not result['python']['supported']:
        result['reason_codes'].append('PYTHON_TOO_OLD')
        return result
    try:
        sqlite = importlib.import_module('sqlite3')
    except (ImportError, OSError):
        # Missing extensions/DLLs must not expose machine-specific error paths.
        result['sqlite']['available'] = False
        result['reason_codes'].append('SQLITE_IMPORT_UNAVAILABLE')
        return result
    result['sqlite'].update(available=True, version=sqlite.sqlite_version)
    try:
        with closing(sqlite.connect(':memory:')) as connection:
            connection.execute('CREATE VIRTUAL TABLE runtime_probe USING fts5(text)')
            connection.execute('INSERT INTO runtime_probe(text) VALUES(?)', ('synthetic runtime probe',))
            row = connection.execute('SELECT text FROM runtime_probe WHERE runtime_probe MATCH ?',
                                     ('synthetic',)).fetchone()
        if row != ('synthetic runtime probe',):
            result['sqlite']['fts5_probe'] = 'FAIL'
            result['reason_codes'].append('FTS5_UNEXPECTED_RESULT')
            return result
    except sqlite.Error:
        # Failure may mean missing FTS5 or another SQLite/runtime problem. Do
        # not infer a specific repair, load extensions or fall back to a file DB.
        result['sqlite']['fts5_probe'] = 'FAIL'
        result['reason_codes'].append('SQLITE_FTS5_PROBE_FAILED')
        return result
    result['sqlite']['fts5_probe'] = 'PASS'
    result['status'] = 'READY'
    return result


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = check_runtime()
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['status'] == 'READY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
