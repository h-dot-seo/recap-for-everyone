# Normalized JSONL input contract

`recap.normalized-message.v1` is a documentation label for the existing `ingest`
record shape, not a required `schema` member or archive-layout guarantee. This
page consolidates current behavior without tightening accepted input. All examples
are synthetic. Keep private messages, identifiers and archives outside this repo.

## Fields and identity

Each nonblank physical line is one JSON object. Required fields are nonempty JSON
strings: `conversation_id`, `message_id`, `role`, `timestamp`, and `text`. `role`
is exactly `user`, `assistant`, `system`, or `tool`. Optional `title` is a string;
omission means `""`. Empty titles are accepted; `null` titles and numeric timestamps
are rejected. Nonempty means at least one character, not nonblank: whitespace-only
text, IDs and timestamps are accepted. Dates are not validated or normalized.

A message identity is `(source, conversation_id, message_id)`. `source` is an
operator-supplied nonblank label, not a field read from the JSON record. Changing
IDs creates different messages rather than updating old ones.

```json
{"conversation_id":"fictional-chat","message_id":"fictional-request","role":"user","timestamp":"supplied fictional time","text":"Synthetic orchard question","title":"Fictional conversation"}
```

Unknown members are **accepted and ignored by storage**, including `schema`,
`source`, `origin_sha256`, and `origin_locator`. They remain only in preserved
input bytes and do not create origin-ledger rows. `NaN` and infinity in unused
members are currently accepted: this is not a full RFC-strict JSON validator.
Duplicate keys and unpaired surrogates are rejected throughout the object, even
in unused nested members. Prefer finite JSON and only documented fields.

## Byte and line rules

UTF-8, an optional initial UTF-8 BOM, and LF/CRLF/CR physical line endings are
accepted. Blank lines are skipped but count toward the physical source line.
Pretty-printed multiline objects are not records. Invalid UTF-8, malformed JSON,
non-object records, invalid required fields, unsupported roles and invalid titles
are rejected before creating a new archive. Decoder nesting failures are reported
cleanly; this contract does not impose a new fixed nesting limit.

