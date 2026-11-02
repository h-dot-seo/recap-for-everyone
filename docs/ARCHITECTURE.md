# Recap architecture

## Authority and provenance

Keep four layers distinct:

1. **Source archive:** the immutable bytes an operator is authorized to collect.
2. **Collection ledger:** source identity, byte hash, byte count, collection run and locator.
3. **Derived index:** a rebuildable integrated query database with source-level provenance.
4. **Publication receipt:** a separately verified statement about bytes actually stored remotely.

A successful collection is not evidence of upload; a successful upload is not proof
that every required object is recoverable. A query index never replaces the source.
The initial CLI implements a local ledger/index subset. It does not implement remote
publication receipts, encrypted backups or a full recovery orchestrator.

## Identifiers and version changes

Names and paths are labels. Use source IDs and immutable byte hashes for identity.
Use the tuple `(source_id, conversation_id, message_id)` for messages. Preserve
different sources even if their session IDs collide. A message with the same tuple
and a different role/time/title/text is a conflict requiring explicit reconciliation.
This release rejects that conflict; it does not silently choose a newer record.

## Import transaction

Read the explicitly selected file, validate records, hash original bytes, insert its
artifact record and message rows in one transaction. The FTS insert trigger runs in
that transaction. Reimporting a file inserts no duplicate messages. An artifact
record may still capture a new source-file version whose messages were all seen.
Messages retain their first accepted provenance locator; the small CLI does not
maintain every later duplicate occurrence. The separate parser utilities support
richer occurrence bookkeeping for a future integration.

## Read-only query boundary

Search and statistics open SQLite using `mode=ro` and `PRAGMA query_only=ON`.
FTS queries use bound SQL parameters and quoted terms. A local database is still
private user material: read-only access does not anonymize results.

## Incremental and full organization

An incremental organizer needs a durable verified cutoff and stable IDs/content
fingerprints. A full organizer must enumerate all in-scope items and page through
all results. Neither should infer global completion from a partial inventory.
Title suggestions should derive from actual user requests rather than tool output.
Renaming online conversations is outside this release; an adapter must verify exact
saved titles after any authorized change.

## Recovery acceptance criteria

For a future remote backup integration: use a clean destination; fetch all declared
objects; verify expected hashes, sizes and counts; rebuild the index; run read-only
queries; retain a recovery receipt. Store decryption keys outside backups. Never
mark remote recovery verified from a local Git ref or a push message alone.
