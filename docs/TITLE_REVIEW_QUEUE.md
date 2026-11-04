# Review a page of title proposals

`review-titles` addresses a common archive task: inspect multiple local title
suggestions without repeatedly invoking a command for each conversation. It never
applies titles, sends content to a model or changes a remote platform. It uses the
same local extractive algorithm as `suggest-title`, not semantic summarization.
To review previously prepared web-branch, local-attributed, operator or model
candidates instead, use [supplied title review](SUPPLIED_TITLE_REVIEW.md) with
repeatable `--proposal` options. That opt-in mode does not generate raw fallbacks.

After deliberately importing your supported web/local files into a private archive:

```sh
python recap.py --db ../recap-demo/archive.sqlite review-titles --source web-demo --limit 20 --offset 0 > ../recap-demo/queue.json
```

Use a new private scratch directory outside the repository and UTF-8 redirection,
as in [the walkthrough](TITLE_WALKTHROUGH.md). Check the command exit status before
opening output. A failed command may leave an empty file. The output contains
**private titles, excerpts and IDs**, not just counts.

## What to review

Items are ordered by the exact conversation ID using binary database ordering.
The source is required; cross-source review is not implicit. The default page is
20 conversations, with an explicit maximum of 100. Offset is an integer from 0
through SQLite's signed 64-bit maximum (9223372036854775807). `next_offset` is null at the end.
`ready_count` and `unavailable_count` count only items on this page.

Each `READY` item includes:

- Conversation identity, current display title and current title revision.
- Whether a local title override already exists (`previously_renamed`). These
  conversations are not silently excluded or overwritten.
- A proposal with one user-message excerpt, its evidence ID, provider label and
  fingerprint of the full archived conversation.
- `action: no_change` when the exact proposed title already matches the current
  title, otherwise `review_rename`. Do not apply no-op proposals merely to clear
  a queue: the normal title writer would append another revision.
- Advisory title collision counts and up to 10 identity samples per category.

An item with no valid local user excerpt is `UNAVAILABLE`, has a fixed reason code,
and has no proposal. It does not prevent review of other conversations.

### Collision meaning

Comparison uses Unicode NFKC normalization, case folding and whitespace collapse.
It does not change titles or source text. This can flag full-width/case/spacing
variants as similar, but is **not semantic similarity** or a security confusables
check. Accents and wording differences are not generally merged.

`page_proposal_count` compares generated proposals **on this page only**.
`existing_title_count` compares the proposed title against current display titles
of **all conversations in the selected source**, excluding the item itself. Only
metadata is scanned for that second comparison. Exact totals may exceed the
identity samples, which are capped at 10 per category. No messages from another
source are included. Proposal collisions on other pages are not computed.

Warnings are advisory, not a uniqueness constraint. You may choose a more useful
manual title, skip the item, or inspect the evidence. The tool never appends
invented distinguishing facts, silently renames collisions or claims uniqueness.
Another title change can invalidate these collision observations immediately.

## Select exactly one proposal for a fresh preview

After reading the queue, select an exact `READY` conversation:

```sh
python recap.py --db ../recap-demo/archive.sqlite preview-title ../recap-demo/queue.json --conversation synthetic-chat > ../recap-demo/reviewed.json
```

This checks the selected proposal using the same validation as an individual
proposal. Queue/proposal source and conversation must agree and exactly one queue
item must match. Duplicate items, unavailable items and mismatched identities are
rejected. The queue is **unsigned**: titles and metadata are untrusted input, not
proof of approval. The normal proposal validator still checks provider, title,
evidence membership and full raw-content fingerprint.

Read the newly generated `reviewed.json`, including `previous_title` and
`expected_revision`, before explicitly applying that one title:

```sh
python recap.py --db ../recap-demo/archive.sqlite apply-title ../recap-demo/reviewed.json
```

Do not pass the whole queue to `apply-title`; it is not an applicable preview.
There is intentionally **no apply-all command**. `preview-title` without
`--conversation` continues to accept a single ordinary proposal as before.
If you edit a selected proposal's title, use the ordinary proposal-preview path
and review it again; never edit a reviewed lease to bypass a stale rejection.

