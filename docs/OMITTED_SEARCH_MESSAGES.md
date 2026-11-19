# Find useful user evidence beyond the three search samples

By default, `find` returns conversations, with at most three sampled matching messages in each.
Those samples can all be assistant messages even when a later user request also
matches. `message_matches_truncated: true` says matching messages were omitted.
`next_cursor` only continues **conversations**, not those omitted messages. A null
cursor and `remaining_matches: 0` do not mean every matching message was displayed.
Raising `find --limit` increases the conversation count, not the three-message cap.

## Page through matching bodies

Copy the exact source and conversation ID from a search result. For the fixture
below, run `python recap.py --db ../recap-message-review-demo/archive.sqlite find "cobalt orchard" --source demo --conversation synthetic-message-review --limit 20`.
Repeat with the same query and filters, passing the returned `next_offset` as
`--offset` until it is null. The fixture returns 66 matches in pages of 20, 20,
20 and 6. The final page includes the user request `focus-user`. Adding
`--text-role user` to the first call returns that one matching request directly.

The `recap.matching-messages.v1` result counts each eligible body containing
**any** folded literal query term once. Terms can appear in different messages.
Ordinary conversation search also considers titles and requires all terms
somewhere in the conversation. A title alone contributes zero matching bodies.
The scoped command also works directly when you already know the IDs. An unknown
source/conversation pair reports an error. A known pair with zero matching bodies
returns an empty page.

`message_match_count` counts all matching bodies before paging. `message_matches`
contains at most `--limit` excerpts (default 20, range 1–1000) in archive insertion
order. `--offset` counts matching bodies from zero. Excerpts use the original
text, with code-point offsets, `source_sha256` and `source_line`. Apply the same
`--canonical-unicode`, `--text-role`, `--from`, `--until` and `--export-sha256`
options used for the initial search. An export filter also returns up to three
matching original locators per body. Each call scans the scoped rows in a fresh
read-only snapshot for its exact count. Imports between calls can change the result.
Conversation cursors and title-history matching apply only to conversation pages.

To read full text and surrounding messages, use the scoped `show` pages in the
walkthrough and follow `selection.next_offset`. Read the role and text before
choosing a user message for a title.

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

The walkthrough uses full-text `show` pages to review the surrounding conversation.
The fixture has no completed-turn markers for the narrow replay engine. The legacy
message-level `search` command uses FTS token semantics.

`show` and scoped `find` pages are in raw archive insertion order. They can include assistant/tool
messages, alternate web branches, rolled-back local turns and multiple imported
export versions, depending on the archive. They are not active-branch, retained-turn
or source-attributed views. For those narrower scopes, use the existing verified
[branch/replay title workflow](TITLE_WALKTHROUGH.md) or
[source-attributed workflow](SOURCE_ATTRIBUTED_TITLES.md) instead of assuming a raw user
role establishes the intended evidence. A selected assistant ID fails title
suggestion; it is not silently replaced with another message.

On `show` pages, a page limit bounds the number of messages, not their byte size
or number of provenance occurrences. Full message text is displayed, so this is
broader private-text exposure than a search excerpt. Keep outputs private and use [exact message or nearby-context
views](MESSAGE_SELECTION.md) when you already know the needed ID. Generation,
preview and explicit apply retain their separate full-content and revision checks.
