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

## Find a known title or session ID before importing

If you remember part of a web title or session ID, use `--contains` to narrow the
metadata inventory instead of scanning every page or importing everything first:

```sh
python recap.py list-export examples/web-export.json --format web --contains "New chat" --limit 1
python recap.py list-export examples/source-attributed-session.jsonl --format local-codex --contains attributed
python export_inventory.py examples/web-export.json --format web --contains "new CHAT" --canonical-unicode
```

The web example matches `synthetic-chat`; the local example matches
`synthetic-attributed`. Use the returned **exact conversation ID**, not the title
or filter text, for a later selected import. A common title can match many IDs.
Filtering does not select or import a conversation automatically and is not
permission to read data. Keep the same original-file hash for the later command.

`--contains` is **one literal substring** matched independently within the
conversation ID or any existing web title. Matching ignores case using Unicode
case folding. It does not split words, join fields, interpret regex/wildcards/SQL,
rank relevance or search message bodies. For example, `orchard plan` requires that
whole substring within one ID or title, not one word in each field. Local formats
match IDs only: metadata fields resembling titles, working directories and user
messages are not searched or turned into guessed titles.

The filter must be non-whitespace text of at most 256 Unicode code points, with
no surrogate code points. Meaningful leading/trailing spaces are retained, not
trimmed for matching. Invalid filter arguments fail before reading the input.
Use `--contains=VALUE` if a literal value begins with a hyphen. Both CLIs support
the same flags. Python callers use the keyword-only `contains=` and
`canonical_unicode=` options after the existing `list_export` arguments.

By default, Unicode normalization is not performed. Add `--canonical-unicode`
when composed/decomposed spelling should match, for example NFC and decomposed
Korean or accented text. It requires `--contains` or the explicit message-text
filter below, and uses the existing
`NFC(NFD(text).casefold())` search-copy rule. The receipt records the normalization
and runtime Unicode version. It is not accent removal, compatibility-width folding,
transliteration or fuzzy matching. Original IDs, titles, source bytes and hashes
are returned unchanged; canonically matching identities remain distinct records.

### Filtered counts, pages and validation

The optional `filter` object reports the exact `contains` value, matching fields,
mode, `matched_conversations` and `matched_selectable_conversations`. These are
totals across all matches, not only the returned page. Existing top-level
`total_conversations`, `selectable_conversations`, `coverage`, byte count and hash
still describe the **whole file**. Without the filter, output shape and behavior
are unchanged. A zero-match page has no conversations and a null `next_offset`;
it does not prove the source lacks relevant message content.

Grouping and validation happen before filtering. If only a repeated web ID's
second title matches, the returned item still includes all its original titles,
counts and `AMBIGUOUS_WEB_ID` blocker. Empty/media-only matches retain
`NO_EXTRACTED_TEXT`. Filtering never makes an ambiguous or unsupported selected
import safe. Malformed unmatched or off-page content still rejects the whole file,
even if the requested substring would match nothing.

`limit`, `offset` and `next_offset` now apply to the matching identities, in the
same Unicode-code-point ID order. Use the same filter and canonical mode on every
page, and pass `--expected-export-sha256` from the first page to require the same
source bytes. Changing a filter means starting at offset zero, not continuing the
previous offset. There is no opaque cursor or automatic cross-call filter lease.

This reduces returned metadata and the need to manually scan pages, **not** the
source-reading scope. Every call still reads and validates the full file and
extracts supported text internally before building the body-free inventory.
Filtering is not a streaming, memory-bound, redaction or completeness guarantee.
The echoed query, IDs and titles may be private, even when no body field appears.

## Find a conversation by remembered message text

Local session IDs may be opaque and web titles may all say `New chat`. If you
remember a phrase from a message instead, explicitly use `--text-contains`:

```sh
python recap.py list-export examples/web-export.json --format web --text-contains "orchard experiment"
python recap.py list-export examples/source-attributed-session.jsonl --format local-codex --text-contains "lunar calendar"
python export_inventory.py examples/source-attributed-session.jsonl --format local-codex --text-contains "LUNAR CALENDAR" --canonical-unicode
```

This returns the exact conversation ID, existing titles and counts, **not message
bodies, excerpts, message IDs or source locators**. Choose either `--contains`
(metadata) or `--text-contains` (extracted message text), not both. Existing
metadata searches do not start searching bodies implicitly. Python callers add
keyword-only `text_contains=...`; the existing positional arguments stay unchanged.
Both filters use the same nonblank, valid-Unicode, 256-code-point query limit,
literal case folding and optional canonical-Unicode matching. Leading/trailing
query whitespace is meaningful. Use `--text-contains=VALUE` for a leading hyphen.

