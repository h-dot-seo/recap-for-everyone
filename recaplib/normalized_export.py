"""Stream a derived, text-only normalized JSONL copy from one read snapshot."""
import hashlib
import json

from recaplib.archive import readonly, _validate_source
from recaplib.recovery import _publish_new_chunks, _reject_existing

FIELDS = ('conversation_id', 'message_id', 'role', 'timestamp', 'title', 'text')


def export_normalized(db, source, output, conversation=None):
    _validate_source(source)
    if conversation is not None and (not isinstance(conversation, str) or not conversation or
            any(0xd800 <= ord(c) <= 0xdfff for c in conversation)):
        raise ValueError('conversation must be nonempty valid Unicode text')
    _reject_existing(output)
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        where, params = 'source_id=?', (source,)
        if conversation is not None:
            where += ' AND conversation_id=?'
            params += (conversation,)
        counts = connection.execute('SELECT COUNT(*),COUNT(DISTINCT conversation_id) '
                                    'FROM messages WHERE ' + where, params).fetchone()
        if not counts[0]:
            raise ValueError('unknown or empty source or conversation')
        tables = [name for name in ('export_provenance', 'export_occurrences')
                  if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                        (name,)).fetchone()]
        omitted = 0
        if tables:
            selection = 'source=?' + (' AND conversation=?' if conversation is not None else '')
            union = ' UNION '.join('SELECT source,conversation,message,original_hash,locator,parent '
                                  'FROM ' + name + ' WHERE ' + selection for name in tables)
            omitted = connection.execute('SELECT COUNT(*) FROM (' + union + ') p WHERE EXISTS '
                '(SELECT 1 FROM messages m WHERE m.source_id=p.source AND '
                'm.conversation_id=p.conversation AND m.message_id=p.message)',
                params * len(tables)).fetchone()[0]
        digest = hashlib.sha256()
        totals = dict(records=0, bytes=0)

        def chunks():
            rows = connection.execute('SELECT ' + ','.join(FIELDS) +
                                      ' FROM messages WHERE ' + where + ' ORDER BY message_pk', params)
            for row in rows:
                record = dict(row)
                # Fail closed for manually damaged rows; use the ingest record predicate
                # without buffering the source or opening a second writable archive.
                if (any(not isinstance(record[k], str) or not record[k]
                        for k in FIELDS if k != 'title') or
                        not isinstance(record['title'], str) or
                        record['role'] not in ('user', 'assistant', 'system', 'tool')):
                    raise ValueError('archive row is not an ingestible normalized message')
                raw = (json.dumps(record, ensure_ascii=False, allow_nan=False,
                                  separators=(', ', ': ')) + '\n').encode('utf-8')
                digest.update(raw)
                totals['records'] += 1
                totals['bytes'] += len(raw)
                yield raw

        publication = _publish_new_chunks(output, chunks(), '.recap-normalized-export-')
        return dict(schema='recap.normalized-export-receipt.v1', **totals,
            conversations=counts[1], sha256=digest.hexdigest(), **publication,
            derived=True, original_export=False, contains_message_text=True,
            receipt_contains_message_text=False, export_provenance_exported=False,
            omitted_export_occurrences=omitted, display_titles_included=False,
            title_history_included=False, review_state_included=False,
            source_bytes_reproduced=False, archive_mutation=False, network_access=False,
            message_order='archive insertion order',
            branch_scope='all imported text nodes; not an active-branch reconstruction',
            scope='one read-only snapshot of one source, optionally one conversation; text-only JSONL',
            boundary='The SHA-256 hashes only this derived file, not an archive artifact or original '
                     'export identity. No original hashes, locators, parent tree, local title history '
                     'or review state are exported. This is not a backup or recovery object for '
                     'the source archive. Re-ingest records this file hash and line as new provenance.',
            warning='PRIVATE FILE: output contains full message text, original titles and identities. '
                    'Keep the file and receipt outside public repositories and shared folders.')
    finally:
        connection.close()
