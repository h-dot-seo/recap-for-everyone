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
decision. This avoids silently treating a skip as a completed rename. Use the explicit `review-titles --state open|skipped|deferred` filter described
below when you want one state. There is no automatic reminder.

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


## Revisit a chosen effective state

After recording decisions, explicitly choose the queue view you want:

```sh
python recap.py --db ../recap-demo/archive.sqlite review-titles --source web-demo --state open
python recap.py --db ../recap-demo/archive.sqlite review-titles --source web-demo --state deferred
python recap.py --db ../recap-demo/archive.sqlite review-titles --source web-demo --state skipped
```

Omitting `--state` still shows all states. This is a **read-only view**, not a new
state change. Selecting a deferred item does not reopen it or apply a title. Use
its current lease in an explicit `review-state --set open` command if you decide
to resume. Alternatively, deliberately preview and apply a title; that new title
revision makes the prior decision stale under the existing rules.

Filtering uses each conversation's **effective current state**, not only the
stored event label. A skipped/deferred event whose content hash or title revision
is stale appears in `--state open`, not in skipped/deferred. The recorded old
decision and `stale_decision` remain visible. Missing decision history is open.
An open item is not proof of poor title quality or an instruction to change it.

`--state` can be combined with `--unrenamed-only`: the conditions intersect. A
renamed conversation with a stale decision is open, but still excluded by the
unrenamed filter. If revisiting all deferred/skipped decisions is your goal,
consider omitting `--unrenamed-only` so title history does not narrow the scope.

Counts are exact for the single read snapshot:

- `source_total_conversations`: all conversations in the explicit source.
- `excluded_renamed_conversations`: removed first by the optional history filter.
- `excluded_review_state_conversations`: removed next by effective-state filtering.
- `total_conversations`: remaining eligible conversations, before page selection.

These three latter counts sum to the source total. `review_state_filter` records
the selected state or null. Page offsets and `next_offset` address only that final
eligible set. After a decision, import or title change, refresh at offset 0 instead
of advancing a saved offset; membership may have moved between state views.

**Cost and privacy scope:** a stale decision cannot safely be detected by SQL
label filtering alone. With `--state`, the tool reads and hashes full raw message
identity/role/text for **every conversation left after the optional unrenamed
filter**, even when the requested page is small or empty. It scans inventory in
100-conversation chunks and handles one conversation's messages at a time. Only
page metadata is retained; page conversations are read again for proposals inside
the same database snapshot. This is not constant-memory processing for a very
large individual conversation, nor a cheap metadata-only filter. No streaming or
performance claim is made for large archives. Without `--state`, only the selected
page's message contents are loaded for proposals as before.

Existing-title collision checks still cover current titles throughout the chosen
source, including conversations excluded by either filter. Candidate-proposal
collisions remain page-only. All scans, counts, state checks and page proposals
share one SQLite read transaction; later changes can still make the result stale.
No source files, messages, titles or decisions are written by filtering. Content
search remains complete for the imported raw archive regardless of the view.
