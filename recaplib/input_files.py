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
