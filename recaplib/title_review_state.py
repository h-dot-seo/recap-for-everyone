"""Explicit local skip/defer/open decisions, separate from title changes."""
import sqlite3
from pathlib import Path
from recaplib.archive import readonly
from recaplib.title_proposal import content_fingerprint

STATES = frozenset(('open', 'skipped', 'deferred'))


def state_snapshot(connection, source, conversation, digest, title_revision):
    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='title_review_history'").fetchone()
    row = connection.execute('SELECT id,state,content_sha256,title_revision FROM title_review_history '
                             'WHERE source=? AND conversation=? ORDER BY id DESC LIMIT 1',
                             (source, conversation)).fetchone() if exists else None
    current = row is not None and row['content_sha256'] == digest and row['title_revision'] == title_revision
    return dict(state=row['state'] if current else 'open', state_revision=row['id'] if row else 0,
                recorded_state=row['state'] if row else None, decision_current=current,
                stale_decision=row is not None and not current,
                expected_content_sha256=digest, expected_title_revision=title_revision)


def _snapshot(connection, source, conversation):
    rows = [dict(row) for row in connection.execute(
        'SELECT message_id,role,text FROM messages WHERE source_id=? AND conversation_id=? ORDER BY message_pk',
        (source, conversation))]
    if not rows:
        raise ValueError('unknown conversation')
    digest = content_fingerprint(rows)
    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='title_history'").fetchone()
    row = connection.execute('SELECT id FROM title_history WHERE source=? AND conversation=? ORDER BY id DESC LIMIT 1',
                             (source, conversation)).fetchone() if exists else None
    return digest, row['id'] if row else 0


def review_state(db, source, conversation, state=None, expected_state_revision=None,
                 expected_title_revision=None, expected_content_sha256=None):
    if not isinstance(source, str) or not source.strip() or not isinstance(conversation, str) or not conversation:
        raise ValueError('source and conversation are required')
    if state is None:
        if any(value is not None for value in (expected_state_revision, expected_title_revision, expected_content_sha256)):
            raise ValueError('expected values are only accepted with an explicit state change')
    else:
        if not isinstance(state, str) or state not in STATES:
            raise ValueError('review state must be open, skipped or deferred')
        if any(type(value) is not int or not 0 <= value <= 2**63-1 for value in (expected_state_revision, expected_title_revision)):
            raise ValueError('state change requires nonnegative signed-64-bit integer state and title revisions')
        if not isinstance(expected_content_sha256, str) or len(expected_content_sha256) != 64 or any(ch not in '0123456789abcdef' for ch in expected_content_sha256):
            raise ValueError('state change requires the current content SHA-256')
    connection = readonly(db) if state is None else sqlite3.connect(Path(db).resolve().as_uri()+'?mode=rw', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('BEGIN' if state is None else 'BEGIN IMMEDIATE')
        digest, title_revision = _snapshot(connection, source, conversation)
        current = state_snapshot(connection, source, conversation, digest, title_revision)
        if state is not None:
            if expected_content_sha256 != digest or expected_title_revision != title_revision or expected_state_revision != current['state_revision']:
                raise ValueError('stale review-state snapshot; read and review current state before changing it')
            # DDL and event append stay in the same explicit transaction. All
            # stale checks precede schema changes; no scripts/implicit commits.
            connection.execute('CREATE TABLE IF NOT EXISTS title_review_history ('
                               'id INTEGER PRIMARY KEY, source TEXT NOT NULL, conversation TEXT NOT NULL, '
                               'state TEXT NOT NULL, content_sha256 TEXT NOT NULL, title_revision INTEGER NOT NULL, '
                               'decided_at TEXT DEFAULT CURRENT_TIMESTAMP)')
            connection.execute('CREATE INDEX IF NOT EXISTS title_review_history_identity ON title_review_history(source,conversation,id)')
            connection.execute('INSERT INTO title_review_history(source,conversation,state,content_sha256,title_revision) VALUES(?,?,?,?,?)',
                               (source, conversation, state, digest, title_revision))
            current = state_snapshot(connection, source, conversation, digest, title_revision)
            connection.commit()
        return dict(source=source, conversation=conversation, **current,
                    scope='local review decision only; no title, message or remote mutation', remote_mutation=False)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def review_state_from_queue(db, source, conversation, state, queue):
    """Use a saved queue lease, never silently refresh it before an explicit write."""
    from recaplib.title_batch import select_queue_item
    if state is None:
        raise ValueError('a queue-based decision requires an explicit state')
    item = select_queue_item(queue, conversation)
    if queue.get('source') != source:
        raise ValueError('queue source does not match the explicitly selected source')
    lease = item.get('review_state')
    if not isinstance(lease, dict) or any(key not in lease for key in (
            'state_revision', 'expected_title_revision', 'expected_content_sha256')):
        raise ValueError('selected queue item lacks a complete review-state lease; regenerate the queue')
    return review_state(db, source, conversation, state, lease['state_revision'],
                        lease['expected_title_revision'], lease['expected_content_sha256'])
