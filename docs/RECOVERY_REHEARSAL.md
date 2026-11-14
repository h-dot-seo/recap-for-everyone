# Declare before a backup, rehearse after every restore

The architecture's [recovery acceptance criteria](ARCHITECTURE.md#recovery-acceptance-criteria)
ask for a clean destination, every declared object fetched, hashes/sizes/counts
verified, read-only queries run and a recovery receipt retained. Two read-only
commands implement the part of that list the archive itself can answer:

- `declare-recovery` reads the **live** archive once and writes a manifest of what
  a complete restore must contain. Store the manifest with the backup, never
  inside the archive. It is a description, not a backup.
- `rehearse-recovery` opens a **restored copy** read-only, compares it with the
  manifest, optionally hashes a directory of fetched backup objects, and writes a
  receipt with one PASS/FAIL line per check.

Neither command fetches, decrypts, uploads or repairs anything, and neither
touches `import`/`ingest` write paths. Remote backup transport and key handling
stay outside this repository.

## Rehearsal with synthetic data

Replace `OUTPUT` with an existing empty directory **outside** this repository and
run from the repository root with your chosen Python launcher:

```sh
python recap.py --db OUTPUT/archive.sqlite ingest examples/conversations.jsonl --source demo
python recap.py --db OUTPUT/archive.sqlite declare-recovery --output OUTPUT/recovery-manifest.json --declared-at 2026-11-08
python recap.py rehearse-recovery OUTPUT/recovery-manifest.json --restored-db OUTPUT/archive.sqlite --output OUTPUT/recovery-receipt.json --objects examples
python recap.py rehearse-recovery OUTPUT/recovery-manifest.json --restored-db OUTPUT/archive.sqlite --output OUTPUT/recovery-receipt-summary.json --text
```

1. The ingest creates a two-message synthetic archive.
2. The declaration writes `recovery-manifest.json` and prints a summary: one source,
   one artifact, two messages, one conversation, the `messages_sha256` digest, `null`
   for the absent export-occurrence and title-history ledgers, and the manifest's own
   byte count and SHA-256. `--declared-at` is recorded exactly as supplied; no clock
   is read. Without it, `declared_at` is `null`.
3. The rehearsal points at the live archive itself. That is allowed and is only a
   **self-check**: the receipt records the path exactly as supplied, its size and the
   SHA-256 of its bytes, and the boundary says the operator must choose a clean
   restored copy for a real rehearsal. `--objects examples` hashes every regular file
   under the repository's `examples/` directory; the ingested `conversations.jsonl`
   bytes are the one declared normalized artifact, so that hash is reported
   `PRESENT`. The result is `RECOVERY_REHEARSAL_PASSED` with exit status 0.
4. The last line repeats the rehearsal without an object directory and prints the
   ASCII text summary instead of JSON. Every run writes its own new receipt file;
   existing paths are refused rather than overwritten.

As with every `--db` command in this repository, `--db` precedes the subcommand.
`rehearse-recovery` takes the restored copy through `--restored-db` and rejects a
global `--db`, so a rehearsal cannot silently read the wrong file.

## Acceptance criteria mapped to checks