A phrase must occur inside **one normalized extracted message**. Separate messages,
conversation IDs, titles, metadata and sessions are never joined for matching.
Content parts joined by the existing extractor can match across their inserted
newline. Extraction still follows the chosen format: `local` uses legacy dictionary
text extraction and whitespace cleanup, `local-codex` preserves supported typed
input/output text, and web text uses its supported parts/code/output shapes. Records
or parts omitted by that parser are not searched or inferred. Legacy `local` can
extract a dictionary's text regardless of its content type; choose `local-codex`
when you need the narrower typed-content extraction contract.

All extracted roles are searched: user/assistant for these local adapters and also
system/tool for web. All web branches and raw local messages remain in scope,
including rolled-back local turns and harness text inside an extracted message.
This does not reconstruct the visible branch, retained history or human-authored
parts. A match is not proof of user intent, completeness or suitable title evidence.
For narrower title evidence, use the separate verified branch/replay/attribution
workflows after deliberate import.

In text mode only, each returned identity adds `matched_messages` and
`matched_role_counts`. Each matching normalized message occurrence counts once,
even if the phrase repeats within it. Repeated source records can count separately,
including records that import later deduplicates or rejects. Existing
`extracted_messages`, `role_counts`, original titles and blockers still describe
the entire identity. Duplicate web IDs remain `AMBIGUOUS_WEB_ID` even if only one
record's body matches; filtering never chooses that record or repairs the identity.

The `filter` summary reports `text_contains`, the matching scope, global
`matched_messages`, `matched_conversations` and `matched_selectable_conversations`.
These counts cover all matches, not just the page. Existing top-level counts,
coverage and original hash remain whole-file values. Empty/media-only identities
cannot match without extracted text; zero matches do not prove the source has no
relevant media or omitted content. Full-file validation still rejects malformed
unmatched content, even for zero results or an offset beyond the last match.

Pages use matching-ID offsets in the same exact Unicode-code-point order. Keep the
same phrase and canonical mode and use the first response's original hash on later
pages. Restart at offset zero when changing the query. This is read-only full-file
parsing, not a streaming search, private-text minimization, automatic selection,
import or model call. No database is accessed, even if the unified CLI is given
`--db`.

**The echoed query may itself reveal message text.** IDs, source titles and match
counts can also be sensitive. `contains_message_text:false` only means extracted
message-body fields are omitted; it is not redaction or permission to share output.

### From a phrase to a reviewed title

Use a new private directory outside the repository. Do not overwrite an existing
scratch directory or saved document. These exact commands use only shipped
invented content:

```sh
mkdir ../recap-text-search-demo
python recap.py list-export examples/title-focus-local.jsonl --format local-codex --text-contains "orchard watering"
python recap.py --db ../recap-text-search-demo/archive.sqlite import examples/title-focus-local.jsonl --format local-codex --source local-search --conversation synthetic-local-focus --expected-export-sha256 4bf9f45d8f22b79b4469002d62a4b3ef82a60fdceb340b0c2bfdd036f678209b
python recap.py --db ../recap-text-search-demo/archive.sqlite show --source local-search --conversation synthetic-local-focus --message focus-user
python recap.py --db ../recap-text-search-demo/archive.sqlite suggest-replay-title examples/title-focus-local.jsonl --source local-search --conversation synthetic-local-focus --message focus-user --output ../recap-text-search-demo/proposal.json
python recap.py --db ../recap-text-search-demo/archive.sqlite preview-title ../recap-text-search-demo/proposal.json --with-evidence --output ../recap-text-search-demo/reviewed.json
```

The inventory identifies `synthetic-local-focus`, with one matching user message
among six raw messages. The fixed digest above belongs only to this unchanged
example; use your own inventory's `original_sha256` for your file. Selected import
keeps the **entire conversation**, not just matching messages. Inspect `focus-user`
and the actual saved proposal/preview, rather than treating a search match or a
`SAVED` receipt as approval. The verified replay excludes the rolled-back turn;
the proposed title is `Compare synthetic orchard watering schedules`, with the
same 80-code-point excerpt cap and separate title revision/content checks.

Only after reviewing the selected identity, evidence and proposed wording:

```sh
python recap.py --db ../recap-text-search-demo/archive.sqlite apply-title ../recap-text-search-demo/reviewed.json
python recap.py --db ../recap-text-search-demo/archive.sqlite find "orchard watering" --source local-search
```

The local title changes only on explicit apply. Original messages, export bytes
and provenance remain intact, and nothing is renamed in the live source app.

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
The local parser validates the same immutable source bytes directly in memory,
without a temporary source copy.

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
