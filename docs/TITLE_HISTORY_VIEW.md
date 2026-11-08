# Review earlier local titles without opening message bodies

Use the explicit history view when you remember changing a title and want to
compare earlier wording. Unlike `title`, this command does not generate an excerpt
or select message-body columns. It still displays **private titles**, including
wording deliberately removed from the current label. Keep its output private.

```sh
python recap.py --db ../recap-demo/archive.sqlite title-history --source web-demo --conversation synthetic-chat --limit 20
```

The standalone equivalent is:

```sh
python title_history.py --db ../recap-demo/archive.sqlite --source web-demo --conversation synthetic-chat --limit 20
```

Both require the exact source label and conversation ID. They do not discover
accounts, scan original session directories, call a model or contact a service.
They do not change titles, approval state, source files or database schema. A
missing database is not created, and an unknown conversation is an error even if
an orphaned history row exists for its identity.

## What the response means

- `display_title` and `revision` describe the current local display label.
- `original_title` is the title on the first archived message in insertion order.
  `original_revision: 0` is a convention, not a stored or timestamped change event.
  It is not necessarily the first or current title on the remote platform.
- `changes` contains local write events, newest revision first. Each has `revision`,
  `title`, `previous_title`, `changed_at` and `is_current`. Timestamps are displayed
  as stored; ordering uses revision IDs, not timestamp parsing.
- The current override is included as an event and marked `is_current: true`.
  A page containing only older events has no current marker even though the
  top-level current title remains visible.
- Repeated wording, no-op writes and reversals remain separate events. Revisions
  are global database IDs and can have gaps within one conversation. Do not infer
  a revision from an event count, array position or previous revision plus one.
- `total_changes` excludes the original-title convention. `returned_changes`,
  `remaining_changes`, `next_offset` and `truncated` describe the requested page.
  An offset at or past the end returns an empty page and no continuation.
- `contains_message_text: false` means no message-body field was selected. A title
  itself can contain a copied message excerpt or other private information.

The default limit is 20, with an explicit range of 1 through 1000. Offset must be
an integer from zero through 9223372036854775807. Source and conversation strings
are not trimmed or Unicode-normalized. A database without title history returns
the original as current, revision 0 and no changes; it is not migrated by reading.
Empty, multiline or otherwise legacy-invalid original titles remain unchanged in
the output. They may not qualify for a new manual title write.

## Read additional pages against a checked revision

Each call reads the original title, current override, count and page in one SQLite
read transaction. Separate calls do not share a snapshot. A new title write shifts
newest-first offsets, so use the **top-level current revision** from your first page
as `--expected-revision` on later pages. Do not use a selected event's revision.

For example, if the first page reports `revision: 7` and `next_offset: 20`:

```sh
python recap.py --db ../recap-demo/archive.sqlite title-history --source web-demo --conversation synthetic-chat --limit 20 --offset 20 --expected-revision 7
```

If that conversation's title changed, this fails with `stale title history`.
Restart at offset 0 and review again. Writes to a different conversation do not
invalidate this guard. Omitting the guard is allowed and reads fresh state, but
pages may then skip or repeat events. The guard detects normal local title writes,
not imports, changed message content or arbitrary external database edits. It is
not an authorization token, a signed document or evidence that a human reviewed it.

SQL limits event rows before Python materialization; no message-body value is
selected or excerpt generated. Exact counting and sorting can still scan history. There is no
total byte, native query-work or latency bound: individual old strings and IDs may
be large. The existing `title` response remains unchanged for compatibility.

## Deliberately reuse earlier wording

This view adds no restore or undo command. A reversal is an ordinary explicit
local title write that appends history; it does not erase the intervening labels.
Read the selected wording for meaning and privacy, and inspect relevant messages
separately if needed. Older wording is not automatically better or safe.

If the **current top-level** revision is 7 and you deliberately choose the literal
title below, the existing checked operation is:

```sh
python recap.py --db ../recap-demo/archive.sqlite title --source web-demo --conversation synthetic-chat --set "Synthetic orchard comparison" --expected-revision 7
```

Replace that title and revision with the values you actually reviewed. Stop on a
stale error and re-read; never edit or guess a revision to force the write. The
write lock checks the current title revision before appending the new event. This
manual route does not bind message content. Use a fresh proposal and
[preview/apply flow](TITLE_REVIEW_EVIDENCE.md) when you need the content fingerprint
and checked user-message evidence as well. Neither route changes a remote title.

New manual titles must remain nonempty single lines of at most 200 code points
without prohibited controls or surrogate characters. An archived original can
violate those rules; review and choose valid wording rather than assuming it can
be reapplied byte-for-byte. Command-line wording can be visible in shell history
and process listings, so never put secrets there. A new event preserves all old
labels, even if the new title is less revealing.

To locate a conversation when you only remember an older title, use the separate
[opt-in historical search](TITLE_HISTORY_SEARCH.md). That search can include body
snippets; this exact-identity history view does not.
