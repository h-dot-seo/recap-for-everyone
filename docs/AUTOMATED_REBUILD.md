# Rebuild from a declared object set and explicit replay plan

`rebuild-archive` never opens the original archive. It reads a recovery manifest,
an operator-supplied replay plan and retained objects. It writes a private staging
DB, verifies declared logical rows and FTS checks, closes every connection and
publishes a **new** DB only on success. It does not repair an existing database.

## Synthetic walkthrough

Use an existing empty OUTPUT directory outside the repository. All example
messages and this plan are fictional/synthetic. The first two commands create a
reference archive and declaration; only the last command performs rebuild.

```sh
python recap.py --db OUTPUT/archive.sqlite ingest examples/conversations.jsonl --source demo
python recap.py --db OUTPUT/archive.sqlite declare-recovery --output OUTPUT/manifest.json --declared-at 2026-11-14
python recap.py rebuild-archive OUTPUT/manifest.json --plan examples/rebuild-plan.json --objects examples --new-db OUTPUT/rebuilt.sqlite --output OUTPUT/rebuild-receipt.json --text
```

Expected exit 0 and `REBUILD_REHEARSAL_PASSED`. The original DB is untouched.
`artifact_rows`, `messages_digest`, source counts, original-export occurrences and
FTS checks must match. This checks index row count and a sampled token, not every
possible search query. Compare logical checks, not SQLite file hashes.

## Exact plan contract

UTF-8 strict JSON (optional BOM), at most 64 MiB, exactly two top-level fields:
`schema: "recap.rebuild-plan.v1"` and `steps`, an ordered array of at most 10,000
steps. Empty steps can rebuild an empty declared archive. Each step has exactly:

- `source`: nonempty source text, matching its manifest declaration.
- `kind`: `normalized`, `web`, `local` or `local-codex`.
- `object_sha256`: lowercase 64-character SHA-256. For normalized input it must
  be an artifact hash declared for this source; for adapters it must be an
  original-export hash declared for this source. A hash from another source is
  not permission to use it for this step.
- `label`: original parsing label for local formats, including parser-significant
  relative components; web permits null. Do not substitute a renamed storage
  filename. Normalized input requires null.
- `conversation`: explicit selected conversation or null, with ordinary adapter
  selection rules. Normalized input requires null.
- `newline`: `lf` or `crlf`. Adapters use exactly this serialization, independent
  of the running OS. Normalized input keeps exact bytes and ignores this field,
  but still requires a valid value for the common schema.

The plan order is used exactly, not sorted or inferred. Source, format, label,
selection, order and original serialization are operator knowledge: v1 manifests
cannot recover those parameters. Wrong parameters produce ordinary check failures,
not a guessed platform-cause diagnosis. Duplicate logical identities may retain
first-ingested provenance; reversing steps can change the logical digest.

The object directory uses recovery's 10,000-file / 1 GiB-per-file limits and
symlink refusals. Every regular file is inventoried, including unrelated files.
Duplicate hashes select the first relative path in sorted order. Each selected
object is read once into immutable bytes with a size bound and rehashed before
replay; changed bytes are refused. These are file limits, not a whole-process
memory bound. Local parsing can materialize substantially more memory.

An adapter import extracting zero messages may have no original hash in the v1
manifest, so that original cannot be authorized by this plan. Missing old parser
parameters, optional derived objects and legacy ledgers are not reconstructed by
guessing. Preserve database backups and import parameters where replay matters.

## Publication, failure and privacy

Both output paths must be absent. Existing files, directories, dangling symlinks
and `NEW.sqlite-journal`, `-wal`, `-shm` collisions are refused without deletion.
The receipt cannot alias the DB or those sidecars. The DB is replayed in a private
same-directory staging file. After all checks pass, connections are closed and
unexpected staging sidecars are refused before hard-link publication. No replace,
overwrite or cross-filesystem copying fallback is used. The filesystem must
support same-directory hard links. This is not hostile concurrent namespace
protection or a guarantee that the whole destination directory is clean.

Malformed/unreadable manifests or plans, invalid object-directory arguments and
early destination conflicts fail before staging and may produce no receipt.
Once a valid plan is loaded, unauthorized/missing objects, replay exceptions,
verification mismatches or DB-publication failures produce a FAILED receipt and
exit 1, with no new DB published. Private staging DB/sidecars are removed on either
path. Cleanup failures are reported as `staging_cleanup_complete: false` and
`remaining_staging_files`; inspect and remove only those owned files when safe.
Step error details use a phase, fixed reason and exception type, not parser text.

The DB and receipt are **not one atomic transaction**. If the DB is published but
receipt writing fails, the command fails with an explicit message naming the
preserved DB. It never deletes that published DB to pretend nothing happened.
Do not retry blindly at the same paths. Receipt publication has its own cleanup
status in stdout. Process termination can leave staging files; this command is
not a crash-recovery service. Existing user files are not garbage-collected.

Receipts use ASCII JSON escapes (valid UTF-8), including for surrogate-escaped
filesystem names, and contain counts, hashes, paths, source labels from comparison checks and
implementation hashes, but no message text. Plans include private source labels
and possibly conversation IDs. Keep both private. Hashes are not authentication.
The implementation hash list includes archive, adapter, parser, strict JSON,
source decoding, recovery and rebuild modules for tracing parser changes; it is
not a signed reproducibility or environment attestation.

## What PASSED does not recover

Declared `title_history` is explicitly `NOT_REBUILDABLE_FROM_OBJECTS`, omitted
from expected tables and not counted as PASS. Use `rehearse-recovery` against a
retained database copy to check that ledger. Review-state and other tables not
covered by the v1 declaration are `NOT_DECLARED_NOT_RESTORED`, never silently
credited as recovered. A message rebuild is not a complete archive restoration.

`new_database_created_exclusively: true` is distinct from the unchanged
`clean_destination_verified: NOT_ESTABLISHED`. Remote backup, decryption-key and
future-recovery verification remain NOT_ESTABLISHED. No network, model calls,
real-corpus fixtures, automatic checkpoints or new provenance claims are added.

## V2 replayable-content rebuild

An explicit v2 manifest is also supported by `rebuild-archive`; see
[v2 rebuild](REBUILD_V2.md). Title/review history checks are explicitly excluded,
never counted as PASS. Other provenance/topology digests remain mandatory and
`full_archive_restored` is false. V1 contracts remain unchanged.
