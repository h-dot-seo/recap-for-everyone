# Two-pass normalized file ingest

`recap.py ingest` and `ingest(..., provenance=None)` process the explicitly chosen
file twice through one open binary file object. They no longer retain the whole
input bytes and all decoded rows. `ingest_bytes`, web/local adapters, recovery
replay and calls supplying `provenance` keep their existing immutable byte paths.
No private input staging copy, temporary export or new CLI option is introduced.

The first pass hashes every raw byte, decodes UTF-8 (one leading BOM permitted),
retains physical LF/CRLF/CR line numbers, validates every record, and rejects
conflicting repeated identities before SQLite is opened. Its identity map retains
(conversation_id, message_id) plus SHA-256 of the canonical JSON tuple
(role, timestamp, effective title, text). Missing title means empty text; ignored
members do not change the existing identity equality. This digest is internal
bookkeeping, not source authenticity or a guarantee against hash collisions.

The second pass parses rows into the existing write transaction. Its raw digest,
byte count, record count and BOM state must match before commit or success receipt.
Detected successful-parse mismatch raises SourceChanged; a parsing, I/O or SQLite
failure aborts with that error and rolls back transactional rows. Existing artifact,
message and FTS rows remain logically unchanged after a failed transaction.

Schema initialization still occurs before BEGIN IMMEDIATE, as before. A second
pass failure on a new destination can leave an empty initialized database/schema.
This is not complete filesystem atomicity or a promise that every failure leaves
no file. First-pass bad input does not open SQLite or create a new database.
Connections and the source handle close on both success and failure. No automatic
repair, deletion, retry or permission to write a different archive is implied.

Error ordering remains file open/read, expected-hash syntax, expected-hash mismatch,
UTF-8 decoding, then the first JSON/row/incoming identity error. A later invalid
UTF-8 sequence therefore takes precedence over an earlier row error. The optional
expected hash does not skip validation. Normal receipts, exact artifact bytes and
hash, physical source_line, duplicate count and first stored provenance remain.

## What two passes do not establish

Equal observed hashes are not an immutable file snapshot or a defense against a
hostile concurrent filesystem. A writer can change and restore bytes between
passes without detection. Use stable operator-controlled inputs. The old read-once
snapshot test is intentionally replaced for this file path, not for the retained
byte/adapter paths. Parsing and writing still require memory for a complete line,
the largest decoded record, and one identity/digest per distinct incoming message.
There is no total process memory bound. The later source admission increment
adds a 2 GiB inclusive input ceiling, checked by stat and cumulative raw bytes
in both passes; see SOURCE_FILE_ADMISSION.md. Existing smaller limits are not raised.

## Synthetic allocation observation

Three fresh subprocesses per version used identical 10,000-row synthetic JSONL
(1,000 conversations; 1,024 repeated `x` characters per message), 11,507,790 input
bytes. tracemalloc started after imports, fixture writing and garbage collection;
each execution created a fresh DB. Python heap peaks in bytes:

- Previous: 44,374,772 / 44,374,672 / 44,374,728 (median 44,374,728).
- Current: 2,570,741 / 2,570,633 / 2,564,035 (median 2,570,633).

This is an environment-specific allocation observation, not total RSS, SQLite
native allocation, runtime speed or a large-input guarantee. No private archive
was used. SCALING.md also corrects stale pre-streaming ZIP descriptions left after
the earlier ZIP change; that correction does not introduce another ZIP change.

## Synthetic example

Create an empty OUTPUT directory outside the checkout and substitute its path:

```sh
python recap.py --db OUTPUT/streamed.sqlite ingest examples/conversations.jsonl --source synthetic
python recap.py --db OUTPUT/streamed.sqlite search orchard
```
