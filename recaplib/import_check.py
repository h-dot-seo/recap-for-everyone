"""Read-only import conflict diagnostics; never repairs or imports evidence."""
from recaplib.errors import add_json_errors_argument, exit_error
from recaplib.cli_errors import safe_diagnostic
import argparse
import json
import hashlib
import sqlite3

from recaplib.archive import _validate_source, readonly
from recaplib.session_workflow import normalize, inspect_normalized

FIELDS = ('role', 'timestamp', 'title', 'text')
MAX_DELTA_BYTES = 8 * 1024 * 1024
DELTA_CATEGORIES = ('conflicting', 'new', 'has_new_identities', 'no_new_identities')


def check_import(db, source, path, kind, conversation=None, expected_export_sha256=None, limit=20, delta_output=None):
    _validate_source(source)
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer in 1..1000')
    if delta_output is not None:
        from recaplib.recovery import _reject_existing, _publish_new_file
        _reject_existing(delta_output)
    if kind == 'normalized':
        rows, coverage = inspect_normalized(path, conversation, expected_export_sha256)
    else:
        rows, coverage = normalize(path, kind, include_report=True, conversation=conversation,
                                   expected_export_sha256=expected_export_sha256)
    archive_counts = dict(new=0, identical=0, conflicting=0)
    repeated = dict(identical=0, conflicting=0)
    classes = dict(title_only=0, text_changed=0, metadata_changed=0)
    samples, seen = [], {}
    conversation_flags = {}

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
        archived_conversations = {row[0] for row in connection.execute(
            'SELECT conversation_id FROM messages WHERE source_id=? GROUP BY conversation_id COLLATE BINARY', (source,))}
        for index, row in enumerate(rows, 1):
            key = (row['conversation_id'], row['message_id'])
            flags = conversation_flags.setdefault(key[0], dict(conflicting=False, new_identity=False))
            values = tuple(row.get(field, '') for field in FIELDS)
            if key in seen:
                first_record, first_values = seen[key]
                if values == first_values:
                    repeated['identical'] += 1
                else:
                    repeated['conflicting'] += 1
                    flags['conflicting'] = True
                    conflict(index, values, first_values, 'input', first_record)
                continue
            seen[key] = (index, values)
            previous = connection.execute(
                'SELECT role,timestamp,title,text FROM messages '
                'WHERE source_id=? AND conversation_id=? AND message_id=?', (source, *key)).fetchone()
            if previous is None:
                archive_counts['new'] += 1
                flags['new_identity'] = True
            elif tuple(previous) == values:
                archive_counts['identical'] += 1
            else:
                archive_counts['conflicting'] += 1
                flags['conflicting'] = True
                conflict(index, values, tuple(previous), 'archive')
    finally:
        connection.close()
    total = sum(classes.values())
    buckets = {category: [] for category in DELTA_CATEGORIES}
    for identity, flags in sorted(conversation_flags.items()):
        category = ('conflicting' if flags['conflicting'] else
                    'new' if identity not in archived_conversations else
                    'has_new_identities' if flags['new_identity'] else 'no_new_identities')
        buckets[category].append(identity)
    delta = dict(conversations=len(conversation_flags),
                 counts={category: len(ids) for category, ids in buckets.items()},
                 scope='incoming conversations after selection only; mutually exclusive priority: conflicting, new, has_new_identities, no_new_identities; same read-only source snapshot',
                 semantics='identity comparison, not growth, activity, review completion or import authorization; derived local IDs can change with filenames; new identities can represent edited branches; archive-only conversations are not classified')
    result = dict(status='CONFLICTS' if total else 'NO_CONFLICTS', conflicts_found=bool(total),
        records=len(rows), unique_identities=len(seen), archive_comparison=archive_counts,
        repeated_input=repeated, conflict_classifications=classes, total_conflicts=total,
        conflict_samples=samples, omitted_conflicts=total-len(samples), limit=limit, coverage=coverage,
        comparison_scope='first incoming occurrence per identity against this archive source; repeats against their first incoming occurrence',
        record_locator='1-based normalized message occurrence after optional conversation selection, not physical source line',
        scope='one read-only archive snapshot; no database creation, import, repair or title change',
        conversation_delta=delta,
        warning='Advisory only, not import authorization or a guarantee. The importer rechecks under its write lock. Title-only conflicts still block import. Samples omit message IDs, titles and bodies; selection coverage may include a private conversation ID.')


    if delta_output is not None:
        document = dict(schema='recap.import-conversation-delta.v1', source=source,
                        status=result['status'], conflicts_found=result['conflicts_found'],
                        conversation_delta=delta, sample_limit_per_category=limit,
                        samples={category: ids[:limit] for category, ids in buckets.items()},
                        omitted={category: max(0, len(ids)-limit) for category, ids in buckets.items()},
                        archive_mutation=False, remote_mutation=False, contains_message_text=False,
                        warning='PRIVATE CONVERSATION IDS. Unsigned advisory snapshot comparison, not authorization, completeness or a checkpoint. Import rechecks under its write lock.')
        raw = (json.dumps(document, ensure_ascii=True, sort_keys=True, indent=2)+'\n').encode('utf-8')
        if len(raw) > MAX_DELTA_BYTES:
            raise ValueError('delta document exceeds byte limit; reduce --limit')
        publication = _publish_new_file(delta_output, raw, '.recap-import-delta-')
        result['delta_document'] = dict(schema=document['schema'], bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(), **publication,
            warning='Private conversation IDs were written to the explicitly selected new file.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_json_errors_argument(parser)
    parser.add_argument('--db', required=True)
    parser.add_argument('input')
    parser.add_argument('--source', required=True)
    parser.add_argument('--format', choices=['web', 'local', 'local-codex', 'normalized'], required=True)
    parser.add_argument('--conversation')
    parser.add_argument('--expected-export-sha256')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--delta-output', help='exclusive new private file for bounded conversation delta ID samples')
    args = parser.parse_args()
    try:
        result = check_import(args.db, args.source, args.input, args.format, args.conversation,
                              args.expected_export_sha256, args.limit, args.delta_output)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        exit_error(parser, args, error)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if result['conflicts_found']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
