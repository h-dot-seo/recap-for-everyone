"""Bound ZIP directory construction with byte or bounded seekable-file reads."""
import struct
import zipfile


def check_directory(raw, max_entries):
    """Compatibility entrypoint for an already retained immutable byte snapshot."""
    return _check_directory(lambda offset, size: raw[offset:offset+size], len(raw), max_entries)


def check_directory_stream(stream, size, max_entries):
    """Preflight the same open file; never read more than the bounded EOCD tail."""
    def read_at(offset, count):
        stream.seek(offset)
        value = stream.read(count)
        if len(value) != count:
            raise zipfile.BadZipFile('invalid or unsupported ZIP central directory')
        return value
    return _check_directory(read_at, size, max_entries)


def _check_directory(read_at, length, max_entries):
    def invalid():
        raise zipfile.BadZipFile('invalid or unsupported ZIP central directory')

    # EOCD's comment is at most 65535 bytes. A short trailing suffix remains
    # acceptable when it fits in this same bounded search, as with zipfile.
    tail_start = max(0, length - 65557)
    tail = read_at(tail_start, length - tail_start)
    found = tail.rfind(b'PK\x05\x06')
    end = tail_start + found if found >= 0 else -1
    if end < 0 or end + 22 > length:
        invalid()
    _, disk, directory_disk, disk_entries, entries, size, offset, comment = struct.unpack('<4s4H2LH', read_at(end, 22))
    if end + 22 + comment > length:
        invalid()
    directory_end = end
    locator = end - 20
    has_zip64 = locator >= 0 and read_at(locator, 4) == b'PK\x06\x07'
    if has_zip64:
        _, record_disk, record_offset, disks = struct.unpack('<4sLQL', read_at(locator, 20))
        record = locator - 56
        if record < 0 or read_at(record, 4) != b'PK\x06\x06':
            invalid()
        (_, record_size, made, needed, disk64, directory_disk64,
         disk_entries64, entries64, size64, offset64) = struct.unpack('<4sQ2H2L4Q', read_at(record, 56))
        # zipfile supports the ordinary 44-byte ZIP64 EOCD payload, not
        # extensible-sector records or multi-disk archives.
        if record_size != 44 or record_disk != 0 or disks != 1 or disk64 != 0 or directory_disk64 != 0 or disk_entries64 != entries64:
            invalid()
        if record_offset > record:
            invalid()
        if any(old != sentinel and old != new for old, sentinel, new in (
                (disk_entries, 65535, disk_entries64), (entries, 65535, entries64),
                (size, 0xffffffff, size64), (offset, 0xffffffff, offset64))):
            invalid()
        entries, size, offset = entries64, size64, offset64
        directory_end = record
    if disk != 0 or directory_disk != 0 or (not has_zip64 and disk_entries != entries):
        invalid()
    if entries > max_entries:
        raise ValueError('ZIP archive exceeds the 1000-entry preparation limit')
    start = directory_end - size
    prefix = start - offset
    if start < 0 or prefix < 0:
        invalid()
    if has_zip64 and record_offset + prefix != record:
        invalid()
    cursor, count = start, 0
    while cursor < directory_end:
        if directory_end - cursor < 46 or read_at(cursor, 4) != b'PK\x01\x02':
            invalid()
        name, extra, entry_comment, entry_disk = struct.unpack('<4H', read_at(cursor + 28, 8))
        if entry_disk not in (0, 65535):
            invalid()
        length = 46 + name + extra + entry_comment
        if length > directory_end - cursor:
            invalid()
        count += 1
        if count > max_entries:
            raise ValueError('ZIP archive exceeds the 1000-entry preparation limit')
        cursor += length
    if count != entries:
        invalid()
