"""Deterministic title-only review hints, never privacy clearance or semantics."""
import re
import unicodedata
from recaplib.title_rules import validate_title

_PATTERNS = (
    ('EMAIL_LIKE', re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')),
    ('URL_LIKE', re.compile(r'(?:https?://|www\.)\S+', re.IGNORECASE)),
    ('LONG_DIGIT_SEQUENCE', re.compile(r'(?<!\w)\+?\d[\d(). -]{5,}\d(?!\w)')),
    ('LONG_IDENTIFIER_LIKE', re.compile(r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-])')),
)


def assess_title(proposal):
    """Return categories only, without echoing matched substrings or source text."""
    title = validate_title(proposal['title'])
    normalized = unicodedata.normalize('NFKC', title)
    normalized = ''.join(ch for ch in normalized if unicodedata.category(ch) != 'Cf')
    flags = [name for name, pattern in _PATTERNS if pattern.search(normalized)]
    if any(unicodedata.category(ch) == 'Cf' for ch in title):
        flags.append('FORMAT_CHARACTERS_PRESENT')
    quality = []
    if len(title) > 80: quality.append('OVER_LOCAL_EXCERPT_LENGTH')
    if proposal.get('truncated') is True: quality.append('REPORTED_TRUNCATION')
    if proposal.get('selection_method') == 'first_user_greeting_fallback':
        quality.append('REPORTED_GREETING_FALLBACK')
    return dict(character_count=len(title), maximum_characters=200,
                counting='Unicode code points, not display width or grapheme clusters',
                privacy_flags=flags, quality_flags=quality,
                assessment='HEURISTIC_ONLY', scanned_scope='proposed title only',
                matched_values_included=False, generation_metadata_verified=False,
                warning='Absence of flags is not privacy clearance. Hints can miss private data or flag harmless text. No semantic quality judgment, redaction or automatic rejection is performed.')