| Criterion | Check(s) | Established / not established |
|---|---|---|
| Use a clean destination | none | Operator responsibility. The receipt records the supplied path, size and SHA-256 and states `clean_destination_verified: "NOT_ESTABLISHED"`. |
| Fetch all declared objects | `declared_objects` (with `--objects DIR`) | Every regular file under `DIR` is hashed. Each declared normalized artifact SHA-256 and each declared original-export hash is reported `PRESENT` or `MISSING`. Required objects must all be present. |
| Verify expected hashes, sizes and counts | `integrity_check`, `expected_tables`, `artifact_rows`, `source_counts`, `messages_digest`, `export_occurrences`, `title_history` | `PRAGMA integrity_check` must return `ok`; the `artifacts` rows (source_id, sha256, bytes, record_count) must equal the declared set exactly; per-source message/conversation counts, the messages digest, the occurrence count with its distinct original hashes, and the title-history count and digest must match or be absent on both sides. |
| Rebuild the index | `fts_rows`, `fts_match_sample` | This command does not rebuild. The separate [normalized-object rebuild rehearsal](REBUILD_REHEARSAL.md) creates a new DB/index first. Here the restored FTS index is checked in place: its indexed row count must equal the message count, and a quoted `MATCH` on the first token of the restored archive's own first message must return that message. |
| Run read-only queries | all checks | The copy is opened with `mode=ro` and `PRAGMA query_only=ON`; the integrity check and the sampled `MATCH` are those queries. |
| Retain a recovery receipt | receipt file | Written with exclusive creation; stdout repeats it plus `receipt_bytes` and `receipt_sha256`. |
| Keys outside backups; never trust a Git ref or push message | none | Stated in the boundary text only; nothing is checked. |

## The manifest

`recovery-manifest.json` has `schema: "recap.recovery-manifest.v1"` and exactly these
fields: `declared_at`, `sources`, `artifacts`, `optional_artifacts`, `messages`,
`conversations`, `messages_sha256`, `export_occurrences`, `title_history`, `fts_rows`,
`digest_semantics`, `scope` and `boundary`.

- `artifacts` repeats the `artifacts` table rows exactly, sorted by source and hash.
- `sources` lists, for every source named by artifacts, messages or occurrences, its
  artifact, message and conversation counts, its `export_occurrences` count and the
  sorted distinct `original_hashes` of its retained original exports (`null` when the
  archive has no occurrence ledger).
- `optional_artifacts` names normalized artifacts whose message rows are all covered
  by declared original-export occurrences, or that no message row references. Export
  adapters derive those normalized bytes in memory during `import`; they never exist
  as files, so the original exports are the objects to keep for them. Artifacts from
  `ingest` of a normalized JSONL file stay required.
- `messages_sha256` is a logical digest: one compact ASCII JSON line per message row
  `[source_id, conversation_id, message_id, role, timestamp, title, text, source_sha256,
  source_line]`, ordered by the identity columns under SQLite BINARY collation. The
  `title_history` digest uses `[source, conversation, previous, title, changed_at]`,
  ordered by those columns; the revision id is excluded. Counts and digests describe
  logical rows, never archive file bytes, page layout or journal state, so a plain file
  copy and a copy made with `VACUUM INTO` both pass. A text dump reloaded through SQL
  is not a supported restore path: it does not recreate the FTS5 shadow tables.
- `fts_rows` counts rows the `messages_fts` index actually holds (its `docsize` shadow
  table). `count(*)` on an external-content FTS5 table reads through to the content
  table and would hide an empty index.

The declaration summary on stdout contains counts, digests and the manifest hash. It
does not list source labels. The manifest file does contain the operator's source
labels and hashes; treat it as private material even though it holds no message text.

## The receipt

`recovery-receipt.json` has `schema: "recap.recovery-receipt.v1"`, `status`
(`RECOVERY_REHEARSAL_PASSED` or `RECOVERY_REHEARSAL_FAILED`), `failed_checks`,
`checks_run`, the manifest's path, size, SHA-256 and `declared_at`, the restored
file's path (as supplied), size and SHA-256, `objects_directory`, the `checks`
list, fixed negative claims (`restored_archive_written: false`,
`clean_destination_verified`, `remote_backup_verified`, `decryption_keys_verified`
and `future_restore_verified` all `NOT_ESTABLISHED`), `scope` and `boundary`.
Each check has `check`, `status` and bounded details such as declared and found
counts, mismatched source labels (at most 20) or the SQLite error text. Message
text is never included; `fts_match_sample` records the sampled `message_pk` and the
token length, not the token.