## Snapshot and raw-history boundaries

A queue's current titles, proposed evidence and collision checks come from **one
SQLite read transaction**. This prevents internal mixing of database versions.
It does not lock later writers or create a permanent snapshot. Re-running with an
offset uses a new snapshot, so concurrent imports can shift pagination: refresh
rather than treating pages as a durable work ledger. Queue limits bound item count,
not file/message byte size; each selected conversation is loaded in full to hash
it, and existing title metadata is scanned across the source. No streaming or
constant-memory claim is made for arbitrarily large conversations/titles.

Selection for `preview-title` creates a **fresh** title-revision lease. If the title
changed since the queue, the new preview shows the new current title/revision and
must be reviewed again. If raw content changed, the stale proposal fingerprint is
rejected. Applying a reviewed preview rechecks content and revision transactionally;
it does not rerun advisory collision checks or enforce unique titles.

This queue deliberately uses **raw archive order**, including all imported web
branches and local records from rolled-back turns. It does not choose web
`current_node` or reconstruct Codex history. Use `suggest-branch-title` or
`suggest-replay-title` individually when their explicit export-backed context is
needed. Their narrower provenance checks and unsupported cases are unchanged.
No raw history is deleted to make a title look cleaner.

## Keep already renamed conversations out of a working page

In the bundled synthetic workflow test, 12 invented web conversations and 12 local
sessions share one archive source. The default 20-item page originally contains
three previously renamed conversations. After two more explicit title changes,
that same page still contains all five; its identity order does not change. This
is correct for an inventory, but creates repeated manual scanning while organizing
many titles. It is a synthetic workflow check, not a measurement of real usage or
of title quality.

Use the opt-in filter when you specifically want conversations with **no existing
local title-history record**:

```sh
python recap.py --db ../recap-demo/archive.sqlite review-titles --source web-demo --unrenamed-only --limit 20 --offset 0 > ../recap-demo/queue.json
```

The condition is applied in SQL **before pagination**, not by hiding items after
fetching a page. With the option:

- `total_conversations` counts eligible conversations in this source.
- `source_total_conversations` counts all conversations in the source.
- `excluded_renamed_conversations` reports the difference.
- `filter` describes the applied condition. Without the option, all conversations
  remain eligible and the excluded count is zero.

All eligibility, counts, current titles, evidence and duplicate checks still use
one database read transaction. Existing-title collision checks continue to include
renamed conversations from the selected source; they do not disappear just
because their proposals are filtered out. Unknown/missing title-history tables in
legacy archives mean no recorded local rename and leave all conversations eligible.

Select one proposal, make any deliberate wording change, preview, review and apply
as described above. Then **refresh at offset 0** to work from the remaining eligible
set. Applying a local title creates history, so that conversation no longer appears
in this filtered view. Continuing with an old offset after rows leave the eligible
set can skip work; offsets are not stable cursors. `next_offset` is useful while
browsing a snapshot's unchanged order, not as a durable completion checkpoint.

The filter does **not** mean “needs review” or “safe title.” Any title-history entry
counts, including a no-op write, an old override or an override later reverted to
the original title. A conversation with a good original title but no local history
still appears. `UNAVAILABLE` and `no_change` items also remain eligible: there is no
persistent skip/accept decision ledger. Do not apply artificial no-op changes merely
to dismiss these items. Omit the filter to revisit previously renamed titles.

Filtering changes only the read-only queue. It does not delete conversations,
remove raw private text, reset titles or modify source files. The existing rename
and content-search history remain available. Excerpts/duplicate warnings/possible
private-detail hints retain all their semantic and privacy limitations.


To revisit explicit decisions, use `--state open`, `--state skipped` or
`--state deferred`. The filter uses current content/title-bound state, so stale
skip/defer events return to open. It scans and hashes all conversations eligible
after the optional unrenamed filter before paginating; this is an opt-in full
content scan, not a metadata-only shortcut. See [state-view counts, concurrency
and cost](TITLE_REVIEW_STATE.md#revisit-a-chosen-effective-state).
