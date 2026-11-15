"""Pre-open admission for existing bounded explicit-file readers."""
from pathlib import Path
import stat


def require_regular_file(path, *, max_bytes, label, too_large):
    """Follow existing symlink semantics, without opening FIFOs or devices.

    This is a preflight, not an atomic filesystem lease. Callers must retain their
    bounded read and post-read length check for files that grow after stat.
    """
    metadata = Path(path).stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(label + ' must be an existing regular file')
    if metadata.st_size > max_bytes:
        raise ValueError(too_large)


MAX_EXPORT_BYTES = 2 * 1024 * 1024 * 1024


def check_source_size(byte_count):
    """Inclusive source-file admission budget, not a total-memory guarantee."""
    if byte_count > MAX_EXPORT_BYTES:
        raise ValueError('source exceeds the 2 GiB input limit')


def require_source_file(path):
    """Preflight source type and size, following regular-file symlinks.

    Readers must still check observed bytes after stat. No immutable lease or
    protection against concurrent namespace changes is established.
    """
    metadata = Path(path).stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError('source must be an existing regular file')
    check_source_size(metadata.st_size)


MAX_DOCUMENT_BYTES = 8 * 1024 * 1024


def read_document_bytes(path):
    """Read one admitted title/plan/transfer document, not a memory sandbox.

    Preserve the read_bytes snapshot seam. Growth after stat may allocate more
    than the budget before the post-read rejection; namespace races are not fixed.
    """
    too_large = 'document exceeds the 8 MiB input limit'
    require_regular_file(path, max_bytes=MAX_DOCUMENT_BYTES, label='document', too_large=too_large)
    raw = Path(path).read_bytes()
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError(too_large)
    return raw


def read_document_text(path):
    """Match legacy UTF-8 read_text universal newlines, without removing a BOM."""
    return read_document_bytes(path).decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
