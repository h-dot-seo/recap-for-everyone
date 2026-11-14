# Reading the current SQLite archive layout

This describes the layout written by the current release, not a stable database
API or a migration contract. Use outside tools read-only, preferably on a copy.
DB Browser for SQLite, datasette, pandas and DuckDB are possible readers, not
required dependencies. External writes bypass identity conflict and revision
checks and can desynchronize the external-content FTS index.

## Inspect before querying

Create an empty directory named `OUTPUT` outside this repository and replace that
literal placeholder with its path. These commands use only synthetic fixtures:

```sh
python recap.py --db OUTPUT/schema.sqlite ingest examples/conversations.jsonl --source synthetic
python recap.py --db OUTPUT/schema.sqlite describe-schema
```

`describe-schema` is available only through `recap.py`. It opens the archive with
`mode=ro` and `PRAGMA query_only=ON`, starts one explicit `BEGIN` snapshot and never
creates the four lazy tables. A missing path is not created. It rejects a database
without all three core tables. It is an inventory, not a schema/integrity validator.
Existing `stats` output is unchanged.

The JSON schema label is `recap.archive-describe.v1` (the report format, not a
versioned layout promise). `runtime_sqlite_version` names the running SQLite
library, not the file format. `user_version` is read without setting it; recap
currently leaves it at 0. `tables` lists present recognized tables in BINARY name
order, with columns in `cid` order, their declared type, `notnull` flag and primary
key ordinal `pk`. SQLite reports `notnull=false` for an `INTEGER PRIMARY KEY` even
though its integer rowid is assigned. Defaults and SQL definitions are not emitted.
`ledgers_present` distinguishes absent lazy tables from present empty ones.

`rows` is a count, except `messages_fts`, where it is the count of
`messages_fts_docsize` rows or null when that shadow table is absent. The same
value appears as `fts_rows`, with `fts_rows_source`. A virtual-table `COUNT(*)`
would read through to `messages`, so it is deliberately not used as an index count.
A docsize count alone does not establish token/index consistency.

Known FTS5 shadow names are classified separately in `shadow_tables`, not as
archive tables. Other names appear in `unknown_tables` with `recognized: false`;
no unknown table is queried for columns or content. Only the first 20 names in
BINARY order are emitted, with total and omitted counts. `indexes` and `triggers`
likewise list at most 20 names each, with counts and omitted counts. These are name
classifications, not proof that objects have expected definitions. No clock is read.
The encoded report is capped at 16 MiB before stdout emission.

PRIVATE METADATA: counts reveal archive size. Object names, column names and
declared types are echoed and may themselves contain private text. Normal message
bodies, titles, source labels and paths are not emitted. `contains_message_text:
false` describes the inventory's intended data fields, not a guarantee that an
arbitrary hostile schema name contains no text. No archive mutation, network,
model call, authentication, completeness or recovery claim is made.

## Tables and columns

The lists below are checked against a fully populated synthetic archive. They
list every column in order; a changed layout must update this reference and its
tests. SQL types/nullable flags come from `describe-schema` rather than this prose.

### artifacts

Created by the first successful normalized `ingest` or export `import`.

- `source_id`: operator-supplied source label.
- `sha256`: SHA-256 of original normalized JSONL bytes, not necessarily vendor bytes.
- `bytes`: normalized input byte count.
- `record_count`: input record count, including identical repeated records.

Composite primary key: `(source_id, sha256)`. All columns are NOT NULL.

### messages

Created with `artifacts`.

- `message_pk`: local integer rowid surrogate; archive insertion order.
- `source_id`: operator-supplied source label.
- `conversation_id`: supplied conversation identifier.
- `message_id`: supplied message identifier.
- `role`: imported user, assistant, system or tool role.
- `timestamp`: text retained as supplied, not a validated date or sort key.
- `title`: original supplied title, possibly the empty string.
- `text`: message body.
- `source_sha256`: normalized artifact hash for the first retained row.
- `source_line`: physical normalized input line for the first retained row.

Identity is the unique tuple `(source_id, conversation_id, message_id)`, not
`message_pk`. All columns except the rowid declaration are explicitly NOT NULL.
The foreign key `(source_id, source_sha256)` refers to `artifacts`. Later identical
imports do not replace the first retained normalized hash/line.

### messages_fts

Created with `messages` as an FTS5 external-content index.

- `text`: indexed message body, with `content='messages'` and
  `content_rowid='message_pk'`.

`messages_ai` is the AFTER INSERT trigger only. There are no automatic UPDATE or
DELETE synchronization triggers. Internal FTS5 tables `messages_fts_config`,
`messages_fts_data`, `messages_fts_docsize`, `messages_fts_idx` are implementation
storage, not independent provenance ledgers. A text-dump reload does not by itself
recreate a verified FTS shadow index; it is not a supported recovery procedure.

### export_provenance

Created on the first export `import`, not normalized `ingest`.