Exit status is 0 for `RECOVERY_REHEARSAL_PASSED`, 1 for `RECOVERY_REHEARSAL_FAILED`
(the receipt is still written) and 1 with a message on stderr when no receipt can
be produced: an unreadable or oversized manifest, an unknown manifest schema label,
a malformed manifest, a missing or non-regular restored file, a missing or symlinked
`--objects` directory, or an existing output path. Argument errors use the parser's
exit status 2.

## What a FAILED receipt looks like

A copy in which one message row was altered after declaration produces:

```json
{
  "schema": "recap.recovery-receipt.v1",
  "status": "RECOVERY_REHEARSAL_FAILED",
  "failed_checks": ["messages_digest"],
  "checks": [
    {"check": "integrity_check", "status": "PASS", "result": "ok", "message_count": 1, "messages": []},
    {"check": "expected_tables", "status": "PASS", "expected": ["artifacts", "messages", "messages_fts"], "missing": []},
    {"check": "artifact_rows", "status": "PASS", "declared": 1, "found": 1, "missing": 0, "unexpected": 0, "missing_rows": [], "unexpected_rows": []},
    {"check": "source_counts", "status": "PASS", "declared_sources": 1, "found_sources": 1, "declared_messages": 2, "found_messages": 2, "declared_conversations": 1, "missing_sources": [], "undeclared_sources": [], "mismatched": [], "mismatched_count": 0},
    {"check": "messages_digest", "status": "FAIL", "declared": "60b19a58...", "found": "3f0c8d21..."},
    {"check": "export_occurrences", "status": "PASS", "state": "both absent", "declared": null, "found": null},
    {"check": "title_history", "status": "PASS", "state": "both absent", "declared": null, "found": null},
    {"check": "fts_rows", "status": "PASS", "fts_rows": 2, "messages": 2, "counted_from": "messages_fts_docsize", "declared_fts_rows": 2},
    {"check": "fts_match_sample", "status": "PASS", "sampled": true, "sampled_message_pk": 1, "token_length": 3, "matched": true, "detail": "quoted first token of the sampled message", "contains_message_text": false}
  ]
}
```

(Digests abbreviated here; real receipts carry the full 64 hex digits and the
remaining fixed fields.) A file that is not a SQLite database fails `integrity_check`
with `result: "OPEN_ERROR"` and the SQLite error text (`file is not a database`,
`database disk image is malformed`); every remaining archive check is then reported
`FAIL` with the detail `not run`, the receipt is still written, the exit status is 1
and no traceback is printed. An empty file opens as an empty database, passes
`integrity_check` and fails `expected_tables`. A copy whose FTS index was lost fails
`integrity_check` on SQLite 3.44 or later with a row naming the FTS5 table, for
example `malformed inverted index for FTS5 table main.messages_fts` or, on newer
builds, `fts5: corruption found ...`; older bundled SQLite versions report `ok` there
and the loss surfaces as `fts_rows` and `fts_match_sample` failures instead. An index
that was not updated after a direct row change fails `fts_match_sample` or `fts_rows`.

## Limits

- Bounds: the manifest is read up to 64 MiB; `--objects` hashes at most 10,000
  regular files of at most 1 GiB each. Symlinks under the object directory, too many
  files, an oversized file, or an entry that cannot be read (permission denied, a
  locked file, or a file removed while the walk ran) are **refused**: the check fails
  with a reason code (`SYMLINK_REFUSED`, `TOO_MANY_FILES`, `OVERSIZED_FILE`,
  `UNREADABLE_FILE`, `UNREADABLE_DIRECTORY`), lists at most 20 unreadable entries by
  relative path and exception type, and reports objects `NOT_CHECKED` when hashing
  did not run. A file that fails only while being hashed is skipped and the remaining
  files are still hashed; the receipt is written either way, so an unreadable entry
  never aborts the rehearsal. The restored file and the object directory must be
  regular entries, not symlinks. Detail lists are capped at 20 items; the
  token sample scans at most the first 100 messages in `message_pk` order.