Empty and blank-only files are accepted and create zero-record artifacts. That
is not collection-completeness evidence. SHA-256 and byte count cover all original
bytes, including BOM, blank lines, ignored members and line endings. See
[source text compatibility](SOURCE_TEXT_COMPATIBILITY.md),
[input boundaries](INPUT_SCOPE.md#normalized-bytes-and-compatibility) and
[JSON parsing limits](WORKFLOWS.md).

## Repeats, titles and order

Identical repeats are not inserted again, but every nonblank record counts in the
receipt's `records` and artifact `record_count`. A conflicting identity within one
input rejects the file before SQLite opens. Conflicts against an existing archive
roll back the batch instead of overwriting data.

A later identical import retains the first inserted row's `source_sha256` and
`source_line`. It can register a different input artifact without adding an origin
occurrence for that row. Byte-different files can therefore have distinct artifact
hashes but identical stored messages. `title` is per record. Before reviewed local
overrides, conversation inventory uses the first inserted message's title. Message
views use insertion order, not timestamps. Keep conversion order and IDs stable.
See [import conflicts](IMPORT_CONFLICTS.md) and [schema reference](SCHEMA.md).

## Provenance and recovery boundary

Ordinary CLI `ingest` records the **normalized input's** hash and physical line,
not the original vendor export's bytes or locator. Hashes establish byte identity,
not producer authentication. Unknown JSON members populate neither
`export_provenance` nor `export_occurrences`. The `find --export-sha256` body filter
follows those ledgers, so it does not select ordinary ingested rows by normalized
artifact hash. See [export-scoped search](EXPORT_SCOPED_SEARCH.md).

Keep the normalized file. In [recovery declarations](RECOVERY_REHEARSAL.md),
artifacts referenced by messages without complete export-occurrence coverage are
required objects. Empty/unreferenced or fully covered artifacts can be optional;
consult the declaration rather than inferring required status from ingestion alone.
Keep the foreign original and conversion record separately: ordinary ingest does
not declare that original. A
[derived normalized export](EXPORT_NORMALIZED.md) copies text, not origin ledgers,
local display-title history, review state or the source archive.

## Current commands and adapter boundary

The write path remains `recap.py --db DB ingest INPUT --source SOURCE`.
Inspect a converted file without any database:

```text
python recap.py inspect INPUT --format normalized
python recap.py --db EXISTING_DB check-import INPUT --format normalized --source SOURCE
python recap.py --db DB ingest INPUT --source SOURCE --expected-sha256 LOWERCASE_HASH
```

Use `original_sha256` from inspection as `LOWERCASE_HASH`. Inspection and
check-import also accept `--expected-export-sha256 LOWERCASE_HASH`. Each command
reads the file once; the hash covers the exact bytes parsed or ingested, including
BOM and line endings. A malformed/mismatched ingest guard fails before SQLite
access. Omitting the guard preserves existing behavior and receipts. A hash binds
bytes, not provenance, authorization, semantic validity or a conflict-free archive.
The archive can change after inspection; ingest rechecks conflicts under its lock.

`session_workflow.py inspect` and `import_check.py` provide equivalent standalone
entry points. `normalized` is accepted **only** by inspect/check-import, not
`list-export`, `import`, `export-title-plan` or `check-title-plan`. Those still use
`web`, `local`, and `local-codex`. Normalized inspection rejects `--conversation`;
there is no selected-conversation ingest or automatic format detection.

### What inspection means

Malformed records fail with the same structural rules as ingest. Conflicting
repeated identities are instead **reported**, not raised: inspection is not
admission. It succeeds even when `repeated_input.conflicting` is nonzero, while
ingest rejects that input. Counts compare each repeat with its first occurrence.
`check-import` also compares each first incoming identity with the existing archive
source, reports conflicts and exits 1 if any are found; it never creates an archive.
Its sample `record`/`first_record` values remain 1-based nonblank message occurrence
numbers, **not physical line numbers**. See [conflict diagnostics](IMPORT_CONFLICTS.md).

The text-free coverage includes `format`, `original_sha256`, `original_bytes`,
`records`, `unique_identities`, `conversations`, `role_counts`, `repeated_input`,
`contains_message_text: false`, `limitations` and `warnings`. `utf8_bom_present`
appears only when true. Silent-acceptance counts are:

- `records_with_ignored_members`: rows with any unknown member (names/values are
  never returned); this includes unused nonfinite values and supplied origin fields.
- `whitespace_only_text_records`: accepted nonempty text that is all whitespace.
- `records_without_title`: rows whose omitted title becomes the empty string.
- `conversations_with_multiple_titles`: identities with more than one supplied or
  defaulted title across incoming records, including repeats.

An empty input warns that ingest still records an empty artifact. Differing titles,
ignored members, whitespace-only text and conflicting repeats also produce warnings.
Reports omit IDs, titles and message bodies, but hashes and counts can still be
private. No original-vendor provenance is introduced. See the separate
[invented adapter illustration](ADAPTER_GUIDE.md) for a synthetic conversion and
receipt; it is not a real-vendor adapter.

### Python validation helper

`from recap import validate_normalized` exposes the structural pass for immutable
`bytes`, returning `(records, coverage)`. Each record is `(decoded_row,
effective_title, physical_line_number)`. **Records contain private input**, including
ignored fields; only coverage is text-free. Repeated identity conflicts are counted,
not raised. This does not write, open a database, or grant import authorization.
`ingest` and `ingest_bytes` accept the additive keyword-only `expected_sha256`;
existing positional provenance and default receipts remain unchanged.

Unsupported formats require explicit, separately reviewed conversion. This page
does not infer fields, authorize collection, transmit data, select a reuse license
or invite copying repository code; [RIGHTS.md](../RIGHTS.md) remains applicable.
Synthetic characterization tests establish these local behaviors, not real vendor
compatibility, authenticity, completeness, privacy clearance or semantic accuracy.