- `source`: source label matching `messages.source_id`.
- `conversation`: identifier matching `messages.conversation_id`.
- `message`: identifier matching `messages.message_id`.
- `original_hash`: SHA-256 of original vendor export bytes.
- `locator`: location in that original export.
- `parent`: supplied parent identifier; NULL for local exports.

All columns are nullable. The legacy primary key is
`(source, conversation, message, original_hash)` and can retain only the first
locator for an identity/export. Retain this legacy table; it is not the complete
occurrence ledger.

### export_occurrences

Created on the first export `import`, with additive backfill from legacy rows.

- `source`: source label matching `messages.source_id`.
- `conversation`: identifier matching `messages.conversation_id`.
- `message`: identifier matching `messages.message_id`.
- `original_hash`: SHA-256 of original vendor export bytes.
- `locator`: location in that original export.
- `parent`: supplied parent identifier; NULL for local exports.

All columns are nullable. Primary key:
`(source, conversation, message, original_hash, locator)`. This preserves repeated
locations, not just one location per message/export. Complete occurrence reads
combine this ledger with legacy rows that have no NULL-safe equal row across all
six fields. `legacy_only_provenance_rows` counts those legacy-only rows, or every
legacy row if the occurrence table is absent, or 0 if both are absent. It does not
assert that the original export was complete or that its hash authenticates it.

### title_history

Created on first `title --set` or `apply-title`.

An explicit title write also requests the non-unique `title_history_identity`
index on `(source, conversation, id)` inside the same transaction as history-table
creation and the new history row. Reads do not create it. Existing archives gain
it only on their next successful explicitly requested title write, not by opening
or inspecting the database. Stale guards or failed writes do not install it.
There is no new table, row format, user_version change or automatic maintenance.
`IF NOT EXISTS` preserves an existing index with that name, including one with a
different definition or table; it is never dropped or silently repaired. Query
plan benefits are conditional on the intended index actually being created.
The index is not a timing guarantee and does not change title revision semantics.

- `id`: local integer primary key and title revision order.
- `source`: source label.
- `conversation`: conversation identifier.
- `previous`: previous effective display title.
- `title`: explicitly recorded new local display title.
- `changed_at`: recorded timestamp with CURRENT_TIMESTAMP default.

All non-rowid columns are nullable. Resolve the display title using the largest
`id` for `(source, conversation)`, never `changed_at`; otherwise use the `title`
of the smallest `message_pk` row for that identity. This is insertion order, not
timestamp order, and an empty title remains an empty title. NULL title values from
outside writers are not valid recap title changes; the example faithfully retains
a present latest row's value rather than treating NULL as a missing row.

### title_review_history

Created on first `review-state --set`.

- `id`: local integer primary key and decision revision order.
- `source`: source label (NOT NULL).
- `conversation`: conversation identifier (NOT NULL).
- `state`: recorded open, skipped or deferred event (NOT NULL).
- `content_sha256`: content fingerprint supplied with the decision lease (NOT NULL).
- `title_revision`: title revision supplied with that lease (NOT NULL).
- `decided_at`: timestamp with CURRENT_TIMESTAMP default (nullable).

Index `title_review_history_identity` covers `(source, conversation, id)`.
The recorded event is not necessarily the effective state: that requires the
Python content fingerprint and a matching title revision. Use `review-state` or
`review-titles` rather than interpreting this table as a current-state materialization.

## Read-only SQL examples

These queries return private titles, identifiers and provenance. Unlike the
metadata command, their results must be handled as private archive data.
Join on `(source_id, conversation_id, message_id)`, never the local `message_pk`
when combining message identities and occurrence ledgers. Inspect lazy-table
presence with `describe-schema` first; a missing table otherwise raises
`no such table`. SQL below is executed in tests through `archive.readonly()`.

### Current local display titles

Requires `title_history`. Returns one row per conversation in BINARY identity order.

```sql
SELECT m.source_id, m.conversation_id,
       CASE WHEN h.id IS NOT NULL THEN h.title ELSE m.title END AS display_title
FROM messages m
LEFT JOIN title_history h ON h.id = (
    SELECT MAX(t.id) FROM title_history t
    WHERE t.source = m.source_id AND t.conversation = m.conversation_id)
WHERE m.message_pk = (
    SELECT MIN(first.message_pk) FROM messages first
    WHERE first.source_id = m.source_id AND first.conversation_id = m.conversation_id)
ORDER BY m.source_id COLLATE BINARY, m.conversation_id COLLATE BINARY;
```

### Messages with every recorded occurrence

Requires both `export_occurrences` and `export_provenance`. Includes legacy-only
rows via NULL-safe comparison. A message with no export provenance remains with
NULL occurrence fields because normalized ingestion alone has no vendor ledger.

