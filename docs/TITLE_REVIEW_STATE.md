# Explicit local skip and defer decisions

Title changes, skipping a suggestion and postponing a decision are different
operations. `review-state` records the latter two without changing any title or
message. The states are:

- `open`: no current skip/defer decision, or explicitly reopen this snapshot.
- `skipped`: you explicitly chose not to work on this conversation snapshot.
- `deferred`: you explicitly postponed the decision. This schedules no reminder.

There is no inferred `completed` state. A title-history entry means a local title
write happened, not that the content was understood or all organization work is
finished. `previously_renamed` and the title revision stay separate from review
state. No title is applied merely because you skip or defer.

## Read, inspect, then record an explicit decision

Use the private database from [the walkthrough](TITLE_WALKTHROUGH.md):

```sh
python recap.py --db ../recap-demo/archive.sqlite review-state --source web-demo --conversation synthetic-chat
```

This is read-only and does not even create the review-state table. Read the returned
`state_revision`, `expected_title_revision` and `expected_content_sha256`. To defer
that exact snapshot, supply all three exact values (replace the placeholders):

```sh
python recap.py --db ../recap-demo/archive.sqlite review-state --source web-demo --conversation synthetic-chat --set deferred --expected-state-revision STATE_REVISION --expected-title-revision TITLE_REVISION --expected-content-sha256 CONTENT_SHA256
```

Use `--set skipped` or `--set open` for an explicit skip or reopen. The returned
state includes a new state revision. Reusing the old lease, even for the same
state, is rejected. Read and inspect the current state before retrying. Repeating
with a fresh lease intentionally appends another decision; it is not an invisible
idempotent retry. State/title revision values are integers, not booleans, and must
fit SQLite's nonnegative signed 64-bit range.

The CLI never guesses revisions, takes a decision from a queue automatically, or
performs a bulk action. Files, messages, original titles and title overrides remain
unchanged. The database receives only the requested local decision event. No
network, model, remote service or reminder is involved.

## How the queue shows decisions

Each `review-titles` item, including `UNAVAILABLE`, now includes `review_state`:

- `state`: effective state for the current content/title snapshot.
- `state_revision`: latest decision event ID, or 0 when none exists. This is an
  opaque optimistic-concurrency revision, not a per-conversation event count.
- `recorded_state`: most recent explicitly stored decision, if any.
- `decision_current`: whether that event matches current raw content and title revision.
- `stale_decision`: whether a stored event no longer matches.
- Current content hash and title revision for a possible explicit decision.

If message identity/role/text or the local title revision changes, the prior
decision becomes **stale** and the effective state is `open`. Its recorded state
and event revision remain visible; nothing is deleted. Refresh before deciding.
The content hash uses the existing full raw-message identity/role/text contract,
not timestamps, provenance metadata, original files or a remote platform snapshot.
Changes only to those unhashed fields do not invalidate the state. This is not a
universal immutable export checkpoint or an authenticated consent record.

All queue state, title and evidence fields use the queue's one SQLite read
transaction. A later concurrent decision can make that queue stale immediately.
The explicit setter always checks again inside its write transaction.

Decisions do **not** automatically hide items. `--unrenamed-only` still means no
local title-history entry, not “open review state”; skipped/deferred items with no
title change remain visible. Omit that filter to revisit a renamed conversation's
decision. This avoids silently treating a skip as a completed rename. There is no
skip-state filter or automatic reminder in this increment.

## Storage and failure boundaries

The first successful explicit decision creates an additive `title_review_history`
table and index in the selected existing archive. Old archives need no migration
for read-only use. Events contain source, conversation, state, raw-content hash,
local title revision and a database timestamp. No free-text notes, message bodies
or proposed titles are stored in the decision table. The latest event wins; older
events are retained. The CLI currently shows the latest event, not a history browser.

Writes use `BEGIN IMMEDIATE`. Source/conversation existence and all three expected
values are checked before schema mutation. Table/index creation and event insertion
are in one transaction. A failed first insert rolls back schema creation too. Two
writers with the same lease cannot both succeed; the loser must refresh. No missing
database is created, and read-only operations never create schema.

The ledger is local and unsigned. Anyone who can edit the database can alter it;
it is not a tamper-proof audit log or security permission store. A changed source
file not reimported into the archive is not checked here. Original export-backed
title commands retain their separate provenance validation.
