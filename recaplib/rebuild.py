"""Rebuild a new archive from declared retained objects and an explicit replay plan."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile

from recaplib import recovery
from recaplib.archive import SCHEMA, _validate_source, ingest_bytes
from recaplib.input_files import require_regular_file
from recaplib.session_workflow import import_export_bytes
from recaplib.source_text import decode_source
from recaplib.strict_json import loads

PLAN_SCHEMA = 'recap.rebuild-plan.v1'
RECEIPT_SCHEMA = 'recap.rebuild-receipt.v1'
PASSED = 'REBUILD_REHEARSAL_PASSED'
FAILED = 'REBUILD_REHEARSAL_FAILED'
MAX_PLAN_BYTES = 64 * 1024 * 1024
MAX_STEPS = 10000
STEP_FIELDS = {'source', 'kind', 'object_sha256', 'label', 'conversation', 'newline'}
SIDECARS = ('-journal', '-wal', '-shm')
IMPLEMENTATIONS = ('archive.py', 'session_workflow.py', 'local_parser.py', 'strict_json.py',
                   'source_text.py', 'recovery.py', 'rebuild.py')
BOUNDARY = ('Rebuilt declared message objects only, not a full archive restoration. Title history cannot '
            'be rebuilt from objects; verify it with rehearse-recovery on a retained database copy. '
            'Review-state and other undeclared tables are not restored or compared. No remote backup, '
            'decryption-key, clean-directory or future-recovery verification. Plans and manifests are '
            'operator-supplied, not authenticated. New database and receipt publication are not a '
            'two-file atomic transaction. No defense against a hostile concurrent path namespace or '
            'whole-process memory limit is established.')


def _read_plan(path):
    require_regular_file(path, max_bytes=MAX_PLAN_BYTES, label='rebuild plan',
                         too_large='rebuild plan exceeds its byte limit')
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_PLAN_BYTES + 1)
    if len(raw) > MAX_PLAN_BYTES:
        raise ValueError('rebuild plan exceeds its byte limit')
    plan = loads(decode_source(raw))
    if not isinstance(plan, dict) or set(plan) != {'schema', 'steps'} or plan['schema'] != PLAN_SCHEMA:
        raise ValueError('rebuild plan must have exactly schema and steps with recap.rebuild-plan.v1')
    if not isinstance(plan['steps'], list) or len(plan['steps']) > MAX_STEPS:
        raise ValueError('rebuild plan steps must be an array within the step limit')
    for step in plan['steps']:
        if not isinstance(step, dict) or set(step) != STEP_FIELDS:
            raise ValueError('rebuild step must have exactly the documented fields')
        _validate_source(step['source'])
        if step['kind'] not in ('normalized', 'web', 'local', 'local-codex') or not recovery._hex64(step['object_sha256']):
            raise ValueError('rebuild step kind or object hash is invalid')
        if step['newline'] not in ('lf', 'crlf'):
            raise ValueError('rebuild step newline must be lf or crlf')
        for field in ('label', 'conversation'):
            value = step[field]
            if value is not None:
                if not isinstance(value, str) or not value:
                    raise ValueError('rebuild label and conversation must be nonempty text or null')
                try:
                    value.encode('utf-8')
                except UnicodeEncodeError:
                    raise ValueError('rebuild fields must contain valid Unicode text') from None
        if step['kind'] in ('local', 'local-codex') and step['label'] is None:
            raise ValueError('local replay requires its original parsing label')
        if step['kind'] == 'normalized' and (step['label'] is not None or step['conversation'] is not None):
            raise ValueError('normalized replay requires null label and conversation')
    return raw, plan


def _database_paths(path):
    return [Path(path)] + [Path(str(path) + suffix) for suffix in SIDECARS]


def _destinations(new_db, output):
    new_db = Path(new_db).parent.resolve(strict=True) / Path(new_db).name
    output = Path(output).parent.resolve(strict=True) / Path(output).name
    if os.path.normcase(str(output)) in {os.path.normcase(str(p)) for p in _database_paths(new_db)}:
        raise ValueError('receipt must not alias the new database or its sidecars')
    for path in _database_paths(new_db) + [output]:
        recovery._reject_existing(path)
    return new_db, output


def _declared_steps(plan, manifest):
    artifacts = {(row['source_id'], row['sha256']) for row in manifest['artifacts']}
    originals = {(source['source_id'], digest) for source in manifest['sources']
                 for digest in source['original_hashes'] or ()}
    for step in plan['steps']:
        allowed = artifacts if step['kind'] == 'normalized' else originals
        if (step['source'], step['object_sha256']) not in allowed:
            raise ValueError('plan object is not declared for this source and input kind')


def _object_bytes(path, expected):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('rebuild object must be a regular file, not a symlink')
    if info.st_size > recovery.MAX_OBJECT_BYTES:
        raise ValueError('rebuild object exceeds its byte limit')
    with Path(path).open('rb') as stream:
        raw = stream.read(recovery.MAX_OBJECT_BYTES + 1)
    if len(raw) > recovery.MAX_OBJECT_BYTES:
        raise ValueError('rebuild object exceeds its byte limit')
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('rebuild object changed since inventory')
    return raw


def _encode_receipt(receipt):
    # Filesystem paths may contain surrogate-escaped bytes on POSIX. Preserve
    # those strings as JSON escapes instead of failing after DB publication.
    return (json.dumps(receipt, ensure_ascii=True, allow_nan=False, indent=2) + '\n').encode('ascii')


def rebuild_archive(manifest_path, plan_path, objects, new_db, output):
    """Create only a verified new DB; never open or mutate the original archive."""
    destination, output = _destinations(new_db, output)
    raw_manifest, manifest = recovery._read_manifest(manifest_path)
    raw_plan, plan = _read_plan(plan_path)
    store = Path(objects)
    if store.is_symlink() or not store.is_dir():
        raise ValueError('objects path must be an existing directory, not a symlink')
    receipt = dict(schema=RECEIPT_SCHEMA, status=FAILED, checks=[], steps=[], objects_used=[],
                   manifest=dict(sha256=hashlib.sha256(raw_manifest).hexdigest(), bytes=len(raw_manifest)),
                   plan=dict(sha256=hashlib.sha256(raw_plan).hexdigest(), bytes=len(raw_plan), steps=len(plan['steps'])),
                   new_database=str(destination), new_database_created_exclusively=False,
                   not_rebuildable_from_objects=['title_history'] if manifest['title_history'] is not None else [],
                   title_history='NOT_REBUILDABLE_FROM_OBJECTS' if manifest['title_history'] is not None else 'NOT_DECLARED',
                   review_state='NOT_DECLARED_NOT_RESTORED', rebuilt_from='declared objects only',
                   live_archive_read=False, existing_archive_written=False, network_access=False,
                   contains_message_text=False, clean_destination_verified='NOT_ESTABLISHED',
                   remote_backup_verified='NOT_ESTABLISHED', decryption_keys_verified='NOT_ESTABLISHED',
                   future_restore_verified='NOT_ESTABLISHED',
                   implementation_sha256={name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                                          for name in IMPLEMENTATIONS},
                   scope='replay plan order, retained object hashes, declared logical rows and sampled FTS checks',
                   boundary=BOUNDARY)
    staging = None
    remaining = []
    phase = 'PLAN_OBJECT_DECLARATION'
    try:
        _declared_steps(plan, manifest)
        phase = 'OBJECT_INVENTORY'
        paths = {}
        passed, details = recovery._objects_check(manifest, store, str(objects), paths)
        receipt['checks'].append(dict(check='declared_objects', status='PASS' if passed else 'FAIL', **details))
        if not passed:
            raise ValueError('declared object inventory failed')
        phase = 'REPLAY'
        with tempfile.NamedTemporaryFile(prefix='.recap-rebuild-', suffix='.sqlite', dir=destination.parent,
                                         delete=False) as stream:
            staging = Path(stream.name)
        connection = sqlite3.connect(staging)
        try:
            connection.executescript(SCHEMA)
        finally:
            connection.close()
        for index, step in enumerate(plan['steps']):
            raw = _object_bytes(paths[step['object_sha256']], step['object_sha256'])
            if step['kind'] == 'normalized':
                result = ingest_bytes(staging, step['source'], raw, expected_sha256=step['object_sha256'])
            else:
                result = import_export_bytes(staging, step['source'], raw, step['label'], step['kind'],
                                             step['conversation'], newline=step['newline'])
            receipt['steps'].append(dict(index=index, kind=step['kind'], object_sha256=step['object_sha256'],
                                         newline=step['newline'], records=result['records'], inserted=result['inserted']))
            if step['object_sha256'] not in receipt['objects_used']:
                receipt['objects_used'].append(step['object_sha256'])
        phase = 'ARCHIVE_VERIFICATION'
        receipt['checks'].extend(recovery._archive_checks(manifest, staging, exclude_history=True))
        if any(item['status'] != 'PASS' for item in receipt['checks']):
            raise ValueError('rebuilt archive differs from declaration')
        phase = 'DATABASE_PUBLICATION'
        _destinations(destination, output)
        # All SQLite connections are closed. Refuse unexpected staging sidecars;
        # never publish a DB that depends on a journal or WAL being copied too.
        for path in _database_paths(staging)[1:]:
            recovery._reject_existing(path)
        with staging.open('rb') as stream:
            os.fsync(stream.fileno())
        os.link(staging, destination)
        receipt['new_database_created_exclusively'] = True
        receipt['status'] = PASSED
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
        # Parser/SQLite error strings may contain private original text or IDs.
        receipt['failure'] = dict(phase=phase, reason='REBUILD_STEP_FAILED', exception_type=type(error).__name__)
    finally:
        if staging is not None:
            for path in _database_paths(staging):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    remaining.append(path.name)
    receipt['staging_cleanup_complete'] = not remaining
    receipt['remaining_staging_files'] = remaining
    receipt['failed_checks'] = [item['check'] for item in receipt['checks'] if item['status'] != 'PASS']
    receipt['checks_run'] = len(receipt['checks'])
    try:
        encoded = _encode_receipt(receipt)
        publication = recovery._publish_new_file(output, encoded, '.recap-rebuild-receipt-')
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        if receipt['new_database_created_exclusively']:
            raise OSError('rebuilt database was published at ' + str(destination) +
                          '; receipt publication failed; database was preserved') from error
        raise
    return dict(receipt, receipt_bytes=len(encoded), receipt_sha256=hashlib.sha256(encoded).hexdigest(),
                receipt_staging_cleanup_complete=publication['staging_cleanup_complete'],
                remaining_receipt_staging_file=publication['remaining_staging_file'])
