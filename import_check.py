"""Read-only import conflict diagnostics; never repairs or imports evidence."""
import argparse
import json
import sqlite3

from recap import readonly
from session_workflow import normalize

FIELDS = ('role', 'timestamp', 'title', 'text')


def check_import(db, source, path, kind, conversation=None, expected_export_sha256=None, limit=20):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('source must not be empty')
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer in 1..1000')
    rows, coverage = normalize(path, kind, include_report=True, conversation=conversation,
                               expected_export_sha256=expected_export_sha256)
    archive_counts = dict(new=0, identical=0, conflicting=0)
    repeated = dict(identical=0, conflicting=0)
    classes = dict(title_only=0, text_changed=0, metadata_changed=0)
    samples, seen = [], {}

    def conflict(record, current, previous, comparison, first_record=None):
        fields = [field for field, value, old in zip(FIELDS, current, previous) if value != old]
        category = ('title_only' if fields == ['title'] else 'text_changed' if 'text' in fields else 'metadata_changed')
        classes[category] += 1
        if len(samples) < limit:
            sample = dict(record=record, comparison=comparison, classification=category, changed_fields=fields)
            if first_record is not None:
                sample['first_record'] = first_record
            samples.append(sample)

    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        # Validate the existing archive's comparison columns even for empty input.
        connection.execute('SELECT role,timestamp,title,text FROM messages LIMIT 0')
        for index, row in enumerate(rows, 1):
            key = (row['conversation_id'], row['message_id'])
            values = tuple(row.get(field, '') for field in FIELDS)
            if key in seen:
                first_record, first_values = seen[key]
                if values == first_values:
                    repeated['identical'] += 1
                else:
                    repeated['conflicting'] += 1
                    conflict(index, values, first_values, 'input', first_record)
                continue
            seen[key] = (index, values)
            previous = connection.execute(
                'SELECT role,timestamp,title,text FROM messages '
                'WHERE source_id=? AND conversation_id=? AND message_id=?', (source, *key)).fetchone()
            if previous is None:
                archive_counts['new'] += 1
            elif tuple(previous) == values:
                archive_counts['identical'] += 1
            else:
                archive_counts['conflicting'] += 1
                conflict(index, values, tuple(previous), 'archive')
    finally:
        connection.close()
    total = sum(classes.values())
    return dict(status='CONFLICTS' if total else 'NO_CONFLICTS', conflicts_found=bool(total),
        records=len(rows), unique_identities=len(seen), archive_comparison=archive_counts,
        repeated_input=repeated, conflict_classifications=classes, total_conflicts=total,
        conflict_samples=samples, omitted_conflicts=total-len(samples), limit=limit, coverage=coverage,
        comparison_scope='first incoming occurrence per identity against this archive source; repeats against their first incoming occurrence',
        record_locator='1-based normalized message occurrence after optional conversation selection, not physical source line',
        scope='one read-only archive snapshot; no database creation, import, repair or title change',
        warning='Advisory only, not import authorization or a guarantee. The importer rechecks under its write lock. Title-only conflicts still block import. Samples omit message IDs, titles and bodies; selection coverage may include a private conversation ID.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('input')
    parser.add_argument('--source', required=True)
    parser.add_argument('--format', choices=['web', 'local', 'local-codex'], required=True)
    parser.add_argument('--conversation')
    parser.add_argument('--expected-export-sha256')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    try:
        result = check_import(args.db, args.source, args.input, args.format, args.conversation,
                              args.expected_export_sha256, args.limit)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if result['conflicts_found']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
