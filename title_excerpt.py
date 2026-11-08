"""Pure deterministic user-text excerpt rules; never reads or modifies evidence."""
import unicodedata


GREETINGS = frozenset(('hi', 'hello', 'hey', 'good morning', 'good afternoon',
                       'good evening', 'thanks', 'thank you', '안녕', '안녕하세요',
                       '반가워요', '감사합니다', '고마워요'))

# These format characters affect ordinary text shaping and emoji sequences.
# Keeping them is not a claim that their placement or rendered label is safe.
JOIN_CONTROLS = frozenset(('\u200c', '\u200d'))


def _clean(text):
    # Keep source evidence unchanged. Retain join controls in the label; replace
    # other Cc/Cf characters as before and collapse ordinary whitespace.
    return ' '.join(''.join(' ' if ch not in JOIN_CONTROLS and unicodedata.category(ch) in ('Cc', 'Cf') else ch
                           for ch in text).split())


def excerpt(rows):
    fallback = None
    selected = None
    for row in rows:
        if row['role'] != 'user':
            continue
        text = _clean(row['text'])
        # A letter beyond the returned prefix must not make a title consisting
        # only of punctuation, emoji or invisible join controls look usable.
        if not any(ch.isalnum() for ch in text[:80]):
            continue
        fallback = fallback or (row, text)
        # Compare canonically equivalent greetings without normalizing the
        # selected label, source message, evidence identity or fingerprint.
        greeting_key = unicodedata.normalize('NFC', text).casefold().strip(' .!?,。！？')
        if greeting_key not in GREETINGS:
            selected = (row, text)
            break
    if fallback is None:
        raise ValueError('no usable user text for a local title excerpt')
    row, text = selected or fallback
    return dict(title=text[:80].rstrip(), evidence_message_ids=[row['message_id']],
                selection_method='first_non_greeting_user_excerpt' if selected else 'first_user_greeting_fallback',
                truncated=len(text) > 80, semantic_validation='NOT_PERFORMED')

