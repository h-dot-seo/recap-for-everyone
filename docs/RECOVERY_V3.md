# Explicit original-export metadata preservation (v3)

Use v3 when a restored archive copy should preserve the `original_exports`
metadata ledger added by explicit imports. This is a supplied declaration and
comparison, not proof of authentic original content, complete collection, or
successful object replay. The default remains v1. Stored v1 and v2 manifests
retain their exact field sets, checks and output contracts.

This synthetic self-check demonstrates the commands; testing the same database
is not evidence that an independently restored backup works. For a real rehearsal,
pass your separately restored copy to `--restored-db`.

```sh
python recap.py --db OUTPUT/v3.sqlite import examples/web-export.json --source synthetic --format web
python recap.py --db OUTPUT/v3.sqlite declare-recovery --manifest-version 3 --output OUTPUT/v3-manifest.json
python recap.py rehearse-recovery OUTPUT/v3-manifest.json --restored-db OUTPUT/v3.sqlite --output OUTPUT/v3-receipt.json
```

## Exact declaration

`recap.recovery-manifest.v3` extends the v2 fields with:

- `original_exports`: null when the table is absent, otherwise `{count,sha256,rows}`.
  An existing empty table has count zero, an empty list and the SHA-256 of empty
  bytes. Absence is not the same as emptiness.
- Each row declares all seven stored fields: `source`, `original_sha256`,
  `original_bytes`, `format`, `selected_conversation`, `normalized_sha256`,
  `extracted_messages`. Whole-file selection remains the stored empty string.
- Rows follow the primary-key order (source, original hash, format, selection,
  normalized hash), using binary text ordering. Physical insertion order and
  SQLite pages/indexes are not evidence. Duplicate identities are rejected.
- The digest covers every field in the declared fixed column order, canonical
  ASCII JSON arrays followed by LF. Row count, digest and rows must agree.
- `original_export_hashes` is the sorted unique hash set derived only from these
  explicit rows. It includes zero-message imports. It does not infer missing
  metadata from legacy provenance or change `sources.original_hashes`.

Same-hash rows may legitimately have different formats or conversation selections.
Their original byte counts must agree. Counts are stored declarations, not an
independent measurement of retained original files. No file path, body copy,
clock, source identity verification, or retention guarantee is added.

## Comparison and objects

The v3 receipt is `recap.recovery-receipt.v3` and records the actual manifest
schema. It retains all v2 checks and adds `original_exports`: every declared row
must match, including missing/unexpected tables or rows. A copied or VACUUMed
archive with equal logical data matches. Checks stay PASS/FAIL; absent on both
sides is described separately from table loss.

If `--objects` is supplied, the explicit v3 hash set adds required original objects
to the existing content-hash scan. There is no inferred legacy union and no change
to normalized artifact optionality. The existing rules treat artifacts with no referenced messages as optional;
v3 adds the explicitly recorded original hash, not a new normalized requirement. Byte
counts are metadata, not a new SIZE_MISMATCH object state. Hash matches do not
establish origin, permission, or completeness.

`rebuild-archive` rejects v3 before reading the replay plan or creating outputs.
This version supports declarations and restored-copy rehearsal, not a new replay
or migration contract. v1/v2 rebuild behavior is unchanged; receipts still report the actual implementation
hash, which changes when implementation bytes change, and the derived receipt hash. No automatic resealing,
existing manifest rewrite, policy change, or full-archive restoration claim occurs.

## Privacy and failure boundaries

Rows include private source labels, hashes and selected conversation IDs. No
message text is intentionally included, but this is not consent for external
sharing. Archive reads do not intentionally write the main DB; SQLite WAL-mode
reads may create WAL/SHM sidecars. Output files remain exclusive, with existing
staging-cleanup and retained-output failure reporting. Keep the supplied original
and restored-copy files separate from outputs. Only synthetic examples are used
here; these commands do not install or connect an external client.
