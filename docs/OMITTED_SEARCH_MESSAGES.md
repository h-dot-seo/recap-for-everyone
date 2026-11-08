# Find useful user evidence beyond the three search samples

`find` returns conversations, with at most three sampled matching messages in each.
Those samples can all be assistant messages even when a later user request also
matches. `message_matches_truncated: true` says matching messages were omitted.
`next_cursor` only continues **conversations**, not those omitted messages. A null
cursor and `remaining_matches: 0` do not mean every matching message was displayed.
Raising `find --limit` increases the conversation count, not the three-message cap.

Use the existing scoped `show --limit ... --offset ...` pages to inspect the rest of
that conversation. Follow `selection.next_offset` until null, choosing the exact
source and conversation returned by search. These pages include **all messages**,
not just matches. Read the role and text before choosing a user message for a title;
do not treat the first assistant sample as eligible user evidence. Term-coverage
flags describe query coverage, not human authorship or useful title wording.

## Copyable synthetic walkthrough

The shipped example has 67 messages: a generic opening user request, 65 assistant
status notes containing `cobalt orchard`, and a final substantive user request.
All IDs and text are invented. Choose a new private directory outside the repository;
do not reuse an existing directory or output filename. Run from the repository root
with your working Python launcher. Check each exit status and inspect each result.

```sh
mkdir ../recap-message-review-demo
python recap.py --db ../recap-message-review-demo/archive.sqlite import examples/message-review-local.jsonl --format local-codex --source demo
python recap.py --db ../recap-message-review-demo/archive.sqlite find "cobalt orchard" --source demo
```

The result has one conversation, `synthetic-message-review`, and 66 matching message
bodies. Its three samples are `status-00`, `status-01` and `status-02`, all assistant
messages. It reports `message_matches_truncated: true` even though `next_cursor` is
null. All query terms are sampled, but the useful later user request is not.

Browse the conversation in bounded pages:

```sh
python recap.py --db ../recap-message-review-demo/archive.sqlite show --source demo --conversation synthetic-message-review --limit 20
python recap.py --db ../recap-message-review-demo/archive.sqlite show --source demo --conversation synthetic-message-review --limit 20 --offset 20
python recap.py --db ../recap-message-review-demo/archive.sqlite show --source demo --conversation synthetic-message-review --limit 20 --offset 40
python recap.py --db ../recap-message-review-demo/archive.sqlite show --source demo --conversation synthetic-message-review --limit 20 --offset 60
```

The pages return 20, 20, 20 and 7 messages, with `next_offset` values 20, 40, 60 and
null. These particular offsets belong to this fixture. For your own conversation,
follow the returned offsets rather than assuming these numbers. `message_count`
continues to describe the whole conversation. On the last page, `focus-user` has
role `user` and text `Compare cobalt orchard irrigation designs`.

After reading that evidence, explicitly choose its archived ID:

```sh
python recap.py --db ../recap-message-review-demo/archive.sqlite suggest-title --source demo --conversation synthetic-message-review --message focus-user --output ../recap-message-review-demo/proposal.json
python recap.py --db ../recap-message-review-demo/archive.sqlite preview-title ../recap-message-review-demo/proposal.json --with-evidence --output ../recap-message-review-demo/reviewed.json
```

The default suggestion would use the generic opening question. The selected
proposal instead uses `focus-user` and the substantive request, with the unchanged
80-code-point excerpt cap. Inspect the actual saved UTF-8 proposal and preview,
including source, conversation, user evidence, wording, previous title and expected
revision. The fixture's original local title is empty and expected revision is zero.
A `SAVED` receipt or an inspected page is not approval. No title changed yet.

Only after that review:

```sh
python recap.py --db ../recap-message-review-demo/archive.sqlite apply-title ../recap-message-review-demo/reviewed.json
python recap.py --db ../recap-message-review-demo/archive.sqlite find "cobalt orchard" --source demo
```

The conversation now has display title `Compare cobalt orchard irrigation designs`
and matches its title as well as its unchanged message bodies. Its title revision
is positive. Original messages, original title, source bytes and provenance remain
intact. Nothing is renamed in the source application.

## Scope and limits

This bridge uses existing commands; it does not add a new search mode or treat
search samples as exhaustive. The fixture demonstrates raw message paging only;
it has no completed-turn markers for the narrow replay engine. The legacy
message-level `search` command has different
FTS token semantics and is not a continuation token for `find` samples.

`show` pages are in raw archive insertion order. They can include assistant/tool
messages, alternate web branches, rolled-back local turns and multiple imported
export versions, depending on the archive. They are not active-branch, retained-turn
or source-attributed views. For those narrower scopes, use the existing verified
[branch/replay title workflow](TITLE_WALKTHROUGH.md) or
[source-attributed workflow](SOURCE_ATTRIBUTED_TITLES.md) instead of assuming a raw user
role establishes the intended evidence. A selected assistant ID fails title
suggestion; it is not silently replaced with another message.

Each page is a fresh read-only database snapshot. New imports can affect later
pages; these offsets are not a cross-call content lease. A page limit bounds the
number of messages, not their byte size or number of provenance occurrences.
Full message text is displayed, so this is broader private-text exposure than a
search excerpt. Keep outputs private and use [exact message or nearby-context
views](MESSAGE_SELECTION.md) when you already know the needed ID. Generation,
preview and explicit apply retain their separate full-content and revision checks.