- Not declared or compared: the legacy `export_provenance` ledger, review-state
  tables, `local_parser` occurrence tables, and SQLite journal or WAL sidecar files.
  A legacy archive with only `export_provenance` gains the occurrence ledger on its
  next import; until then its adapter-imported artifacts count as required objects.
- The sampled `MATCH` exercises one token of one message, not the whole index. The
  row-count check uses the index's own shadow table, but neither check is a full
  FTS5 integrity audit.
- Exclusive output uses the same same-directory staging and hard-link publication as
  saved title documents, with the same filesystem requirements and limits. It refuses
  files, directories and dangling symlinks already at the destination; it is not a
  defense against a hostile concurrent directory namespace.
- Comparing the live archive with itself is a self-check of the tool and of the
  declaration, not evidence that any backup exists.

## Boundary

A passing rehearsal verifies **this restored copy against the declared manifest**. It
does not prove that the remote backup is complete or current, that decryption keys
are safe, that the destination was clean, or that a future restore will succeed.
The manifest describes the live archive at declaration time and is not a backup or
proof of a remote copy. The tool cannot tell a restored copy from the live archive;
the operator is responsible for that choice. Never mark recovery as verified from a
Git ref, a push message or a passing self-check of the live archive. Manifest and
receipt contain source labels, hashes and paths: keep them private with the backup.

## Read-only SQLite connection protections

Archive reads and metadata-only SQLite artifact inspection use connection-local
`query_only=ON`, `trusted_schema=OFF` and `cell_size_check=ON`. Python/SQLite
builds exposing `SQLITE_DBCONFIG_DEFENSIVE` also enable it. Settings are read back;
unavailable features are reported as `UNAVAILABLE`, not assumed enabled. A
supported protection that remains disabled fails the connection setup. Failed
archive connection setup closes the connection. No persistent DB setting changes.

Recovery rehearsal records these actual states inside the `integrity_check`
check's `sqlite_protections` detail (not a new top-level receipt field). If opening
fails before read-back, values remain `NOT_CHECKED`. A schema view that invokes
non-innocuous functions may now be rejected, even if a plain SQLite connection
would read it. Shipped tables and FTS queries remain supported.

This is defense in depth, **not a sandbox for hostile database files**. There is
no SQL CPU/memory budget or protection against hostile concurrent directory
changes. Write connections for ingest, title history and review state are unchanged
and assume an operator-created archive. These protections do not authenticate
content, validate all semantics or prove recovery completeness.

Relevant existing bounded readers now preflight regular-file type and their existing
byte budget before open, while retaining one bounded read and post-read checks.
Symlinks to regular files retain their prior behavior; this does not change the
separate recovery restored/object symlink policy. See [security](../SECURITY.md).

### Optional title-history lookup index

Successful explicit title writes request `title_history_identity` on
`title_history(source, conversation, id)` within the write transaction. Older
archives remain readable without it, and reads or recovery inspection do not add
it. Index presence or physical layout is not part of the logical title-history
row digest; this auxiliary lookup index changes neither recovery rows nor their
meaning. It does not restore missing title or review history. An existing index
of the same name is retained even if defined differently; no automatic repair or
performance guarantee is implied.

## Optional archived web topology is not declared by v1

`export_nodes` and `export_conversations`, written by explicit web import, are
not declared or compared by recovery manifest v1. Missing or changed topology
therefore does not by itself fail a v1 rehearsal. The original web export bytes
can reproduce these ID-only ledgers through explicit import; without those bytes,
text-only occurrence rows cannot reconstruct missing roots, tips or pointers.
This does not change any existing v1 digest, check or result field. See
[archive branches](ARCHIVE_BRANCH.md).

## Explicit v2 declarations

The v1 contract above remains the default and remains accepted unchanged.
`--manifest-version 2` explicitly declares revision ordering, review decisions,
legacy provenance, full occurrence rows and recorded web topology. See the
[separate v2 guide](RECOVERY_V2.md) for exact added scope, v1 compatibility and
the restored-copy-only boundary. Existing v1 manifests are never relabelled or
automatically re-sealed.
