"""Bound central-directory entry construction using an immutable ZIP snapshot."""
import struct
import zipfile


def check_directory(raw, max_entries):
    """Inspect ZIP/ZIP64 directory structure, not names, members or authenticity.

    Like stdlib zipfile, support a prepended executable/prefix and the fixed-size
    ZIP64 end record. Bounds apply before ZipFile allocates ZipInfo objects.
    """
    def invalid():
        raise zipfile.BadZipFile('invalid or unsupported ZIP central directory')

    # EOCD's comment is at most 65535 bytes. A short trailing suffix remains
    # acceptable when it fits in this same bounded search, as with zipfile.
    end = raw.rfind(b'PK\x05\x06', max(0, len(raw) - 65557))
    if end < 0 or end + 22 > len(raw):
        invalid()
    _, disk, directory_disk, disk_entries, entries, size, offset, comment = struct.unpack_from('<4s4H2LH', raw, end)
    if end + 22 + comment > len(raw):
        invalid()
    directory_end = end
    locator = end - 20
    has_zip64 = locator >= 0 and raw[locator:locator+4] == b'PK\x06\x07'
    if has_zip64:
        _, record_disk, record_offset, disks = struct.unpack_from('<4sLQL', raw, locator)
        record = locator - 56
        if record < 0 or raw[record:record+4] != b'PK\x06\x06':
            invalid()
        (_, record_size, made, needed, disk64, directory_disk64,
         disk_entries64, entries64, size64, offset64) = struct.unpack_from('<4sQ2H2L4Q', raw, record)
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
        if directory_end - cursor < 46 or raw[cursor:cursor+4] != b'PK\x01\x02':
            invalid()
        name, extra, entry_comment, entry_disk = struct.unpack_from('<4H', raw, cursor + 28)
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
