# Read a message or a bounded conversation page

A search result gives a `source_id`, `conversation_id` and a `message_id` for each
sample. Use those exact identities to open its complete archived evidence without
printing every other message in a long session:

```sh
python recap.py --db ../archive.sqlite show --source demo --conversation synthetic-chat --message m2
```

The same options work with `conversation_view.py`. `--message` is an exact identity
match, not a title, source-file line number, substring or query. The explicit source
and conversation keep identical IDs in other conversations or sources separate.
An unknown message produces an error without creating or changing the archive.

After inspecting a useful **user** message, `suggest-title --message ID` can use
that exact message for a reviewable local title excerpt. This is a separate action,
not an automatic consequence of opening a search hit. See [explicit title evidence
selection](TITLE_REVIEW_HINTS.md#choose-a-more-informative-user-message) for the
complete generate/preview/apply workflow and raw-history scope limitations.

## Page through a longer conversation

```sh
python recap.py --db ../archive.sqlite show --source demo --conversation synthetic-chat --limit 1
python recap.py --db ../archive.sqlite show --source demo --conversation synthetic-chat --limit 1 --offset 1
```

`--limit` accepts 1 through 1000 messages. `--offset` is zero-based and requires an
explicit limit when nonzero. Read the returned `selection.next_offset` to request
the next page; `null` means there are no more messages in this snapshot. An offset
past the end returns an empty message list and the conversation summary. You cannot
combine an exact message selection with a page limit or nonzero offset.

No selection flags preserves the original full-conversation view.

## Read bounded neighbors around a search hit

When a single hit is not enough to understand the archived record, request raw
neighbors around its exact message ID without finding its page offset first:

```sh
python recap.py --db ../archive.sqlite show --source demo --conversation synthetic-chat --around-message m2 --before 1 --after 1
```

The same flags work with `conversation_view.py`. Omitting `--before` or `--after`
uses two neighbors on that side. Each count accepts an integer from 0 through 50,
so a context view contains at most 101 messages including the anchor. Counts clip
at conversation boundaries; missing neighbors are not invented. Both counts zero
returns just the anchor. An unknown anchor fails rather than choosing another ID.

`--around-message` cannot be combined with `--message`, `--limit` or a nonzero
`--offset`. `--before` and `--after` require the around-message selector; they do
not silently broaden exact-message or full-conversation views. The Python API
appends `around_message_id=None, before=None, after=None` to the existing
`conversation(...)` parameters. Booleans/fractions are not accepted as counts.
Detail views require explicit text source/conversation identities, never numeric
coercion or `None` as an implicit cross-source lookup. Accepted strings remain exact.

The context selection reports:

- `anchor_message_id`, `anchor_index` within the returned list, and `anchor_offset`
  within the entire conversation. Offsets count messages in archive order.
- Resolved requested `before`/`after` counts and actual `returned_before`/
  `returned_after` counts, plus `returned_messages`.
- `offset`, the first returned message's conversation ordinal, and the exact
  `omitted_before`/`omitted_after` counts.
- `next_offset`, usable with ordinary page selection after this window, or null
  when no later messages exist in this snapshot. This is not a durable cursor.

This is a broader private-text view than `--message`: neighbors can include other
roles, alternate web branches, discarded local history or later imported export
versions. They are **adjacent in archive insertion order**, not necessarily prior
or next turns, replies, timestamp order, or semantic context. Use `web-branch` or
supported replay workflows when you need those different source-specific views.

In particular, opening a hit from `find --export-sha256` does **not** restrict its
neighbors to that export. Source/conversation scope stays exact, but all recorded
export versions in that conversation are eligible. The result labels this scope
explicitly and preserves every returned message's original provenance.

## Structured results and evidence scope

The conversation's source, identity, original/current title, title revision and
`message_count` remain unchanged. **`message_count` always counts the entire
conversation**, not just this page. The additional `selection` object contains:

- For a page: `mode: "page"`, `limit`, `offset`, `returned_messages` and `next_offset`.
- For one message: `mode: "message"`, the requested `message_id` and
  `returned_messages: 1`.
- For anchored neighbors: `mode: "context"` and the counts/offsets described above.

`messages` includes only the selected records, with their complete archived text,
original message title, normalized-artifact hash/line and recorded original-export
provenance. Ordering is archive insertion order, not a date sort or active-branch
reconstruction. Original line numbers/locators are not renumbered for a page.

Both legacy and additive provenance ledgers remain supported; their union removes
duplicate occurrences. Normalized-only archives still return empty provenance
lists. Selection does not repair, verify or rewrite any source evidence.

This is a conversation/message selection, **not an original-export filter**. Using
`--message` on a hit from `find --export-sha256` displays every recorded provenance
occurrence for that message and current conversation-wide title metadata. Exact
message mode does not load other messages. The explicit around-message mode above
adds eligible neighbors regardless of their original-export hash.

## Snapshot, privacy and resource limits

Each call reads metadata, anchor/window bounds when requested, selected bodies
and provenance in one SQLite snapshot. Context queries locate only bounded nearby
message keys before fetching bodies; gaps and interleaved source IDs do not
change the scoped order.
Separate page requests can see new imports or title changes between calls. These
are offset pages, not a durable cross-request snapshot or cursor.

SQL restricts both body retrieval and provenance retrieval to selected messages,
so Python does not buffer all the unselected text or occurrence records. Summary
counts still inspect conversation metadata in SQLite. A single very long message
or a message with many recorded occurrences can still produce a large result; a
message limit is not a byte limit or an absolute memory guarantee.

The output contains private conversation text, titles and identifiers. Keep it
outside the public repository and review it before sharing. Both CLIs escape
Unicode for JSON output that remains usable on ASCII terminals; escaping is not
redaction. No files, database records, titles, remote services or permissions change.

To save these same selections as readable UTF-8, use `render --format markdown`
or `render --format html` with a required new `--output` path. The saved file keeps
selection/context warnings and provenance; stdout is only a private saved-view
receipt. The 16 MiB output cap does not turn a message-count bound into an input
memory limit. See [Markdown views](RENDER_MARKDOWN.md) and
[HTML views](RENDER_VIEWS.md).
