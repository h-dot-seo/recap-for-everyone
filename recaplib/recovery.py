"""Declare a live archive for backup and rehearse recovery of a restored copy read-only."""
from recaplib.cli_errors import safe_diagnostic
import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import unicodedata
from pathlib import Path

from recaplib.archive import readonly
from recaplib.input_files import require_regular_file
from recaplib.source_text import decode_source
from recaplib.strict_json import loads
from recaplib.text_summary import summary_text

MANIFEST_SCHEMA = 'recap.recovery-manifest.v1'
DECLARATION_SCHEMA = 'recap.recovery-declaration.v1'
RECEIPT_SCHEMA = 'recap.recovery-receipt.v1'
PASSED = 'RECOVERY_REHEARSAL_PASSED'
FAILED = 'RECOVERY_REHEARSAL_FAILED'
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_OBJECT_FILES = 10000
MAX_OBJECT_BYTES = 1024 * 1024 * 1024
MAX_SAMPLED_MESSAGES = 100
MAX_DETAIL_ITEMS = 20
EXPECTED_TABLES = ('artifacts', 'messages', 'messages_fts')
CHECKS = ('integrity_check', 'expected_tables', 'artifact_rows', 'source_counts', 'messages_digest',
          'export_occurrences', 'title_history', 'fts_rows', 'fts_match_sample')
OBJECTS_CHECK = 'declared_objects'
MANIFEST_FIELDS = ('schema', 'declared_at', 'sources', 'artifacts', 'optional_artifacts', 'messages', 'conversations',
                   'messages_sha256', 'export_occurrences', 'title_history', 'fts_rows',
                   'digest_semantics', 'scope', 'boundary')
SOURCE_FIELDS = ('source_id', 'artifacts', 'messages', 'conversations', 'export_occurrences', 'original_hashes')
ARTIFACT_FIELDS = ('source_id', 'sha256', 'bytes', 'record_count')
NOT_RUN = 'not run: the restored archive could not be opened or did not pass integrity_check'
DIGEST_SEMANTICS = ('messages_sha256: SHA-256 over one line per messages row; each line is the compact ASCII '
                    'JSON array [source_id, conversation_id, message_id, role, timestamp, title, text, '
                    'source_sha256, source_line] followed by LF, rows ordered by source_id, conversation_id '
                    'and message_id under SQLite BINARY collation. title_history.sha256: the same construction '
                    'over [source, conversation, previous, title, changed_at] ordered by those five columns; '
                    'the revision id is excluded. fts_rows counts rows held by the messages_fts index '
                    '(its docsize shadow table), not the content table. Counts and digests describe logical '
                    'rows, never archive file bytes, page layout or journal state.')
MANIFEST_SCOPE = ('one read-only snapshot of the live archive: artifact rows, per-source message and '
                  'conversation counts, logical digests, optional export-occurrence and title-history '
                  'ledgers and the FTS row count; legacy export_provenance and review-state tables are '
                  'not declared. optional_artifacts lists normalized artifacts whose message rows are all '
                  'covered by declared original-export occurrences or that no message row references; the '
                  'adapters derive those bytes in memory, so only the original exports are required backup '
                  'objects for them')
MANIFEST_BOUNDARY = ('This manifest describes the live archive at declaration time. It is not a backup, not '
                     'proof that any remote copy exists or is complete, and not a recovery. Store it with '
                     'the backup, never inside the archive it describes. A later rehearsal compares one '
                     'restored copy against these declared rows, counts and digests only.')
RECEIPT_SCOPE = ('one read-only snapshot of the supplied restored copy compared with the declared manifest; '
                 'no repair, import, index rebuild, backup, upload or archive change')
RECEIPT_BOUNDARY = ('A passing rehearsal verifies this restored copy against the declared manifest. It does '
                    'not prove that the remote backup is complete or current, that decryption keys are safe, '
                    'or that a future restore will succeed. The tool cannot know whether the supplied path '
                    'is a clean restored copy or the live archive: the operator is responsible for pointing '
                    'the rehearsal at a clean restored copy. Running it against the live archive is allowed '
                    'and is only a self-check. Never derive recovery verification from a git ref or a push '
                    'message.')
