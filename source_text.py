"""Decode source exports without changing hashed bytes or Unicode evidence."""
from codecs import BOM_UTF8


def decode_source(raw):
    """Strict UTF-8; tolerate one signature only at the beginning of the file."""
    return raw.decode('utf-8-sig')


def physical_lines(raw):
    """Match universal physical newlines, not Unicode separators inside JSON."""
    return decode_source(raw).replace('\r\n', '\n').replace('\r', '\n').split('\n')
