# Find messages associated with one original export

A source ID is an operator-chosen namespace, not necessarily a single file. If you
import web and local exports into the same source, ordinary `find` searches all of
them. Use an explicit original-export hash to restrict the **message bodies**:

```sh
python recap.py inspect examples/web-export.json --format web
python recap.py --db ../recap-demo/archive.sqlite find "orchard" --source web-demo --export-sha256 ORIGINAL_SHA256
```

Replace `ORIGINAL_SHA256` with the exact lowercase `original_sha256` from inspection
of the original file you intentionally imported. This is the whole original file's
SHA-256, not a message hash, normalized artifact hash or title-proposal content hash.
It is a 64-character lowercase hexadecimal value. Use the private database and
scratch-directory precautions from the walkthrough. There is no automatic path
scan, export discovery, upload or remote lookup.

The standalone `conversation_search.py` accepts the same `--export-sha256` option.
It can be combined with `--source`, `--limit` and the explicit
`--include-title-history` option. Omitting it preserves ordinary search scope.

## What the filter does and does not mean

A message is eligible only if its source, conversation and message identity have
an occurrence linked to that exact original hash in the archive's export provenance
ledger. Both the legacy `export_provenance` and additive `export_occurrences`
tables are supported. Their union avoids duplicate evidence records. Multiple
occurrences of the same message do not duplicate the conversation result.

Only eligible message bodies satisfy query terms. Body snippets and `message_count`
are restricted to those eligible messages. A term found only in another export's
unlinked message cannot satisfy the query. This also works when two exports add
different messages to one archived conversation.

**Current titles and opted-in prior titles remain conversation-wide archive
metadata.** They are not restricted to title wording that existed in that file.
The current/original title anchor remains the archive's first message metadata,
even when that message is not linked to the requested export. A title-only match
can return a conversation if it has at least one eligible message. This is useful
for finding a renamed conversation associated with an old file, but is not a
historical reconstruction of that export's original user interface.

The existing case-insensitive literal AND semantics and ranking are unchanged:
current title first, then opted-in historical titles, then body-only matches.
`total_matches` counts conversations and `limit` caps returned conversations.
Export scope does not filter by timestamps, current web branch, effective Codex
replay history or review decision state.

## Result evidence

Filtered results explicitly report the requested hash and scope. Each conversation
contains `matched_export_sha256` and a `message_count_scope` explanation.
For displayed matching body snippets:

- `source_sha256` / `source_line` still identify the normalized stored artifact.
  They are not relabeled as the original export.
- `export_provenance` shows up to three distinct matching original-export
  hash/locator/parent records, ordered by locator and parent (not chronology).
- `export_provenance_count` is the exact distinct matching occurrence count.
- `export_provenance_truncated` reports whether more than three such records exist.

The usual maximum of three body snippets per returned conversation remains.
Title-only results may have no body snippets; the filter still requires an eligible
message. Use the existing explicit `show` command if you intentionally need the
whole archived conversation and its provenance, including other exports.

`export_provenance_available` reports whether either supported ledger table exists.
It does not prove that the requested hash has entries. A nonexistent hash returns
zero matches. An archive produced only by direct normalized-JSONL `ingest` has no
export association ledger, so the filtered result is empty and availability is
false. There is deliberately **no fallback from normalized artifact hashes to
original-export hashes**. Ordinary search still works for those archives.

## Preservation, trust and cost

This is a read-only ledger lookup in one SQLite snapshot. It does not reread the
original file, validate its present bytes, repair provenance, delete messages,
rename titles or change review state. The locally stored ledger is unsigned and
can be edited by someone with database access. Recorded association is not an
independent proof that the current archived text still equals a source file.
Export-backed title proposal commands retain their separate file/provenance checks.

The hash identifies recorded original bytes, not an access permission or durable
filesystem path. A source filter further narrows the namespace; without it, the
same original file imported under multiple sources may yield multiple conversations.
Search results can include private text, locators and current/past labels. Filtering
is not anonymization, and opt-in title history can reveal labels intentionally
removed from current display titles. No external service receives these fields.

Eligible bodies are restricted in SQL with provenance-existence conditions. Current
and optional historical title metadata are still scanned in the usual ordered
cursors; matching snippet provenance is read separately inside the same snapshot.
Exact occurrence counts can require reading many ledger rows. This is not a
streaming file search or an indexed full-text query over every provenance field,
and no large-archive timing guarantee is claimed.
