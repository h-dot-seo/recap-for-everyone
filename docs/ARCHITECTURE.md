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

The normalized-file CLI reads its explicitly selected input once; the byte API
accepts an immutable snapshot. Both validate all normalized records and incoming
identity conflicts before opening SQLite, then use the same archive write path.
Artifact, message, original-export provenance and FTS changes share the data
transaction. Schema initialization remains a separate earlier step: this is not a
promise that every possible failure leaves no new database file or schema.

Web/local export adapters hash the exact original source bytes, normalize their
selected messages in memory and pass the generated JSONL bytes to that same writer.
They do not create temporary source or normalized JSONL files. The normalized
artifact hash retains the prior platform-native text newline behavior; it is not
the original export's hash or a cross-platform canonical identity. Original export
hashes and physical mapping/line locators are retained separately in the coverage
receipt and companion provenance ledgers. SQLite still writes the selected archive
and may use its own journal or internal temporary storage.

Reimporting unchanged identities inserts no duplicate messages. A new artifact may
record a later input whose messages were already accepted. Messages keep their first
accepted normalized artifact hash and line. Export imports additionally retain
original hash/locator/parent occurrences in the additive export_occurrences ledger,
with the legacy export_provenance ledger supported for compatibility. Query views
combine these ledgers without inventing missing historical evidence. No message or
original title is overwritten to reconcile a conflicting export.

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
