"""Prepare one explicitly chosen ZIP member as a new local web-export file."""
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile
import zlib
from recaplib.session_workflow import _normalize_bytes
from recaplib.zip_preflight import check_directory

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 1000
MAX_RATIO = 200


def validate_member_limit(value):
    if value is None:
        return MAX_MEMBER_BYTES
    if type(value) is not int or not 1 <= value <= MAX_MEMBER_BYTES:
        raise ValueError('max_member_bytes must be an integer in 1..' + str(MAX_MEMBER_BYTES))
    return value


def resource_limits(max_member_bytes=None):
    """Declare effective bounds; an operator may only lower the member bound."""
    return dict(member_bytes=validate_member_limit(max_member_bytes), ratio=MAX_RATIO, entries=MAX_ENTRIES,
                archive_ceiling=MAX_ARCHIVE_BYTES, operator_supplied=max_member_bytes is not None)


def exceeded_member_limits(info, max_member_bytes=None):
    """Metadata-only diagnostics, independent of higher-priority safety reasons."""
    exceeded = []
    if info.file_size > validate_member_limit(max_member_bytes):
        exceeded.append('member_bytes')
    if info.file_size > max(info.compress_size, 1) * MAX_RATIO:
        exceeded.append('ratio')
    return exceeded


def _safe_member(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name
            or name.startswith('/') or any(part in ('', '.', '..') for part in name.split('/'))
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
        raise ValueError('member must be an explicit portable relative file name without traversal')
    return name


def archive_bytes(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError('ZIP archive exceeds the 64 MiB preparation limit')
    return raw


def _validate_expected_archive_sha256(expected):
    if expected is not None and (not isinstance(expected, str) or len(expected) != 64 or any(ch not in '0123456789abcdef' for ch in expected)):
        raise ValueError('expected archive hash must be a lowercase SHA-256 hex digest')


def _checked_archive_sha256(raw, expected):
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None and digest != expected:
        raise ValueError('ZIP archive changed after inspection; inspect and select again')
    return digest


def member_problem(info, max_member_bytes=None):
    """Metadata-only eligibility shared with read-only candidate inspection."""
    try:
        _safe_member(info.orig_filename)
    except ValueError:
        return 'UNSAFE_MEMBER_NAME', 'member must be an explicit portable relative file name without traversal'
    if info.orig_filename != info.filename:
        return 'ALTERED_MEMBER_NAME', 'selected ZIP member name was altered during decoding'
    mode = (info.external_attr >> 16) & 0xffff
    if info.is_dir() or info.external_attr & 0x10 or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
        return 'NONREGULAR_MEMBER', 'selected ZIP member must be a regular file'
    if info.flag_bits & 1:
        return 'ENCRYPTED_MEMBER', 'encrypted ZIP members are not supported'
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        return 'UNSUPPORTED_COMPRESSION', 'only stored or deflated ZIP members are supported'
    if exceeded_member_limits(info, max_member_bytes):
        return 'MEMBER_EXPANSION_LIMIT', 'selected member exceeds the 16 MiB or 200:1 expansion limit'
    return None


def prepare_web_export(path, member, output, expected_archive_sha256=None, max_member_bytes=None):
    member_limit = validate_member_limit(max_member_bytes)
    _validate_expected_archive_sha256(expected_archive_sha256)
    member = _safe_member(member)
    if not member.lower().endswith('.json'):
        raise ValueError('select one JSON member, not an HTML page or attachment')
    raw = archive_bytes(path)
    archive_digest = _checked_archive_sha256(raw, expected_archive_sha256)
    try:
        check_directory(raw, MAX_ENTRIES)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise ValueError('ZIP archive exceeds the 1000-entry preparation limit')
            selected = [entry for entry in entries if entry.filename == member]
            if len(selected) != 1:
                raise ValueError('member must identify exactly one ZIP entry; no member is selected automatically')
            info = selected[0]
            problem = member_problem(info, max_member_bytes)
            if problem is not None:
                if max_member_bytes is not None and problem[0] == 'MEMBER_EXPANSION_LIMIT':
                    raise ValueError('selected member exceeds effective limits: ' + ', '.join(exceeded_member_limits(info, max_member_bytes)) + '; member_bytes=' + str(member_limit) + '; ratio=' + str(MAX_RATIO))
                raise ValueError(problem[1])
            with archive.open(info) as stream:
                content = stream.read(member_limit + 1)
            if len(content) > member_limit or len(content) != info.file_size:
                raise ValueError('selected member size is inconsistent or exceeds the limit')
            # read() reaches EOF for accepted members and validates the CRC.
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, zlib.error) as error:
        raise ValueError('invalid or unsupported ZIP member') from error
    try:
        _, coverage = _normalize_bytes(content, PurePosixPath(member).name, 'web', include_report=True)
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as error:
        raise ValueError('selected JSON member is not a supported web export') from error
    destination = Path(output)
    parent = destination.parent.resolve(strict=True)
    destination = parent / destination.name
    temporary = None
    published = False
    cleanup_complete = True
    try:
        # Same-directory staging + atomic no-overwrite hard link. Do not fall
        # back to replace/rename if the selected filesystem lacks hard links.
        fd, temporary = tempfile.mkstemp(prefix='.recap-prepare-', dir=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, destination)
        published = True
    finally:
        if temporary is not None:
            try:
                Path(temporary).unlink()
            except OSError:
                if not published:
                    raise
                cleanup_complete = False
    return dict(schema='recap.prepared-web-export.v1', archive_sha256=archive_digest,
                limits=resource_limits(max_member_bytes),
                archive_bytes=len(raw), selected_member=member, prepared_sha256=hashlib.sha256(content).hexdigest(),
                prepared_bytes=len(content), coverage=coverage, database_access=False, remote_mutation=False,
                staging_cleanup_complete=cleanup_complete,
                remaining_staging_file=Path(temporary).name if not cleanup_complete else None,
                scope='one selected JSON member copied unchanged to a new local file; no archive-wide extraction or import',
                warning='PRIVATE LOCAL COPY. JSON shape validation is not a completeness guarantee. Later import provenance uses the prepared JSON hash, not the outer ZIP hash.')
