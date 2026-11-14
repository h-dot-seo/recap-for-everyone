# Inspect recorded original-export metadata

`recap.py --db DB ledger` reads one global page of import bookkeeping. Explicit
web, local and local-codex imports now retain the original byte hash, **byte count**,
format, explicit conversation selection, normalized artifact hash and extracted
row count. No original body, path, filename, clock or collection judgement is added.

## Synthetic walkthrough

Use a fresh OUTPUT directory outside the repository. All input content is synthetic.

```sh
python recap.py --db OUTPUT/ledger.sqlite import examples/web-export.json --source demo --format web
python recap.py --db OUTPUT/ledger.sqlite ledger --source demo --limit 10
python recap.py --db OUTPUT/ledger.sqlite ledger --source demo --limit 1 --text
```

The JSON schema is `recap.archive-ledger.v1`. `entries` can contain:

- `original_export`: the seven stored fields plus `kind`. Whole-file selection is
  null in JSON, stored as an empty string. A nonempty selection ID remains exact,
  including whitespace if it is the actual supplied conversation identifier.
- `artifact`: source, normalized sha256, bytes and record_count with origin_status
  recorded or unledgered. A normalized artifact can have multiple original
  imports, so no single format, original byte count or selection is inferred.
- `unledgered_original_hash`: a distinct source/hash found in either occurrence or
  legacy provenance but lacking an original-export metadata row. Unknown original
  byte count, format and selection are null, not guessed.

`--source` is an exact optional source filter. `--limit` is 1..1000, default 50;
`--offset` is 0..9223372036854775807. All kinds share one deterministic page and
`total/returned/next_offset`. Follow next_offset until null, not a separate page
per entry kind. The query uses SQLite sorting and pagination; returned JSON has a
16 MiB limit. This is not a bound on query work or process memory, and very large
metadata values may require a smaller page. Each call gets a separate snapshot.

## Write and legacy boundaries

Only explicit export import supplies origin metadata, from its already-read
coverage snapshot. The writer computes normalized hash and extracted count from
its actual serialized rows. The table is created inside the existing import
transaction. Zero-message imports get a row even when several originals normalize
to the same empty artifact. Format is in the primary key, so local/local-codex
imports are not conflated merely because their normalized bytes match.

The primary key is `(source,original_sha256,format,selected_conversation,normalized_sha256)`.
Repeated identical imports are additive and idempotent. Conflicting stored byte
count or extracted count for the same key causes failure, not silent overwrite.
A failure rolls back the import transaction. Required column names, declared
types, NOT NULL and primary-key positions are checked; compatible physical column
reordering is supported through named INSERT fields. Incompatible existing table
layouts (including extra generated columns) are not dropped or repaired. Extra
constraints and triggers are not removed: an ignored or changed insert must still
leave the exact primary-key row with matching byte and message counts, otherwise
the transaction fails. CHECK failures also roll back rather than being reported
as successful imports. Initial core-schema creation retains its existing
separate failure boundary.

Plain normalized `ingest` is unchanged and adds no original-export row. Reading
an old archive never creates or backfills the table. Reimporting explicitly known
original bytes can record their metadata, but missing history is never invented.
Unledgered means no matching metadata record, **not** proof that an import never
occurred. This is not a list of files currently retained on disk.

## Privacy and recovery scope

Output is PRIVATE METADATA: source labels, hashes and selected conversation IDs
may identify private work. `contains_message_text:false` means this tool does not
intentionally fetch message bodies; it is not permission to transmit the output.
`retention_verified` and `import_completeness` remain NOT_ESTABLISHED. Read-only
SQLite access may create WAL/SHM sidecars; main archive bytes are not intentionally
changed. No network or automatic external transmission occurs.

Recovery manifests v1 and v2 do **not** declare or compare `original_exports`.
This new ledger does not change their original_hashes, object authorization,
checks or rebuild behavior. In particular, preserving a zero-message original
hash here does not authorize it in an old recovery declaration. A future explicitly
versioned contract would need to bind and use this metadata; do not relabel or
re-seal existing manifests. No source authenticity, rights or complete recovery
is established by the new rows.
