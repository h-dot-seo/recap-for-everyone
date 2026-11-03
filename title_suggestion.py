"""Generate a reviewable local user-text excerpt, without models or network calls."""
import argparse
import json
import sqlite3
import unicodedata
from title_proposal import snapshot


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


def suggest(db, source, conversation):
    rows, digest = snapshot(db, source, conversation)
    return dict(source=source, conversation=conversation, content_sha256=digest,
                provider='local-extractive', **excerpt(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--conversation', required=True)
    args = parser.parse_args()
    try:
        result = suggest(args.db, args.source, args.conversation)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
