"""Pure deterministic user-text excerpt rules; never reads or modifies evidence."""
import unicodedata


GREETINGS = frozenset(('hi', 'hello', 'hey', 'good morning', 'good afternoon',
                       'good evening', 'thanks', 'thank you', '안녕', '안녕하세요',
                       '반가워요', '감사합니다', '고마워요'))


def _clean(text):
    # Keep source evidence unchanged; remove controls only from the proposed label.
    return ' '.join(''.join(' ' if unicodedata.category(ch) in ('Cc', 'Cf') else ch
                           for ch in text).split())


def excerpt(rows):
    fallback = None
    selected = None
    for row in rows:
        if row['role'] != 'user':
            continue
        text = _clean(row['text'])
        if not any(ch.isalnum() for ch in text):
            continue
        fallback = fallback or (row, text)
        if text.casefold().strip(' .!?,。！？') not in GREETINGS:
            selected = (row, text)
            break
    if fallback is None:
        raise ValueError('no usable user text for a local title excerpt')
    row, text = selected or fallback
    return dict(title=text[:80].rstrip(), evidence_message_ids=[row['message_id']],
                selection_method='first_non_greeting_user_excerpt' if selected else 'first_user_greeting_fallback',
                truncated=len(text) > 80, semantic_validation='NOT_PERFORMED')