_HEX64 = re.compile(r'[0-9a-f]{64}')
_DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')


def _validate_declared_at(value):
    if value is None:
        return None
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ValueError('declared_at must be YYYY-MM-DD text')
    month, day = int(value[5:7]), int(value[8:10])
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise ValueError('declared_at must be a plausible YYYY-MM-DD calendar date')
    return value


def _hex64(value):
    return isinstance(value, str) and _HEX64.fullmatch(value) is not None


def _count(value):
    return type(value) is int and value >= 0


def _canonical_line(values):
    return (json.dumps(values, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n').encode('ascii')


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def _reject_existing(output):
    """Fail early for an occupied destination, including a dangling symlink."""
    destination = Path(output)
    destination.parent.resolve(strict=True)
    try:
        destination.lstat()
    except FileNotFoundError:
        return
    raise FileExistsError('output path already exists; choose a new file name')


def _publish_new_file(output, raw, prefix):
    return _publish_new_chunks(output, (raw,), prefix)


def _publish_new_chunks(output, chunks, prefix):
    """Publish a byte iterator with bounded buffering and no replacement fallback."""
    destination = Path(output)
    parent = destination.parent.resolve(strict=True)
    destination = parent / destination.name
    temporary = None
    published = False
    cleanup_complete = True
    try:
        # Close the private same-directory staging file before linking on Windows.
        # Hard-link publication is atomic and refuses files, directories and
        # symlinks already at the destination. Never fall back to replacement.
        with tempfile.NamedTemporaryFile(prefix=prefix, dir=parent, delete=False) as stream:
            temporary = Path(stream.name)
            for raw in chunks:
                if stream.write(raw) != len(raw):
                    raise OSError('incomplete recovery document write')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        published = True
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                if not published:
                    raise
                cleanup_complete = False
    return dict(staging_cleanup_complete=cleanup_complete,
                remaining_staging_file=temporary.name if not cleanup_complete else None)


def _tables(connection):
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _artifact_rows(connection):
    return [dict(zip(ARTIFACT_FIELDS, row)) for row in connection.execute(
        'SELECT source_id,sha256,bytes,record_count FROM artifacts '
        'ORDER BY source_id COLLATE BINARY, sha256 COLLATE BINARY')]


def _messages_digest(connection):
    digest = hashlib.sha256()
    for row in connection.execute(
            'SELECT source_id,conversation_id,message_id,role,timestamp,title,text,source_sha256,source_line '
            'FROM messages ORDER BY source_id COLLATE BINARY, conversation_id COLLATE BINARY, '
            'message_id COLLATE BINARY'):
        digest.update(_canonical_line(list(row)))
    return digest.hexdigest()


def _message_totals(connection):
    messages = connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
    conversations = connection.execute(
        'SELECT COUNT(*) FROM (SELECT DISTINCT source_id, conversation_id FROM messages)').fetchone()[0]
    return messages, conversations


def _occurrences(connection, tables):
    if 'export_occurrences' not in tables:
        return None, {}
    total = connection.execute('SELECT COUNT(*) FROM export_occurrences').fetchone()[0]
    per_source = {}
    for row in connection.execute('SELECT source, COUNT(*) FROM export_occurrences GROUP BY source'):
        if not isinstance(row[0], str):
            raise ValueError('export_occurrences contains a source that is not text')
        per_source[row[0]] = dict(export_occurrences=row[1], original_hashes=[])
    for row in connection.execute('SELECT DISTINCT source, original_hash FROM export_occurrences '
                                  'ORDER BY source COLLATE BINARY, original_hash COLLATE BINARY'):
        if not _hex64(row[1]):
            raise ValueError('export_occurrences contains an original_hash that is not a lowercase SHA-256 digest')
        per_source[row[0]]['original_hashes'].append(row[1])
    return total, per_source


def _source_entries(connection, tables):
    """Per-source counts for every source named by artifacts, messages or occurrences."""
    artifacts = _artifact_rows(connection)
    counts = {}
    for row in connection.execute(
            'SELECT source_id, COUNT(*), COUNT(DISTINCT conversation_id) FROM messages GROUP BY source_id'):
        counts[row[0]] = (row[1], row[2])
    total, occurrences = _occurrences(connection, tables)
    entries = []
    for source_id in sorted(set(counts) | {row['source_id'] for row in artifacts} | set(occurrences)):
        if not isinstance(source_id, str):
            raise ValueError('archive contains a source identity that is not text')
        messages, conversations = counts.get(source_id, (0, 0))
        ledger = occurrences.get(source_id, dict(export_occurrences=0, original_hashes=[]))
        entries.append(dict(source_id=source_id,
                            artifacts=sum(row['source_id'] == source_id for row in artifacts),
                            messages=messages, conversations=conversations,
                            export_occurrences=None if total is None else ledger['export_occurrences'],
                            original_hashes=None if total is None else ledger['original_hashes']))
    return entries, artifacts, total


def _optional_artifacts(connection, tables, artifacts):
    """Normalized artifacts that are not separately required backup objects.

    An artifact is optional when no message row references it, or when every
    referencing message has an export_occurrences row for its original export.
    Export adapters derive those normalized bytes in memory during import, so
    the declared original exports are the objects to keep for them.
    """
    coverage = ('SUM(EXISTS(SELECT 1 FROM export_occurrences o WHERE o.source=m.source_id AND '
                'o.conversation=m.conversation_id AND o.message=m.message_id))'
                if 'export_occurrences' in tables else '0')
    referenced = {}
    for row in connection.execute('SELECT source_id, source_sha256, COUNT(*), ' + coverage +
                                  ' FROM messages m GROUP BY source_id, source_sha256'):
        referenced[(row[0], row[1])] = (row[2], row[3])
    optional = []
    for artifact in artifacts:
        total, covered = referenced.get((artifact['source_id'], artifact['sha256']), (0, 0))
        if total == 0 or covered == total:
            optional.append(dict(source_id=artifact['source_id'], sha256=artifact['sha256']))
    return optional


def _title_history(connection, tables):
    if 'title_history' not in tables:
        return None
    count = connection.execute('SELECT COUNT(*) FROM title_history').fetchone()[0]
    digest = hashlib.sha256()
    for row in connection.execute(
            'SELECT source,conversation,previous,title,changed_at FROM title_history ORDER BY '
            'source COLLATE BINARY, conversation COLLATE BINARY, previous COLLATE BINARY, '
            'title COLLATE BINARY, changed_at COLLATE BINARY'):
        digest.update(_canonical_line(list(row)))
    return dict(count=count, sha256=digest.hexdigest())


def _fts_rows(connection, tables):
    # count(*) on an external-content FTS5 table reads through to the content
    # table even when the index is empty; the docsize shadow table holds one row
    # per indexed row and is what the index actually knows about.
    if 'messages_fts_docsize' in tables:
        return connection.execute('SELECT COUNT(*) FROM messages_fts_docsize').fetchone()[0], 'messages_fts_docsize'
    return connection.execute('SELECT COUNT(*) FROM messages_fts').fetchone()[0], 'messages_fts'


def _first_token(text):
    """First run of FTS5 unicode61 token characters: categories L*, N* and Co."""
    if not isinstance(text, str):
        return None
    start = None
    for index, character in enumerate(text):
        if character.isalnum() or unicodedata.category(character) == 'Co':
            if start is None:
                start = index
        elif start is not None:
            return text[start:index]
    return None if start is None else text[start:]


def _describe(connection):
    tables = _tables(connection)
    missing = [name for name in EXPECTED_TABLES if name not in tables]
    if missing:
        raise ValueError('archive lacks the expected tables: ' + ', '.join(missing))
    sources, artifacts, occurrences = _source_entries(connection, tables)
    messages, conversations = _message_totals(connection)
    return dict(sources=sources, artifacts=artifacts,
                optional_artifacts=_optional_artifacts(connection, tables, artifacts),
                messages=messages, conversations=conversations,
                messages_sha256=_messages_digest(connection), export_occurrences=occurrences,
                title_history=_title_history(connection, tables), fts_rows=_fts_rows(connection, tables)[0])


def declare_recovery(db, output, declared_at=None):
    """Write a new manifest describing the live archive; the archive is only read."""
    declared_at = _validate_declared_at(declared_at)
    _reject_existing(output)
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        description = _describe(connection)
    finally:
        connection.close()
    manifest = dict(schema=MANIFEST_SCHEMA, declared_at=declared_at, **description,
                    digest_semantics=DIGEST_SEMANTICS, scope=MANIFEST_SCOPE, boundary=MANIFEST_BOUNDARY)
    raw = _encode(manifest)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('recovery manifest exceeds the 64 MiB limit')
    publication = _publish_new_file(output, raw, '.recap-recovery-manifest-')
    history = description['title_history']
    return dict(schema=DECLARATION_SCHEMA, status='DECLARED', manifest_schema=MANIFEST_SCHEMA,
                manifest_bytes=len(raw), manifest_sha256=hashlib.sha256(raw).hexdigest(),
                declared_at=declared_at, sources=len(description['sources']),
                artifacts=len(description['artifacts']), optional_artifacts=len(description['optional_artifacts']),
                messages=description['messages'],
                conversations=description['conversations'], messages_sha256=description['messages_sha256'],
                export_occurrences=description['export_occurrences'],
                title_history=None if history is None else history['count'],
                fts_rows=description['fts_rows'], **publication,
                archive_mutation=False, network_access=False, contains_message_text=False,
                backup_created=False, remote_copy_verified='NOT_ESTABLISHED',
                scope='one read-only archive snapshot described in a new local manifest file; '
                      'no backup, upload, repair or archive change',
                boundary=MANIFEST_BOUNDARY)


def _read_manifest(path):
    require_regular_file(path, max_bytes=MAX_MANIFEST_BYTES, label='recovery manifest',
                         too_large='recovery manifest exceeds the 64 MiB limit')
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('recovery manifest exceeds the 64 MiB limit')
    try:
        value = loads(decode_source(raw))
    except UnicodeError:
        raise ValueError('recovery manifest must be UTF-8 JSON') from None
    return raw, _validate_manifest(value)


def _validate_manifest(value):
    if not isinstance(value, dict):
        raise ValueError('recovery manifest must be a JSON object')
    if value.get('schema') != MANIFEST_SCHEMA:
        raise ValueError('unsupported recovery manifest schema; expected ' + MANIFEST_SCHEMA)
    if set(value) != set(MANIFEST_FIELDS):
        raise ValueError('recovery manifest must contain exactly the declared fields')
    _validate_declared_at(value['declared_at'])
    if (not all(_count(value[key]) for key in ('messages', 'conversations', 'fts_rows')) or
            not _hex64(value['messages_sha256']) or
            not all(isinstance(value[key], str) for key in ('digest_semantics', 'scope', 'boundary'))):
        raise ValueError('recovery manifest counts, digest or boundary text are malformed')
    if not isinstance(value['artifacts'], list) or not isinstance(value['sources'], list):
        raise ValueError('recovery manifest artifacts and sources must be arrays')
    for row in value['artifacts']:
        if (not isinstance(row, dict) or set(row) != set(ARTIFACT_FIELDS) or
                not isinstance(row['source_id'], str) or not row['source_id'] or not _hex64(row['sha256']) or
                not _count(row['bytes']) or not _count(row['record_count'])):
            raise ValueError('recovery manifest artifact rows are malformed')
    pairs = {(row['source_id'], row['sha256']) for row in value['artifacts']}
    optional = value['optional_artifacts']
    if (not isinstance(optional, list) or any(not isinstance(row, dict) or set(row) != {'source_id', 'sha256'}
                                                or (row['source_id'], row['sha256']) not in pairs for row in optional)
            or len({(row['source_id'], row['sha256']) for row in optional}) != len(optional)):
        raise ValueError('recovery manifest optional_artifacts must name distinct declared artifact rows')
    ledger = value['export_occurrences']
    if ledger is not None and not _count(ledger):
        raise ValueError('recovery manifest export_occurrences must be null or a count')
    seen = set()
    for source in value['sources']:
        if (not isinstance(source, dict) or set(source) != set(SOURCE_FIELDS) or
                not isinstance(source['source_id'], str) or not source['source_id'] or
                source['source_id'] in seen or
                not all(_count(source[key]) for key in ('artifacts', 'messages', 'conversations'))):
            raise ValueError('recovery manifest source entries are malformed')
        seen.add(source['source_id'])
        hashes = source['original_hashes']
        if ledger is None:
            if source['export_occurrences'] is not None or hashes is not None:
                raise ValueError('recovery manifest sources declare occurrences without an occurrence ledger')
        elif (not _count(source['export_occurrences']) or not isinstance(hashes, list) or
                any(not _hex64(item) for item in hashes) or hashes != sorted(set(hashes))):
            raise ValueError('recovery manifest original hashes must be sorted distinct SHA-256 digests')
    history = value['title_history']
    if history is not None and (not isinstance(history, dict) or set(history) != {'count', 'sha256'} or
                                not _count(history['count']) or not _hex64(history['sha256'])):
        raise ValueError('recovery manifest title_history must be null or a count with a digest')
    return value


def _regular_file(path, label):
    target = Path(path)
    info = target.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError(label + ' must be an existing regular file, not a symlink or directory')
    digest = hashlib.sha256()
    size = 0
    with target.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
            size += len(chunk)
    return dict(path=str(path), bytes=size, sha256=digest.hexdigest())


def _error_text(error):
    return type(error).__name__ + ': ' + str(error)


def _run_check(name, function):
    try:
        passed, details = function()
    except (sqlite3.Error, ValueError, TypeError, OverflowError) as error:
        passed, details = False, dict(error=_error_text(error))
    return dict(check=name, status='PASS' if passed else 'FAIL', **details)


def _artifact_check(manifest, connection):
    found = _artifact_rows(connection)
    key = lambda row: tuple(row[field] for field in ARTIFACT_FIELDS)
    declared, present = {key(row) for row in manifest['artifacts']}, {key(row) for row in found}
    missing, unexpected = sorted(declared - present), sorted(present - declared)
    return not missing and not unexpected, dict(
        declared=len(manifest['artifacts']), found=len(found), missing=len(missing), unexpected=len(unexpected),
        missing_rows=[dict(zip(ARTIFACT_FIELDS, row)) for row in missing[:MAX_DETAIL_ITEMS]],
        unexpected_rows=[dict(zip(ARTIFACT_FIELDS, row)) for row in unexpected[:MAX_DETAIL_ITEMS]])


def _source_check(manifest, entries):
    fields = ('artifacts', 'messages', 'conversations')
    declared = {source['source_id']: source for source in manifest['sources']}
    found = {entry['source_id']: entry for entry in entries}
    mismatched = [dict(source_id=name, declared={f: declared[name][f] for f in fields},
                       found={f: found[name][f] for f in fields})
                  for name in sorted(set(declared) & set(found))
                  if any(declared[name][f] != found[name][f] for f in fields)]
    missing, undeclared = sorted(set(declared) - set(found)), sorted(set(found) - set(declared))
    return not (mismatched or missing or undeclared), dict(
        declared_sources=len(declared), found_sources=len(found),
        declared_messages=manifest['messages'], found_messages=sum(e['messages'] for e in entries),
        declared_conversations=manifest['conversations'],
        missing_sources=missing[:MAX_DETAIL_ITEMS], undeclared_sources=undeclared[:MAX_DETAIL_ITEMS],
        mismatched=mismatched[:MAX_DETAIL_ITEMS], mismatched_count=len(mismatched))


def _digest_check(manifest, connection):
    found = _messages_digest(connection)
    return found == manifest['messages_sha256'], dict(declared=manifest['messages_sha256'], found=found)


def _ledger_state(declared, present):
    if declared is None and not present:
        return 'both absent'
    if declared is None:
        return 'table present but not declared'
    if not present:
        return 'declared but table missing'
    return 'compared'


def _occurrence_check(manifest, entries, total, tables):
    state = _ledger_state(manifest['export_occurrences'], 'export_occurrences' in tables)
    if state != 'compared':
        return state == 'both absent', dict(state=state, declared=manifest['export_occurrences'], found=total)
    declared = {source['source_id']: (source['export_occurrences'], source['original_hashes'])
                for source in manifest['sources']}
    found = {entry['source_id']: (entry['export_occurrences'], entry['original_hashes']) for entry in entries}
    mismatched = sorted(name for name in set(declared) | set(found)
                        if declared.get(name, (0, [])) != found.get(name, (0, [])))
    passed = manifest['export_occurrences'] == total and not mismatched
    return passed, dict(state=state, declared=manifest['export_occurrences'], found=total,
                        declared_hashes=sum(len(h) for _, h in declared.values()),
                        found_hashes=sum(len(h) for _, h in found.values()),
                        mismatched_sources=mismatched[:MAX_DETAIL_ITEMS], mismatched_count=len(mismatched))


def _history_check(manifest, connection, tables):
    found = _title_history(connection, tables)
    state = _ledger_state(manifest['title_history'], found is not None)
    if state != 'compared':
        return state == 'both absent', dict(state=state, declared=manifest['title_history'], found=found)
    return found == manifest['title_history'], dict(state=state, declared=manifest['title_history'], found=found)


def _fts_count_check(manifest, connection, tables):
    rows, counted = _fts_rows(connection, tables)
    messages = _message_totals(connection)[0]
    return rows == messages, dict(fts_rows=rows, messages=messages, counted_from=counted,
                                  declared_fts_rows=manifest['fts_rows'])


def _fts_sample_check(connection):
    sampled, token = None, None
    for row in connection.execute('SELECT message_pk, text FROM messages ORDER BY message_pk LIMIT ?',
                                  (MAX_SAMPLED_MESSAGES,)):
        token = _first_token(row[1])
        if token is not None:
            sampled = row[0]
            break
    if sampled is None:
        empty = _message_totals(connection)[0] == 0
        return empty, dict(sampled=False, sampled_message_pk=None, token_length=0, matched=None,
                           detail='no messages to sample' if empty else
                           'no FTS token in the first %d messages' % MAX_SAMPLED_MESSAGES,
                           contains_message_text=False)
    hit = connection.execute('SELECT rowid FROM messages_fts WHERE messages_fts MATCH ? AND rowid=?',
                             ('"' + token.replace('"', '""') + '"', sampled)).fetchone()
    return hit is not None, dict(sampled=True, sampled_message_pk=sampled, token_length=len(token),
                                 matched=hit is not None, detail='quoted first token of the sampled message',
                                 contains_message_text=False)


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path, directory):
    try:
        return Path(path).relative_to(directory).as_posix()
    except ValueError:
        return Path(path).name


def _objects_check(manifest, directory, supplied, paths_by_hash=None):
    kinds, required = {}, set()
    optional = {(row['source_id'], row['sha256']) for row in manifest['optional_artifacts']}
    for row in manifest['artifacts']:
        kinds.setdefault(row['sha256'], set()).add('normalized_artifact')
        if (row['source_id'], row['sha256']) not in optional:
            required.add(row['sha256'])
    for source in manifest['sources']:
        for value in source['original_hashes'] or ():
            kinds.setdefault(value, set()).add('original_export')
            required.add(value)
    refusals, files, unreadable = set(), [], []

    def refuse(code, path, error):
        # Record the relative path and the exception type only; OS error text may carry absolute paths.
        refusals.add(code)
        unreadable.append(dict(path=_relative(path, directory), error=type(error).__name__))

    def unlistable(error):
        refuse('UNREADABLE_DIRECTORY', directory if error.filename is None else error.filename, error)

    for root, names, leaves in os.walk(directory, onerror=unlistable, followlinks=False):
        for name in list(names):
            path = Path(root) / name
            try:
                symlink = path.is_symlink()
            except OSError as error:
                refuse('UNREADABLE_DIRECTORY', path, error)
                names.remove(name)
                continue
            if symlink:
                refusals.add('SYMLINK_REFUSED')
                names.remove(name)
        for name in leaves:
            path = Path(root) / name
            try:
                if path.is_symlink():
                    refusals.add('SYMLINK_REFUSED')
                elif path.is_file():
                    files.append(path)
            except OSError as error:
                refuse('UNREADABLE_FILE', path, error)
        if len(files) > MAX_OBJECT_FILES:
            refusals.add('TOO_MANY_FILES')
            break
    present, hashed = set(), 0
    checked = not refusals
    if checked:
        # A file that cannot be read, or vanished since the walk, is recorded and skipped like an
        # oversized one; the remaining files are still hashed so the receipt stays informative.
        for path in sorted(files, key=lambda item: _relative(item, directory)):
            try:
                if path.lstat().st_size > MAX_OBJECT_BYTES:
                    refusals.add('OVERSIZED_FILE')
                    continue
                digest = _hash_file(path)
                present.add(digest)
                if paths_by_hash is not None:
                    paths_by_hash.setdefault(digest, path)
            except OSError as error:
                refuse('UNREADABLE_FILE', path, error)
                continue
            hashed += 1
    unreadable.sort(key=lambda item: item['path'])
    objects = [dict(sha256=value, kinds=sorted(kinds[value]), required=value in required,
                    status=('PRESENT' if value in present else 'MISSING') if checked else 'NOT_CHECKED')
               for value in sorted(kinds)]
    missing_required = sum(item['status'] == 'MISSING' and item['required'] for item in objects)
    missing_optional = sum(item['status'] == 'MISSING' and not item['required'] for item in objects)
    return not refusals and not missing_required, dict(
        directory=supplied, files_seen=len(files), files_hashed=hashed, declared=len(objects),
        required=len(required), present=sum(item['status'] == 'PRESENT' for item in objects),
        missing_required=missing_required, missing_optional=missing_optional, refusals=sorted(refusals),
        unreadable=unreadable[:MAX_DETAIL_ITEMS], unreadable_count=len(unreadable),
        limits=dict(max_files=MAX_OBJECT_FILES, max_bytes_per_file=MAX_OBJECT_BYTES), objects=objects)


def _archive_checks(manifest, restored_db, exclude_history=False):
    """Shared read-only checks; rebuild can explicitly exclude unreplayable history."""
    checks = []
    connection = None
    sqlite_protections = dict(trusted_schema='NOT_CHECKED', cell_size_check='NOT_CHECKED', defensive='NOT_CHECKED')
    try:
        try:
            connection = readonly(restored_db)
            from recaplib.sqlite_safety import safety_status
            sqlite_protections = safety_status(connection)
            connection.execute('BEGIN')
            rows = [row[0] for row in connection.execute('PRAGMA integrity_check')]
        except sqlite3.Error as error:
            checks.append(dict(check='integrity_check', status='FAIL', result='OPEN_ERROR',
                               error=_error_text(error), message_count=0, messages=[], sqlite_protections=sqlite_protections))
            opened = False
        else:
            opened = rows == ['ok']
            checks.append(dict(check='integrity_check', status='PASS' if opened else 'FAIL',
                               result='ok' if opened else 'NOT_OK', message_count=len(rows),
                               messages=[] if opened else [str(row) for row in rows[:MAX_DETAIL_ITEMS]],
                               sqlite_protections=sqlite_protections))
        if opened:
            tables = _tables(connection)
            expected = list(EXPECTED_TABLES) + [name for name, declared in (
                ('export_occurrences', manifest['export_occurrences']), ('title_history', manifest['title_history']))
                if declared is not None and not (exclude_history and name == 'title_history')]
            missing = [name for name in expected if name not in tables]
            checks.append(dict(check='expected_tables', status='PASS' if not missing else 'FAIL',
                               expected=expected, missing=missing))
            checks.append(_run_check('artifact_rows', lambda: _artifact_check(manifest, connection)))
            try:
                entries, _, total = _source_entries(connection, tables)
            except (sqlite3.Error, ValueError, TypeError) as error:
                failure = dict(error=_error_text(error))
                checks.append(dict(check='source_counts', status='FAIL', **failure))
                checks.append(dict(check='messages_digest', status='FAIL', **failure))
                checks.append(dict(check='export_occurrences', status='FAIL', **failure))
            else:
                checks.append(_run_check('source_counts', lambda: _source_check(manifest, entries)))
                checks.append(_run_check('messages_digest', lambda: _digest_check(manifest, connection)))
                checks.append(_run_check('export_occurrences',
                                         lambda: _occurrence_check(manifest, entries, total, tables)))
            if not exclude_history:
                checks.append(_run_check('title_history', lambda: _history_check(manifest, connection, tables)))
            checks.append(_run_check('fts_rows', lambda: _fts_count_check(manifest, connection, tables)))
            checks.append(_run_check('fts_match_sample', lambda: _fts_sample_check(connection)))
        else:
            checks.extend(dict(check=name, status='FAIL', detail=NOT_RUN) for name in CHECKS[1:]
                          if not (exclude_history and name == 'title_history'))
    finally:
        if connection is not None:
            connection.close()
    return checks


def rehearse_recovery(manifest_path, restored_db, output, objects=None):
    """Verify a restored copy against a declared manifest; the copy is only read."""
    raw, manifest = _read_manifest(manifest_path)
    _reject_existing(output)
    if objects is not None:
        store = Path(objects)
        if store.is_symlink() or not store.is_dir():
            raise ValueError('objects path must be an existing directory, not a symlink')
    restored = _regular_file(restored_db, 'restored archive')
    checks = _archive_checks(manifest, restored_db)
    if objects is not None:
        checks.append(_run_check(OBJECTS_CHECK, lambda: _objects_check(manifest, Path(objects), str(objects))))
    failed = [check['check'] for check in checks if check['status'] != 'PASS']
    receipt = dict(schema=RECEIPT_SCHEMA, status=PASSED if not failed else FAILED, failed_checks=failed,
                   checks_run=len(checks),
                   manifest=dict(path=str(manifest_path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                 schema=MANIFEST_SCHEMA, declared_at=manifest['declared_at']),
                   restored=restored, objects_directory=None if objects is None else str(objects),
                   checks=checks, restored_archive_written=False, archive_mutation=False, network_access=False,
                   contains_message_text=False, clean_destination_verified='NOT_ESTABLISHED',
                   remote_backup_verified='NOT_ESTABLISHED', decryption_keys_verified='NOT_ESTABLISHED',
                   future_restore_verified='NOT_ESTABLISHED', scope=RECEIPT_SCOPE, boundary=RECEIPT_BOUNDARY)
    encoded = _encode(receipt)
    publication = _publish_new_file(output, encoded, '.recap-recovery-receipt-')
    return dict(receipt, receipt_bytes=len(encoded), receipt_sha256=hashlib.sha256(encoded).hexdigest(),
                **publication)


def render_text(result):
    header = ('Recovery manifest declaration' if result.get('schema') == DECLARATION_SCHEMA
              else 'Archive rebuild receipt' if result.get('schema') == 'recap.rebuild-receipt.v1'
              else 'Recovery rehearsal receipt')
    items = []
    for key, value in result.items():
        if key == 'checks':
            for check in value:
                detail = {name: item for name, item in check.items() if name not in ('check', 'status')}
                items.append(('check ' + check['check'], [check['status'], detail]))
        else:
            items.append((key, value))
    return summary_text(header, items)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    declare = commands.add_parser('declare', help='write a recovery manifest describing the live archive without changing it')
    declare.add_argument('--db', required=True)
    declare.add_argument('--output', required=True, help='new manifest JSON path outside the archive; existing paths are refused')
    declare.add_argument('--declared-at', help='YYYY-MM-DD recorded as supplied text; no clock is read')
    rehearse = commands.add_parser('rehearse', help='verify a restored archive copy against a declared manifest and write a receipt')
    rehearse.add_argument('manifest', help='recovery manifest JSON written by declare')
    rehearse.add_argument('--restored-db', required=True, help='restored SQLite copy; opened read-only and never written')
    rehearse.add_argument('--output', required=True, help='new receipt JSON path; existing paths are refused')
    rehearse.add_argument('--objects', help='directory of fetched backup objects to hash for every declared artifact and original export hash')
    for command in (declare, rehearse):
        command.add_argument('--text', action='store_true', help='print an ASCII text summary instead of JSON')
    args = parser.parse_args()
    try:
        if args.command == 'declare':
            result = declare_recovery(args.db, args.output, args.declared_at)
        else:
            result = rehearse_recovery(args.manifest, args.restored_db, args.output, args.objects)
        rendered = render_text(result) if args.text else json.dumps(result, ensure_ascii=True, indent=2) + '\n'
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, safe_diagnostic(error) + '\n')
    print(rendered, end='')
    if args.command == 'rehearse' and result['status'] != PASSED:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
