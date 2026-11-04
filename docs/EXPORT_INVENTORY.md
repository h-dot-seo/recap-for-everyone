# Choose a conversation before importing

`list-export` shows IDs, existing web titles and extraction counts from an explicitly
supplied export. It requires no database and includes no message-body fields. Use
it when you want to import just one conversation without opening a large JSON file
in an editor or first indexing everything.

```sh
python recap.py list-export examples/web-export.json --format web
python recap.py list-export examples/source-attributed-session.jsonl --format local-codex
```

The examples list `synthetic-chat` with original title `New chat`, and
`synthetic-attributed` without a local title. Both have two extracted messages.
Local session metadata is not searched for guessed title fields. To inspect or
import one identity, use the exact `conversation` value:

```sh
python recap.py inspect examples/web-export.json --format web --conversation synthetic-chat
```

If you choose to import, create a new private scratch directory outside this
repository. Choose another path if it already exists:

```sh
mkdir ../recap-inventory-demo
python recap.py --db ../recap-inventory-demo/archive.sqlite import examples/web-export.json --format web --source demo --conversation synthetic-chat
```

`--source` is your archive grouping, not an authenticated account. The import keeps
all extracted branches for the selected web conversation, or raw local records
for a selected session. It does not clear an existing database. See
[input scope](INPUT_SCOPE.md) for import selection and provenance limits.

## What the inventory means

- One item per distinct conversation ID, including identities with no extracted
  text. IDs are sorted by Unicode code point, without locale or fuzzy matching.
- `original_titles` contains distinct web titles in source order. Missing/null
  web titles appear as an empty string. Local items have an empty list. Titles
  come from the source, not a model or local display-title override.
- `metadata_records` counts web conversation objects or local session metadata
  records for that ID. Repeated local metadata can describe one session.
- `extracted_messages` and `role_counts` count normalized occurrences, not distinct
  database rows. Repeated identical IDs can later be deduplicated by import.
- `selection_supported` means the existing selected-import parser can select the
  ID and has text to import. It does not authorize access, prove completeness,
  resolve database conflicts or guarantee a useful title.
- `AMBIGUOUS_WEB_ID` means multiple web conversation records share the ID.
  They are grouped for inspection and their titles/counts retained, but selected
  import refuses that ambiguity. Recap does not merge or choose one for you.
- `NO_EXTRACTED_TEXT` means the selected-import path has no supported text.
  It can represent empty or media-only content, not proof the conversation is empty.

The top-level `coverage` object retains whole-file extraction counts and warnings.
It is not narrowed to the current page. `selectable_conversations` is likewise a
whole-file count. Nontext, tool or unsupported records retain the existing
format-specific extraction boundaries.

## Pages, privacy and unchanged source bytes

```sh
python recap.py list-export examples/web-export.json --format web --limit 1 --offset 0
python export_inventory.py examples/web-export.json --format web --limit 1 --offset 0
```

The standalone command has equivalent output. Follow `next_offset` until it is
null. Limits range from 1 to 1000 identities. Pagination bounds returned identities,
not bytes, title lengths, metadata records or parsing memory. Each request reads,
validates and parses the entire file, including off-page conversations; malformed
off-page data still fails. No database is opened or created. There is no account
access, directory discovery, upload, source modification or automatic import.
The existing local parser uses a temporary copy of the same bytes for validation.

Each call reads original bytes once, preserves their SHA-256 and returns
`original_sha256`. Repeated pages are separate snapshots. To require the same
bytes on a later page, inspection or import, pass that digest with
`--expected-export-sha256`. See [the source-hash check](INPUT_SCOPE.md#bind-inspection-to-exact-source-bytes).
Without this option, a later call reads the file as it exists then. If the file
changes, inspect it again rather than replacing a mismatch with automatic approval.

**IDs and titles may be private.** Body-free output is not anonymized, redacted or
safe to publish. A source title can itself contain copied message text or secrets.
The `contains_message_text:false` field describes omitted message-body fields,
not a privacy guarantee. JSON escaping preserves Unicode on ASCII terminals;
escaping is not redaction. Keep inventory output outside public repositories.
