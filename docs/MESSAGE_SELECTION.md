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

## Structured results and evidence scope

The conversation's source, identity, original/current title, title revision and
`message_count` remain unchanged. **`message_count` always counts the entire
conversation**, not just this page. The additional `selection` object contains:

- For a page: `mode: "page"`, `limit`, `offset`, `returned_messages` and `next_offset`.
- For one message: `mode: "message"`, the requested `message_id` and
  `returned_messages: 1`.

`messages` includes only the selected records, with their complete archived text,
original message title, normalized-artifact hash/line and recorded original-export
provenance. Ordering is archive insertion order, not a date sort or active-branch
reconstruction. Original line numbers/locators are not renumbered for a page.

Both legacy and additive provenance ledgers remain supported; their union removes
duplicate occurrences. Normalized-only archives still return empty provenance
lists. Selection does not repair, verify or rewrite any source evidence.

This is a conversation/message selection, **not an original-export filter**. Opening
a hit from `find --export-sha256` displays every recorded provenance occurrence for
that selected archived message and current conversation-wide title metadata. It
does not silently load other messages from the conversation.

## Snapshot, privacy and resource limits

Each call reads metadata, selected bodies and provenance in one SQLite snapshot.
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
