# Export normalized message text

`export-normalized` writes an ingest-shaped, derived JSONL file from one source,
optionally one exact conversation. It opens the archive read-only and uses one
explicit snapshot for counts, omitted provenance and every message. Unlike `show`,
this is a whole-source file export, not a nested conversation view.

## Synthetic walkthrough

Create an empty private directory outside the repository and replace `OUTPUT`
with its path. All example content is fictional. Keep the stdout receipt beside
the private output file. Each command below starts with `python recap.py`.

```sh
python recap.py --db OUTPUT/archive.sqlite ingest examples/conversations.jsonl --source synthetic
python recap.py --db OUTPUT/archive.sqlite import examples/web-export.json --format web --source synthetic
python recap.py --db OUTPUT/archive.sqlite export-normalized --source synthetic --output OUTPUT/messages.jsonl
python recap.py --db OUTPUT/moved.sqlite ingest OUTPUT/messages.jsonl --source moved
python recap.py --db OUTPUT/archive.sqlite stats
python recap.py --db OUTPUT/moved.sqlite stats
```

The message counts match; artifact counts need not. Add `--conversation ID` for
one exact conversation. `--source` and `--output` are required. Missing/empty
selections and missing databases fail without publishing a file. Existing paths,
including dangling symlinks, are refused. The same-directory private staging file
is flushed and fsynced before exclusive hard-link publication; there is no replace
fallback. The receipt reports staging cleanup, including a remaining basename if
cleanup after publication fails. Output directories must already exist.

## Bytes and scope

One JSON object per message has these fields, in order: `conversation_id`,
`message_id`, `role`, `timestamp`, `title`, `text`. Empty titles are retained;
`title` is each message's original source title, never a local display title.
UTF-8 has no BOM. Physical lines end with LF only. JSON uses non-ASCII Unicode,
finite values and fixed comma-space/colon-space separators. Embedded controls are
JSON escaped, not stripped; Unicode separators, Hangul and emoji are preserved.
Rows use global `message_pk` insertion order, including interleaved conversations.
Exporting, ingesting into an empty archive and exporting again is byte-identical.
Buffering is per message, not per source; a single very large message still needs
memory proportional to that message. Invalid manually modified rows fail closed.

All imported text nodes, alternate branches and discarded/rollback turns remain.
This is not an active branch or effective-history reconstruction. There is no
redaction, content filtering, network access or archive mutation. Separate calls
have separate snapshots and do not establish a shared cross-call snapshot.

## Private file and provenance boundary

PRIVATE FILE: the JSONL includes full message text, original titles and identities.
Keep it and its receipt outside public repositories and shared folders. The receipt
contains counts and a hash, not message text, titles, source/conversation IDs or
output paths. `contains_message_text: true` describes the file;
`receipt_contains_message_text: false` describes the receipt itself.

The receipt schema is `recap.normalized-export-receipt.v1`. Its SHA-256 identifies
only the derived output bytes, not an archive artifact identity or an original
export identity (equal bytes can coincidentally have the same hash). Original
hashes, locators and parent trees are not exported. `omitted_export_occurrences`
counts distinct matching rows in the union of modern and legacy ledgers, with
backfilled duplicates counted once. No origin-field option or ledger import is
provided. Local display titles, title history and review state are excluded.
A new archive starts with original titles and no local title revisions.

Re-ingest records this derived file's hash and physical line as new provenance.
It is not a backup or recovery object for the source archive; keep original exports
and use the SQLite backup and [recovery rehearsal](RECOVERY_REHEARSAL.md) workflow.
Once ingested elsewhere, this file is a required backup object of the new archive.
Do not substitute it for original exports in branch/replay/attributed title,
export-title-plan or original-input title-adapter workflows. No completeness,
authenticity, privacy clearance or recovery success is established by export.
