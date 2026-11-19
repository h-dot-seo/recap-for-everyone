"""Stream a derived, text-only normalized JSONL copy from one read snapshot."""
import hashlib
import json

from recaplib.archive import readonly, _validate_source
from recaplib.import_checkpoint import read_checkpoint, verify_cutoff
from recaplib.recovery import _publish_new_chunks, _reject_existing

FIELDS = ('conversation_id', 'message_id', 'role', 'timestamp', 'title', 'text')


def _checkpoint_filter(connection, source, since, through):
    """Verify the cutoffs before exposing their row predicates to export queries."""
    if since is None and through is None:
        return '', {}
    columns = '(m.conversation_id,m.message_id,m.source_sha256)'
    receipt = dict(schema='recap.normalized-export-receipt.v2', checkpoint_status='CUTOFF_VERIFIED')
    predicates = {}
    for name, checkpoint in (('since', since), ('through', through)):
        if checkpoint is None:
            continue
        verified = verify_cutoff(connection, checkpoint)
        if verified is None:
            raise ValueError('import checkpoint cutoff could not be verified')
        function = 'recap_after_' + name
        connection.create_function(function, 3, verified.is_after)
        predicates[name] = function + columns
        receipt[name + '_checkpoint_schema'] = checkpoint['schema']

    if since is not None and through is not None:
        # Compare the whole source, even when exporting just one conversation.
        upper_artifacts = {row['sha256'] for row in through['artifacts']}
        if (any(row['sha256'] not in upper_artifacts for row in since['artifacts']) or
                connection.execute('SELECT 1 FROM messages m WHERE m.source_id=? AND NOT ' +
                                   predicates['since'] + ' AND ' + predicates['through'] + ' LIMIT 1',
                                   (source,)).fetchone()):
            raise ValueError('starting checkpoint must be contained in ending checkpoint')
    clause = ''
    if since is not None:
        clause += ' AND ' + predicates['since']
    if through is not None:
        clause += ' AND NOT ' + predicates['through']
    return clause, receipt


def export_normalized(db, source, output, conversation=None, *, since_checkpoint=None, through_checkpoint=None):
    _validate_source(source)
    if conversation is not None and (not isinstance(conversation, str) or not conversation or
            any(0xd800 <= ord(c) <= 0xdfff for c in conversation)):
        raise ValueError('conversation must be nonempty valid Unicode text')
    _reject_existing(output)
    since = read_checkpoint(since_checkpoint, source) if since_checkpoint is not None else None
    through = read_checkpoint(through_checkpoint, source) if through_checkpoint is not None else None
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        where, params = 'source_id=?', (source,)
        if conversation is not None:
            where += ' AND conversation_id=?'
            params += (conversation,)
        cutoff_filter, cutoff_receipt = _checkpoint_filter(connection, source, since, through)
        counts = connection.execute('SELECT COUNT(*),COUNT(DISTINCT conversation_id) '
                                    'FROM messages m WHERE ' + where + cutoff_filter, params).fetchone()
        if not counts[0]:
            if cutoff_receipt and (conversation is None or connection.execute(
                    'SELECT 1 FROM messages WHERE ' + where + ' LIMIT 1', params).fetchone()):
                return dict(**cutoff_receipt, status='NO_NEW_MESSAGES', published=False,
                            records=0, conversations=0, receipt_contains_message_text=False,
                            archive_mutation=False, network_access=False)
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
                'm.conversation_id=p.conversation AND m.message_id=p.message' + cutoff_filter + ')',
                params * len(tables)).fetchone()[0]
        digest = hashlib.sha256()
        totals = dict(records=0, bytes=0)

        def chunks():
            rows = connection.execute('SELECT ' + ','.join(FIELDS) +
                                      ' FROM messages m WHERE ' + where + cutoff_filter + ' ORDER BY message_pk', params)
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
        receipt = dict(schema='recap.normalized-export-receipt.v1', **totals,
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
        if cutoff_receipt:
            receipt.update(cutoff_receipt, status='EXPORTED', published=True,
                           scope='accepted messages selected by verified source checkpoints in one '
                                 'read-only snapshot, optionally one conversation; text-only JSONL')
        return receipt
    finally:
        connection.close()
