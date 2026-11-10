"""Synthetic schema inventory, SQL reference and read-only boundary tests."""
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from recaplib.archive import ingest, readonly
from recaplib import archive_schema
from recaplib.archive_schema import describe_schema
from recaplib.session_workflow import import_export, titles
from recaplib.title_review_state import review_state

ROOT = Path(__file__).resolve().parents[1]


class ArchiveSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'synthetic.sqlite'
        ingest(self.db, 'synthetic', ROOT / 'examples/conversations.jsonl')

    def populate(self):
        import_export(self.db, 'web', ROOT / 'examples/web-export.json', 'web')
        titles(self.db, 'web', 'synthetic-chat', 'Synthetic reviewed title', 0)
        lease = review_state(self.db, 'web', 'synthetic-chat')
        review_state(self.db, 'web', 'synthetic-chat', 'skipped', lease['state_revision'],
                     lease['expected_title_revision'], lease['expected_content_sha256'])

    def run_cli(self, path=None):
        return subprocess.run([sys.executable, 'recap.py', '--db', str(path or self.db), 'describe-schema'],
                              cwd=ROOT, capture_output=True, env=dict(os.environ, PYTHONIOENCODING='ascii'))

    def test_ingest_only_is_deterministic_readonly_and_creates_no_lazy_tables(self):
        before = self.db.read_bytes()
        one = describe_schema(self.db)
        self.assertEqual(one, describe_schema(self.db))
        self.assertEqual(before, self.db.read_bytes())
        self.assertEqual(one['schema'], 'recap.archive-describe.v1')
        self.assertEqual([t['name'] for t in one['tables']], ['artifacts', 'messages', 'messages_fts'])
        self.assertFalse(any(one['ledgers_present'].values()))
        self.assertEqual(one['user_version'], 0)
        self.assertEqual(one['fts_rows'], 2)
        self.assertEqual(one['legacy_only_provenance_rows'], 0)
        self.assertFalse(one['archive_mutation'])
        self.assertFalse(one['network_access'])
        self.assertFalse(one['contains_message_text'])
        self.assertNotIn(str(self.db), json.dumps(one))
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertEqual(json.loads(self.run_cli().stdout), one)
        self.assertEqual(before, self.db.read_bytes())

    def test_trace_is_one_read_snapshot_without_writes(self):
        self.populate()
        seen = []
        def traced(db):
            connection = readonly(db)
            connection.set_trace_callback(seen.append)
            return connection
        with patch.object(archive_schema, 'readonly', traced):
            describe_schema(self.db)
        self.assertEqual(seen[0], 'BEGIN')
        self.assertEqual(sum(sql == 'BEGIN' for sql in seen), 1)
        self.assertFalse(any(re.match(r'\s*(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|REPLACE)\b', sql, re.I) for sql in seen))

    def test_all_columns_match_document_and_sql_executes(self):
        self.populate()
        doc = (ROOT / 'docs/SCHEMA.md').read_text(encoding='utf-8')
        before = self.db.read_bytes()
        report = describe_schema(self.db)
        self.assertTrue(all(report['ledgers_present'].values()))
        self.assertEqual([t['name'] for t in report['tables']], sorted(archive_schema.ARCHIVE_TABLES))
        with closing(readonly(self.db)) as connection:
            for table in report['tables']:
                section = doc.split('### ' + table['name'] + '\n', 1)[1].split('\n### ', 1)[0].split('\n## ', 1)[0]
                columns = re.findall(r'^- `([^`]+)`:', section, re.M)
                actual = list(connection.execute('SELECT * FROM pragma_table_info(?) ORDER BY cid', (table['name'],)))
                self.assertEqual(columns, [r['name'] for r in actual], table['name'])
                self.assertEqual(table['columns'], [dict(name=r['name'], type=r['type'], notnull=bool(r['notnull']), pk=r['pk']) for r in actual])
            blocks = re.findall(r'```sql\n(.*?)```', doc, re.S)
            self.assertEqual(len(blocks), 3)
            rows = [connection.execute(sql).fetchall() for sql in blocks]
            self.assertIn('Synthetic reviewed title', [r['display_title'] for r in rows[0]])
            self.assertEqual(len(rows[1]), 4)
            self.assertEqual(len(rows[2]), 1)
        self.assertEqual(before, self.db.read_bytes())
        self.assertIn('messages_ai', report['triggers']['names'])
        self.assertIn('title_review_history_identity', report['indexes']['names'])

    def test_legacy_only_counts_use_all_six_null_safe_fields(self):
        self.populate()
        self.assertEqual(describe_schema(self.db)['legacy_only_provenance_rows'], 0)
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('INSERT INTO export_provenance VALUES(NULL,NULL,NULL,NULL,NULL,NULL)')
            c.execute('INSERT INTO export_occurrences VALUES(NULL,NULL,NULL,NULL,NULL,NULL)')
            c.execute("INSERT INTO export_provenance VALUES('synthetic','c','m','hash','line:2',NULL)")
            c.execute("INSERT INTO export_occurrences VALUES('synthetic','c','m','hash','line:1',NULL)")
            c.execute("INSERT INTO export_provenance VALUES('synthetic','c','n','hash','line:3','parent')")
            c.execute("INSERT INTO export_occurrences VALUES('synthetic','c','n','hash','line:3',NULL)")
        before = self.db.read_bytes()
        self.assertEqual(describe_schema(self.db)['legacy_only_provenance_rows'], 2)
        self.assertEqual(before, self.db.read_bytes())
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('DROP TABLE export_occurrences')
            total = c.execute('SELECT COUNT(*) FROM export_provenance').fetchone()[0]
        self.assertEqual(describe_schema(self.db)['legacy_only_provenance_rows'], total)

    def test_stale_fts_uses_docsize_not_external_content(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("INSERT INTO messages_fts(messages_fts) VALUES('delete-all')")
        report = describe_schema(self.db)
        self.assertEqual(report['fts_rows'], 0)
        counts = {t['name']: t['rows'] for t in report['tables']}
        self.assertEqual(counts['messages'], 2)
        self.assertEqual(counts['messages_fts'], 0)
        self.assertEqual(report['fts_rows_source'], 'messages_fts_docsize')

    def test_no_docsize_never_falls_back_to_messages(self):
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('DROP TRIGGER messages_ai')
            c.execute('DROP TABLE messages_fts')
            c.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(text, content='messages', content_rowid='message_pk', columnsize=0)")
        with patch.object(archive_schema, '_fts_rows', side_effect=AssertionError('must not use fallback')):
            report = describe_schema(self.db)
        self.assertIsNone(report['fts_rows'])
        self.assertIsNone(report['fts_rows_source'])
        self.assertIsNone(next(t['rows'] for t in report['tables'] if t['name'] == 'messages_fts'))

    def test_hostile_unknown_names_are_only_bounded_metadata(self):
        hostile = 'x"; DROP TABLE messages; --\n한국어'
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute('CREATE TABLE "' + hostile.replace('"', '""') + '" (private TEXT)')
            for i in range(25):
                c.execute('CREATE TABLE "synthetic_%02d" (private TEXT)' % i)
                c.execute('CREATE INDEX "synthetic_index_%02d" ON "synthetic_%02d"(private)' % (i, i))
                c.execute('CREATE TRIGGER "synthetic_trigger_%02d" AFTER INSERT ON "synthetic_%02d" BEGIN SELECT 1; END' % (i, i))
        before = self.db.read_bytes()
        seen = []
        def traced(db):
            c = readonly(db)
            c.set_trace_callback(seen.append)
            return c
        with patch.object(archive_schema, 'readonly', traced):
            report = describe_schema(self.db)
        self.assertEqual(len(report['unknown_tables']), 20)
        self.assertEqual(report['unknown_table_count'], 26)
        self.assertEqual(report['unknown_tables_omitted'], 6)
        self.assertTrue(all(t['recognized'] is False for t in report['unknown_tables']))
        self.assertEqual(len(report['indexes']['names']), 20)
        self.assertEqual(len(report['triggers']['names']), 20)
        self.assertEqual(report['triggers']['omitted_count'], 6)
        self.assertFalse(any('private' in sql or hostile in sql for sql in seen))
        self.assertEqual(before, self.db.read_bytes())
        with patch.object(archive_schema, 'MAX_DETAIL_ITEMS', 50):
            full = describe_schema(self.db)
        self.assertIn(hostile, [t['name'] for t in full['unknown_tables']])
        self.assertEqual(json.loads(json.dumps(full))['unknown_tables'], full['unknown_tables'])

    def test_output_byte_limit_refuses_before_stdout(self):
        before = self.db.read_bytes()
        with patch.object(archive_schema, 'MAX_OUTPUT_BYTES', 10):
            with self.assertRaisesRegex(ValueError, 'output byte limit'):
                describe_schema(self.db)
        self.assertEqual(before, self.db.read_bytes())

    def test_bad_inputs_fail_without_traceback_or_creating_paths(self):
        missing = Path(self.tmp.name) / 'missing.sqlite'
        bad = Path(self.tmp.name) / 'not-sqlite'
        bad.write_bytes(b'Synthetic non-SQLite file')
        unrelated = Path(self.tmp.name) / 'unrelated.sqlite'
        with closing(sqlite3.connect(unrelated)) as c:
            c.execute('CREATE TABLE synthetic (id INTEGER)')
        for path in (missing, bad, unrelated):
            result = self.run_cli(path)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b'')
            self.assertNotIn(b'Traceback', result.stderr)
        self.assertFalse(missing.exists())
        self.assertIn(b'archive lacks the expected tables', self.run_cli(unrelated).stderr)
        self.assertEqual(bad.read_bytes(), b'Synthetic non-SQLite file')

    def test_views_cannot_impersonate_required_tables(self):
        other = Path(self.tmp.name) / 'views.sqlite'
        with closing(sqlite3.connect(other)) as c, c:
            for name in ('artifacts', 'messages', 'messages_fts'):
                c.execute('CREATE VIEW ' + name + ' AS SELECT 1')
        with self.assertRaisesRegex(ValueError, 'archive lacks the expected tables'):
            describe_schema(other)

    def test_snapshot_remains_consistent_during_a_concurrent_commit(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('PRAGMA journal_mode=WAL')
        original_tables = archive_schema._tables
        def after_first_read(connection):
            found = original_tables(connection)
            with closing(sqlite3.connect(self.db)) as other, other:
                other.execute('CREATE TABLE synthetic_new (id INTEGER)')
                other.execute('DELETE FROM messages')
            return found
        with patch.object(archive_schema, '_tables', after_first_read):
            snapshot = describe_schema(self.db)
        self.assertEqual(next(t['rows'] for t in snapshot['tables'] if t['name'] == 'messages'), 2)
        self.assertEqual(snapshot['unknown_table_count'], 0)
        later = describe_schema(self.db)
        self.assertEqual(next(t['rows'] for t in later['tables'] if t['name'] == 'messages'), 0)
        self.assertEqual(later['unknown_table_count'], 1)

    def test_sql_uses_revision_order_and_keeps_legacy_only_rows(self):
        self.populate()
        with closing(sqlite3.connect(self.db)) as c, c:
            c.execute("UPDATE title_history SET changed_at='9999-12-31'")
            c.execute("INSERT INTO title_history(source,conversation,previous,title,changed_at) VALUES('web','synthetic-chat','old','','0001-01-01')")
            original = c.execute('SELECT * FROM export_provenance LIMIT 1').fetchone()
            c.execute('UPDATE export_provenance SET locator=? WHERE source=? AND conversation=? AND message=? AND original_hash=?',
                      ('synthetic-legacy-only', *original[:4]))
        blocks = re.findall(r'```sql\n(.*?)```', (ROOT / 'docs/SCHEMA.md').read_text(encoding='utf-8'), re.S)
        with closing(readonly(self.db)) as c:
            current = [dict(row) for row in c.execute(blocks[0])]
            self.assertEqual(next(row['display_title'] for row in current if row['source_id'] == 'web'), '')
            occurrences = [dict(row) for row in c.execute(blocks[1])]
            self.assertEqual(len(occurrences), 5)
            self.assertEqual(sum(row['locator'] == 'synthetic-legacy-only' for row in occurrences), 1)
            history = [dict(row) for row in c.execute(blocks[2])]
            self.assertLess(history[0]['id'], history[1]['id'])
        self.assertEqual(describe_schema(self.db)['legacy_only_provenance_rows'], 1)

    def test_byte_limit_failure_emits_no_partial_report(self):
        from recap import main
        from contextlib import redirect_stdout, redirect_stderr
        from io import StringIO
        out, err = StringIO(), StringIO()
        with patch.object(sys, 'argv', ['recap.py', '--db', str(self.db), 'describe-schema']), \
                patch.object(archive_schema, 'MAX_OUTPUT_BYTES', 1), redirect_stdout(out), redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 1)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('output byte limit', err.getvalue())

    def test_documented_sh_block_executes_exactly(self):
        doc = (ROOT / 'docs/SCHEMA.md').read_text(encoding='utf-8')
        blocks = re.findall(r'```sh\n(.*?)```', doc, re.S)
        self.assertEqual(len(blocks), 1)
        for line in blocks[0].splitlines():
            tokens = shlex.split(line)
            self.assertEqual(tokens[0], 'python')
            args = [t.replace('OUTPUT', self.tmp.name) for t in tokens[1:]]
            result = subprocess.run([sys.executable] + args, cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['schema'], 'recap.archive-describe.v1')
        self.assertFalse(any(json.loads(result.stdout)['ledgers_present'].values()))


if __name__ == '__main__':
    unittest.main()
