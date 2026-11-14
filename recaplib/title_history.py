"""Explicit read-only local title history; never reads message-body columns."""
from recaplib.cli_errors import safe_diagnostic
import argparse
import json
import sqlite3
from recaplib.archive import readonly


def history(db, source, conversation, limit=20, offset=0, expected_revision=None):
    if (not isinstance(source, str) or not source.strip() or
            not isinstance(conversation, str) or not conversation):
        raise ValueError('source and conversation must be nonempty text identities')
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('history limit must be an integer in 1..1000')
    if type(offset) is not int or not 0 <= offset <= 2**63-1:
        raise ValueError('history offset must be an integer in 0..9223372036854775807')
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
        raise ValueError('expected_revision must be a nonnegative integer')
    connection = readonly(db)
    try:
        connection.execute('BEGIN')
        identity = (source, conversation)
        original = connection.execute('SELECT title FROM messages WHERE source_id=? '
            'AND conversation_id=? ORDER BY message_pk LIMIT 1', identity).fetchone()
        if original is None:
            raise ValueError('unknown conversation')
        original = original[0]
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='title_history'").fetchone()
        current = connection.execute('SELECT title,id FROM title_history WHERE source=? '
            'AND conversation=? ORDER BY id DESC LIMIT 1', identity).fetchone() if exists else None
        display_title, revision = current if current is not None else (original, 0)
        if expected_revision is not None and expected_revision != revision:
            raise ValueError('stale title history; restart at offset 0 and review the current revision')
        changes = []
        total = 0
        if exists:
            total = connection.execute('SELECT COUNT(*) FROM title_history WHERE source=? '
                'AND conversation=?', identity).fetchone()[0]
            rows = connection.execute('SELECT id,title,previous,changed_at FROM title_history '
                'WHERE source=? AND conversation=? ORDER BY id DESC LIMIT ? OFFSET ?',
                (*identity, limit, offset))
            for row in rows:
                changes.append(dict(revision=row['id'], title=row['title'],
                    previous_title=row['previous'], changed_at=row['changed_at'],
                    is_current=row['id'] == revision))
        remaining = max(0, total - offset - len(changes))
        return dict(source=source, conversation=conversation,
            original_title=original, original_revision=0,
            display_title=display_title, revision=revision,
            total_changes=total, limit=limit, offset=offset,
            returned_changes=len(changes), remaining_changes=remaining,
            next_offset=offset + len(changes) if remaining else None,
            truncated=bool(remaining), changes=changes,
            order='newest local revision first', contains_message_text=False,
            scope='local display title history only',
            warning='PRIVATE TITLES. Old wording may expose information removed from the current title. This read is not approval or a remote title history. Separate pages can change; pass the current revision as expected_revision to reject intervening title writes. This guard does not track imports, message changes or external database edits. Row limits are not byte or query-work limits. Reapplying eligible old wording requires an explicit checked title change using the current revision, not the selected historical revision.')
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--conversation', required=True)
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--expected-revision', type=int,
                        help='reject a title changed since an earlier history page')
    args = parser.parse_args()
    try:
        result = history(args.db, args.source, args.conversation,
                         args.limit, args.offset, args.expected_revision)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, safe_diagnostic(error) + '\n')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
