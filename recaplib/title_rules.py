"""Shared validation for local display titles; no source-text mutation."""
import unicodedata


def validate_title(title):
    if (not isinstance(title, str) or not title.strip() or len(title) > 200 or
            any(unicodedata.category(ch) in ('Cc', 'Cs', 'Zl', 'Zp') for ch in title)):
        raise ValueError('title must be a nonempty single line of at most 200 characters without controls or surrogate code points')
    return title
