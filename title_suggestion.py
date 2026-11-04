"""Generate a reviewable local user-text excerpt, without models or network calls."""
import argparse
import json
import sqlite3
from title_proposal import snapshot
from title_excerpt import GREETINGS, _clean, excerpt


def suggest(db, source, conversation, message_id=None):
    if message_id is not None and (not isinstance(message_id, str) or not message_id):
        raise ValueError('selected message ID must be nonempty text')
    rows, digest = snapshot(db, source, conversation)
    context = {}
    if message_id is not None:
        # Select only inside the exact conversation's single content snapshot.
        # Keep its full fingerprint so changes outside this evidence still stale
        # the proposal. Never substitute another row for a failed selection.
        rows = [row for row in rows if row['message_id'] == message_id]
        if len(rows) != 1 or rows[0]['role'] != 'user':
            raise ValueError('selected message must identify a user message in this conversation')
        context['evidence_selection'] = dict(mode='explicit_user_message', message_id=message_id,
            scope='raw archived user message; not branch, replay or source-attributed selection')
    return dict(source=source, conversation=conversation, content_sha256=digest,
                provider='local-extractive', **excerpt(rows), **context)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--conversation', required=True)
    parser.add_argument('--message', help='use exactly this archived user message for the excerpt; no alternate-message fallback')
    args = parser.parse_args()
    try:
        result = suggest(args.db, args.source, args.conversation, args.message)
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
