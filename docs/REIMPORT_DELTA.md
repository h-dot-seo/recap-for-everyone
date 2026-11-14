# Conversation identity delta before re-import

`check-import` now adds `conversation_delta` counts for incoming conversations
inside the same read-only snapshot as its existing message comparisons. It does
not import, change titles, modify provenance or advance any checkpoint.

Every incoming conversation belongs to exactly one category, in this priority:

1. `conflicting`: any archive or repeated-input value conflict, even when new IDs
   also occur. A title-only conflict still blocks the entire import.
2. `new`: no stored message exists for this conversation in the selected source.
3. `has_new_identities`: the conversation exists and has at least one incoming
   message identity not stored in this source, with no detected conflict.
4. `no_new_identities`: no incoming new identity or conflict was found.

The four counts sum to `conversations`. Repeated identical input rows do not
inflate conversation counts. Conversations only in the archive are not classified.
Optional web/local selection limits the incoming population; normalized input
still does not support conversation selection. Source IDs remain separate.

These are mechanical identity comparisons, not growth, deletion, activity, review
completion or completeness claims. Local basename/line-derived IDs can change
when a file is renamed; an edited branch can introduce new IDs. `NO_CONFLICTS`
is not import authorization. The importer rechecks under its own write lock.

## Private ID samples

`--delta-output NEW_JSON` optionally writes `recap.import-conversation-delta.v1`
with binary-sorted ID samples limited by `--limit` **per category**, omitted
counts and the same count summary. Stdout retains status/conflicts/counts and
adds only a file hash/byte receipt, not delta IDs. Existing selection coverage may
already include a selected private ID. The file contains no message bodies, but
conversation IDs and source IDs are private. It is unsigned, not a durable cutoff.

An occupied output path, including a dangling symlink, is rejected before input
reads. Publication is exclusive and atomic; output size is limited to 8 MiB.
A requested file is also written when conflicts exist, then the command exits 1
as before. No file is written when validation or publication fails. The standalone
`import_check.py` accepts the same option. No delta file is written without it.

## Executable synthetic example

Replace OUTPUT with a new private directory whose parent exists. The two invented
normalized files demonstrate all four categories and a title-only conflict. The
last command is expected to exit 1 because the conflict is deliberately supplied.

```sh
mkdir "OUTPUT"
python recap.py --db "OUTPUT/archive.sqlite" ingest examples/delta-before.jsonl --source synthetic-delta
python recap.py --db "OUTPUT/archive.sqlite" check-import examples/delta-after.jsonl --source synthetic-delta --format normalized --delta-output "OUTPUT/delta.json" --limit 2
```

The result has one conversation in each category. `archive-only` is not counted.
The archive remains unchanged by the check; inspect the private file before taking
any separately authorized import or review action.

To review operator-chosen IDs from this private delta, use repeated
`review-titles --conversation ID`; see [selected title review](SELECTED_TITLE_REVIEW.md).
Nothing selects, approves or applies them automatically.
