"""Generate a reviewable local user-text excerpt, without models or network calls."""
import argparse
import json
import sqlite3
from title_proposal import snapshot
from title_excerpt import GREETINGS, _clean, excerpt


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
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
