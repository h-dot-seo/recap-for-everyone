"""Prepare one explicitly chosen ZIP member as a new local web-export file."""
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile
import zlib
from session_workflow import _normalize_bytes

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 1000
MAX_RATIO = 200


def _safe_member(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name
            or name.startswith('/') or any(part in ('', '.', '..') for part in name.split('/'))
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
        raise ValueError('member must be an explicit portable relative file name without traversal')
    return name


def prepare_web_export(path, member, output):
    member = _safe_member(member)
    if not member.lower().endswith('.json'):
        raise ValueError('select one JSON member, not an HTML page or attachment')
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError('ZIP archive exceeds the 64 MiB preparation limit')
    # Every central-directory entry needs this signature. Count before ZipFile
    # constructs entry objects; conservative false positives are acceptable.
    if raw.count(b'PK\x01\x02') > MAX_ENTRIES:
        raise ValueError('ZIP archive exceeds the 1000-entry preparation limit')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ENTRIES:
                raise ValueError('ZIP archive exceeds the 1000-entry preparation limit')
            selected = [entry for entry in entries if entry.filename == member]
            if len(selected) != 1:
                raise ValueError('member must identify exactly one ZIP entry; no member is selected automatically')
            info = selected[0]
            if info.orig_filename != member:
                raise ValueError('selected ZIP member name was altered during decoding')
            mode = (info.external_attr >> 16) & 0xffff
            if info.is_dir() or info.external_attr & 0x10 or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                raise ValueError('selected ZIP member must be a regular file')
            if info.flag_bits & 1:
                raise ValueError('encrypted ZIP members are not supported')
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError('only stored or deflated ZIP members are supported')
            if info.file_size > MAX_MEMBER_BYTES or info.file_size > max(info.compress_size, 1) * MAX_RATIO:
                raise ValueError('selected member exceeds the 16 MiB or 200:1 expansion limit')
            with archive.open(info) as stream:
                content = stream.read(MAX_MEMBER_BYTES + 1)
            if len(content) > MAX_MEMBER_BYTES or len(content) != info.file_size:
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
    return dict(schema='recap.prepared-web-export.v1', archive_sha256=hashlib.sha256(raw).hexdigest(),
                archive_bytes=len(raw), selected_member=member, prepared_sha256=hashlib.sha256(content).hexdigest(),
                prepared_bytes=len(content), coverage=coverage, database_access=False, remote_mutation=False,
                staging_cleanup_complete=cleanup_complete,
                remaining_staging_file=Path(temporary).name if not cleanup_complete else None,
                scope='one selected JSON member copied unchanged to a new local file; no archive-wide extraction or import',
                warning='PRIVATE LOCAL COPY. JSON shape validation is not a completeness guarantee. Later import provenance uses the prepared JSON hash, not the outer ZIP hash.')
