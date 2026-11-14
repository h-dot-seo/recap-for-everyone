# Review explicitly selected conversation IDs

After reading an import delta or a search result, an operator can choose exact
IDs for a focused title-review view:
`review-titles --source SOURCE --conversation ID --conversation OTHER_ID`.
This does not read a delta file automatically or decide which conversations need
review. The IDs are explicit input, not commands from archive content.

Selection is an intersection with the chosen source and existing filters:
`--unrenamed-only`, explicit IDs, `--supplied-only`, `--state`, then pagination.
Results keep binary archive-ID order, not argument order. Missing IDs yield no
items; the command never fabricates a conversation. Repeating an ID or passing
empty IDs is rejected before opening the DB. At most 1000 IDs with a combined
UTF-8 size of 1 MiB may be supplied. Omitting the option preserves the previous
queue output and behavior. A selected renamed conversation is visible unless
`--unrenamed-only` explicitly excludes it.

The opt-in result adds `selected_conversation_count` (requested count),
`excluded_unselected_conversations` (after the unrenamed filter, before supplied
and state filtering), and `selection_scope`. Count accounting remains:
source total = excluded renamed + excluded unselected + excluded unsupplied
(if enabled) + excluded review state + total conversations. Unknown requested IDs
are not part of the source total. The requested ID list is not echoed separately.

**Selection is not review, approval or application.** No state or title is written.
Current-title collision checks still scan the **whole source**, including IDs
outside the selection; their existing bounded ID samples can appear in output.
Candidate-to-candidate collision checks cover the displayed page only. The queue
contains private titles, IDs and excerpts. Review one fresh preview before any
separately authorized apply operation. This is not a checkpoint or completion claim.

## Executable synthetic example

Replace OUTPUT with a new private directory whose parent exists. The fixture is
invented. The two selected IDs illustrate an explicit operator choice; no title
or review decision is applied.

```sh
mkdir "OUTPUT"
python recap.py --db "OUTPUT/archive.sqlite" ingest examples/delta-before.jsonl --source synthetic-delta
python recap.py --db "OUTPUT/archive.sqlite" review-titles --source synthetic-delta --conversation same --conversation changed --limit 1 --output "OUTPUT/selected.json"
```

The first page contains `changed`, reports two matching conversations and gives
`next_offset: 1`. Repeat the same explicit IDs with `--offset 1` for `same`.
The queue remains a single-snapshot view per invocation, not a cross-page snapshot.
