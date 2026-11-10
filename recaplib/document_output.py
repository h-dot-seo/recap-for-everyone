"""Exclusive same-directory byte publication; no replacement fallback."""
import os
from pathlib import Path
import tempfile


def write_bytes(raw, output, prefix):
    """Publish complete bytes and return staging cleanup details, never a path."""
    if not isinstance(raw, bytes):
        raise TypeError('document output requires bytes')
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
            if stream.write(raw) != len(raw):
                raise OSError('incomplete document write')
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