```sql
WITH occurrences AS (
    SELECT source, conversation, message, original_hash, locator, parent
    FROM export_occurrences
    UNION ALL
    SELECT p.source, p.conversation, p.message, p.original_hash, p.locator, p.parent
    FROM export_provenance p
    WHERE NOT EXISTS (
        SELECT 1 FROM export_occurrences o
        WHERE o.source IS p.source AND o.conversation IS p.conversation
          AND o.message IS p.message AND o.original_hash IS p.original_hash
          AND o.locator IS p.locator AND o.parent IS p.parent)
)
SELECT m.source_id, m.conversation_id, m.message_id,
       o.original_hash, o.locator, o.parent
FROM messages m
LEFT JOIN occurrences o ON o.source = m.source_id
    AND o.conversation = m.conversation_id AND o.message = m.message_id
ORDER BY m.source_id COLLATE BINARY, m.conversation_id COLLATE BINARY,
         m.message_id COLLATE BINARY, o.original_hash COLLATE BINARY,
         o.locator COLLATE BINARY, o.parent COLLATE BINARY;
```

### Recorded title history

Requires `title_history`. This lists events, not a timestamp-sorted reconstruction.

```sql
SELECT source, conversation, id, previous, title, changed_at
FROM title_history
ORDER BY source COLLATE BINARY, conversation COLLATE BINARY, id;
```

## Open maintainer decision gate

No schema stability promise is adopted here. A future owner decision could name
read-stable columns, require additive-change announcements in validation history,
and choose a migration/layout mechanism such as `PRAGMA user_version`. Those
choices, versioning rules and compatibility guarantees remain open. This guide's
drift tests document current code; they do not turn it into a permanent contract.

## Optional web topology ledgers

Explicit web import retains `export_nodes` (source, conversation, original hash,
node ID, parent ID and deterministic mapping ordinal) and `export_conversations`
(source, conversation, original hash, supplied current-node ID/state and node
count). These additive rows share the existing import transaction, not a new
schema epoch or automatic migration. They contain no title or message text, but
IDs are private metadata. A selected import stores only its selected conversation.
See [archive branches](ARCHIVE_BRANCH.md) for path selection and recovery limits.

### export_conversations

Created only by explicit web import, in its data transaction.

- `source`: supplied source label.
- `conversation`: supplied conversation identifier.
- `original_hash`: exact original web-export SHA-256.
- `current_node`: valid supplied mapping-node ID, otherwise NULL.
- `current_node_state`: valid, absent, invalid or ambiguous; never an inferred leaf.
- `mapping_nodes`: recorded mapping-node count, zero for ambiguous duplicate records.

Primary key: `(source, conversation, original_hash)`. Duplicate conversation
records in the same export remain importable but cannot supply an unambiguous
branch. This preserves import admission rather than choosing the first record.

### export_nodes

Created only by explicit web import, in its data transaction.

- `source`: supplied source label.
- `conversation`: supplied conversation identifier.
- `original_hash`: exact original web-export SHA-256.
- `node`: mapping-node identifier, including nodes without extracted text.
- `parent`: supplied parent identifier or NULL for a root.
- `ordinal`: zero-based original mapping order, not SQLite rowid or chronology.
- `has_text`: 0 or 1, whether normalization extracted supported nonblank text for this node.

Primary key: `(source, conversation, original_hash, node)`. Ordinal and text
membership are deterministic parsing metadata, not new message content. Readers
validate graph structure, counts and selected-export occurrence agreement rather
than inferring a missing path. These tables have no NOT NULL constraints; malformed
or incomplete values are not accepted as branch evidence. Recovery v1 does not
compare either table. There is no automatic repair, DROP or migration.

## Explicit logical ledger comparison

[Recovery v2](RECOVERY_V2.md) optionally binds history revision IDs and all
provenance/topology row columns. This adds no SQLite tables, migration, index,
archive stamp or schema-stability promise. Default recovery v1 stays unchanged.

### original_exports

Created only by explicit web/local/local-codex import, in its existing transaction.

- `source`: supplied source label (NOT NULL).
- `original_sha256`: exact original input byte hash (NOT NULL).
- `original_bytes`: original byte count, not original content (NOT NULL).
- `format`: explicit web, local or local-codex format (NOT NULL).
- `selected_conversation`: exact selected ID, or empty string for whole input (NOT NULL).
- `normalized_sha256`: actual serialized normalized artifact hash (NOT NULL).
- `extracted_messages`: actual normalized input row count, including repeated extracted rows (NOT NULL).

Primary key: `(source, original_sha256, format, selected_conversation, normalized_sha256)`.
No clock, path or original message body is stored. Read-only access never creates
or backfills it; same-key metadata conflicts fail without overwrite. Recovery v1
and v2 do not declare or compare it. See [archive ledger](ARCHIVE_LEDGER.md).

`original_exports` is recognized in the present-table listing only; existing
`ledgers_present` flags remain unchanged. Presence does not imply recovery v1/v2
coverage.
