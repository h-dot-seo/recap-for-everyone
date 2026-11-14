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
selected messages in memory. They serialize the same JSONL bytes for artifact
identity but validate the existing rows without decoding that JSONL a second time,
then pass the checked records to the same writer. Direct normalized ingestion
still strict-parses its supplied bytes.
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

Local display-title changes are one deliberate write path. `title --set`,
reviewed proposal application and explicit restores append to the title history
under revision checks. They never rewrite archived message bytes, source hashes or
the original export title, and they never rename a conversation online.

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

`declare-recovery` and `rehearse-recovery` (`recaplib/recovery.py`) implement the archive-side
part of this list. The declaration records the live archive's artifact rows, counts,
logical digests, ledgers and FTS row count in a manifest stored with the backup. The
rehearsal opens a restored copy read-only and checks integrity, expected tables,
exact artifact rows, counts, digests, ledgers and the FTS index in place, optionally
confirms that every declared object hash is present in a fetched-object directory,
and writes a receipt with `RECOVERY_REHEARSAL_PASSED` or `RECOVERY_REHEARSAL_FAILED`.
The clean destination remains the operator's responsibility and is recorded as not
established; this command verifies the index in place. The separate
[normalized-object rebuild rehearsal](REBUILD_REHEARSAL.md) exercises a new database
and index via retained JSONL on supported platforms. Adapter replay additionally
requires matching format, selection, label, order and platform newline behavior;
the automated rebuild command requires an operator-supplied replay plan;
the manifest still does not contain a complete plan. Remote fetch, decryption, key custody
and backup scheduling stay outside the repository. See
[the recovery rehearsal guide](RECOVERY_REHEARSAL.md).

## Lower-level title API input boundary

`session_workflow.titles` validates its identities and optional revision before
opening or resolving the database. The source must be non-whitespace Unicode text;
the conversation must be a nonempty Unicode string. Neither is trimmed, normalized
or case-folded. Text IDs such as `"1"`, `"01"` and `"1.0"` stay distinct. A numeric or
boolean Python argument is rejected instead of relying on SQLite affinity to match
a text key. Surrogate code points are rejected rather than sent to SQLite.

A supplied `expected_revision` must have exact Python type `int` and be nonnegative.
`False`, `True`, `0.0` and `1.0` are not revision tokens even when Python equality
would match a real revision. This deliberately rejects formerly accepted malformed
direct calls. On a write, the integer still has to match the selected conversation's
latest `title_history.id`, allocated from the global history table, under the existing
immediate transaction. It is not the table's global maximum or a per-conversation
counter. No revision is guessed or changed after a stale error.

For compatibility, `expected_revision=None` still means no revision guard in this
lower-level API. An informational read still ignores a valid supplied revision; it
is not a compare-and-swap read. The CLI continues to require an explicit revision
for `title --set`, and the proposal workflow requires a checked preview with its
content fingerprint and integer revision. Prefer that workflow for integrations
and explicit human review. Type checks are not authentication, proof of approval,
semantic validation or a remote title permission. No old ledger events are scanned,
repaired or removed by this change.

## Code layout

The repository root holds the entry points: `recap.py` (the unified CLI), the
standalone scripts (thin compatibility entry points that import `main` from the module
of the same name in `recaplib/`), `runtime_check.py`, `verify_manifest.py`, `build_manifest.py` and
`audit_publication.py`. The implementation is the `recaplib/` package;
`recaplib/archive.py` holds the schema, the import transaction, the read-only
connection and the FTS search described above and is re-exported by `recap.py`. The
synthetic test suite is the `tests/` package. The layout changes no documented command
and is a reading aid, not a stability promise for importing `recaplib` from other code.

## Runtime-dependent JSON depth

Strict JSON decoding remains the shared input boundary. Local occurrence hashing
also catches encoder `RecursionError`, because some interpreters decode deeper
objects than they can serialize. The error retains only the fixed nesting label,
source path and physical line, before archive creation; exception notes and JSON
keys are not exposed. Synthetic tests probe bounded depths without changing the
process recursion limit. See [input scope](INPUT_SCOPE.md#testing-interpreter-dependent-nesting).

The render layer consumes the existing single-snapshot conversation object, without SQL changes. It hashes that exact view as `view_sha256`, not a whole-content fingerprint, and emits HTML or Markdown through an incremental 16 MiB encoded-output cap. The shared document byte publisher preserves title JSON receipts and atomic no-overwrite publication; recovery and ZIP preparation retain their existing separate contracts. See [HTML views](RENDER_VIEWS.md).

Markdown shares the HTML control/format display layer but does not HTML-escape
fenced values. All metadata and message bodies are inside fixed-info text fences.
A bounded first pass finds the longest backtick run and counts UTF-8 bytes; both
fences are counted before allocation and publication. Only program text and
ordinals are emitted outside fences. This follows CommonMark isolation, without
claiming every viewer is safe. See [Markdown views](RENDER_MARKDOWN.md).

## Reading archive metadata

`recaplib/archive_schema.py` implements `recap.py --db DB describe-schema` with
one explicit read-only snapshot. It separates known archive tables, FTS5 shadow
names and bounded unknown schema names, and counts legacy-only provenance using
NULL-safe field equality. It does not create lazy tables or validate the archive.
[SCHEMA.md](SCHEMA.md) documents the current layout and tested read-only SQL;
its drift tests are not a database compatibility or stability promise.

`recaplib/render_queue.py` reads one bounded saved queue, validates its current envelope/item shapes and preserves supplied proposal metadata as inert JSON. It reuses the HTML display layer and exclusive byte publisher without changing conversation rendering. The file SHA-256 binds the page to input bytes, not current database truth. No SQL, clock, model or network call is made. See [saved queue views](RENDER_QUEUE.md).

## Derived normalized export

`recaplib/normalized_export.py` streams one source, optionally one conversation,
in global message insertion order under one read-only BEGIN snapshot. The recovery
publisher now has a streaming sibling sharing the existing staged hard-link
publication implementation. Memory is bounded by a message, not source size.
Only original message fields are exported, never origin ledgers or local state.
The derived file hash is not an original-export identity or recovery claim; see
[normalized export](EXPORT_NORMALIZED.md).

## Normalized input contract

[The input contract](NORMALIZED_JSONL.md) names the existing ingest record shape
without changing validation or the archive layout. Synthetic characterization
tests pin ignored members, byte/line provenance, repeated identities and titles.
Normalized inspection and adapter examples remain separate increments.

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

For Python callers replaying retained export bytes, see [explicit byte replay](EXPORT_BYTE_REPLAY.md). This API supplies original parsing labels and
LF/CRLF serialization explicitly; the existing path-based CLI remains unchanged.
It is an import write API, not an exclusive new-DB or verified recovery command.

Use [automated declared-object rebuild](AUTOMATED_REBUILD.md)
with `python recap.py rebuild-archive MANIFEST --plan PLAN --objects DIR
--new-db NEW.sqlite --output NEW.json [--text]`. It never opens the original DB;
it exclusively publishes a checked new DB from explicit replay steps. Declared
title history is not rebuilt, and review state remains undeclared/unrestored.

## Source-wide review view cutoff

Use `declare-review-checkpoint` and `review-titles --since-checkpoint` for an
explicit unsigned source snapshot, not review completion or batch approval.
Content/title comparisons and private-file limits are described in
[the checkpoint guide](REVIEW_CHECKPOINT.md). Existing per-conversation review-state
decisions remain independent; no checkpoint changes the archive.

For import-lineage incremental counts, use `declare-checkpoint` then `changed-since`
with the same explicit source. Continue only on `CUTOFF_VERIFIED`; an unverified
subset reports no delta. This is distinct from the title/content review view cutoff,
not review completion or import permission. Never advance automatically. See
[accepted-artifact cutoff](IMPORT_CHECKPOINT.md).

For contributor byte inventories, `build_manifest.py` reports a read-only plan.
After reviewing it, an exact plan hash can create a separate new candidate outside
the checkout, never overwrite the manifest or approve publication. See
[manifest generation](BUILD_MANIFEST.md).

Handled CLI OS/SQLite/decoder failures use fixed, path-free stderr diagnostics.
Existing validation messages and stdout result failures keep their contracts;
exit 1 alone does not establish that no write occurred. See
[failure diagnostics](ERROR_DIAGNOSTICS.md).

For a private pointer without message text or titles, use `export-provenance`
for one explicit message and `check-provenance` to recheck it. Locator hashes
do not establish authorship, consent, retrieval or publication evidence. See
[message provenance cards](MESSAGE_PROVENANCE.md).

## Synthetic cost observations

The optional benchmark uses deterministic generated input only, verified by exact
regeneration as well as hashes. Separate timing/allocation runs operate on new
scratch archives, not an existing user archive. Local receipts bind fixture and
implementation bytes and state uncontrolled-cache and native-memory limits. They
do not change archive contracts or establish speed, correctness or recovery
guarantees. See [SCALING](SCALING.md).

## Command discovery

`describe` combines the unified argparse tree with explicit current DB/effect
declarations. It reads no archive and grants no authorization. Import/ingest,
title changes and review decisions remain separate authorized write paths;
new-file publication and rebuild retain their existing partial-failure boundaries.
The optional release label is declared metadata, not manifest verification.
See [command catalogue](COMMAND_CATALOG.md).

Command effect regressions execute all declared default-read unified commands on
synthetic fixtures before checking full scratch-tree byte/path invariance. Explicit
conditional writes are tested separately. The archive fixture uses DELETE journal
mode and is closed between operations; this evidence is not a universal no-sidecar
or hostile-filesystem guarantee. See [command catalogue](COMMAND_CATALOG.md).

## Execution error representation

Global `--json-errors` changes only the existing caught-error stderr path in the
unified CLI. Explicit ValueError subclasses retain authored messages and check
order; standard exception families supply coarse codes. No substring classifier,
new catch boundary or transaction behavior is added. Default/standalone diagnostics
and result-level negative JSON remain unchanged. See [JSON_ERRORS](JSON_ERRORS.md).

## Synthetic CLI test boundaries

The test-only `tests/_cli.py` harness invokes explicitly imported entry points
with temporary argv, cwd and captured ASCII streams. It preserves integer return
codes, SystemExit semantics and unexpected-exception traceback visibility, then
restores the caller state. It is serial test infrastructure, not process isolation
or a replacement for interpreter startup, fd-level behavior or subprocess deadlines.

The first migrated family is adapter native output, title API validation, title
document output, title file encoding and saved title responses. Commands parsed
from guides remain real subprocesses, including the saved-response walkthrough.
Interpreter-mode, temporary-directory environment, audit-hook and fd-leakage
checks also remain real processes. Root CLI help and ASCII-failure smoke checks
exercise the shims that in-process calls bypass. Manifest verification and
publication audit retain their real-process checks. Production CLI output, archive
transactions, provenance and partial-publication behavior are unchanged.

## Agent routing and write stop points

SKILL.md uses the README task categories for navigation and the command catalogue
for current DB requirements and write resources. Archive writes and new-file
publication are listed separately, including conditional output flags. Source
import, title wording and review-state decisions remain operator-controlled; a
saved file or catalogue entry is not approval. Existing detailed boundary prose
is retained with its guides, not replaced by links. Regression checks bind the
routing and write tables to parser/catalogue facts and preserve the prior skill
text. They do not validate an operator's review or grant execution authority.

## Explicit MCP read surface

The optional recap_mcp.py shim enters a standard-library stdio dispatcher with a
fixed six-tool allowlist. It calls read functions directly, never the unified CLI
or a generic shell. Launch-time DB selection is not a tool argument; write flags
and file-input fields are absent and rejected. Each call owns a read connection,
not a session-long snapshot. Request/response bounds do not bound query memory or
wall time. Logical read-only access can still have SQLite sidecar effects and can
disclose private content to the selected client. See [MCP_SERVER](MCP_SERVER.md).

Optional MCP file reads are gated by explicit launch-time input directories and a
lowerable byte admission limit. Canonical-path containment, regular-file status
and size are checked before existing readers. This deliberately preserves those
readers and their source semantics rather than claiming an atomic namespace lease
or hostile-writer protection. Default archive tools are unchanged; no additional
DB access, output writer or automatic directory enumeration is exposed.

The opt-in MCP supplied-proposal queue preserves the existing bounded proposal
loader and read-only review_queue logic. Its extra arguments exist only for
servers launched with allowed input directories. All paths and aggregate declared
size are admitted before loading; the original combined 1 MiB bounded-read check
remains. Raw default queues and CLI contracts are unchanged. Reduced preflight
budgets do not create an atomic filesystem lease, and queue readiness never
authenticates operator approval or enables application.

## Recorded web-export topology

An explicit web import also writes deterministic ID-only nodes, parent links,
mapping ordinals and the supplied pointer state inside its existing transaction.
`show --branch` reads a selected recorded export, not a live website selection.
It neither changes default show ordering nor imports only the active branch.
These additive ledgers do not imply a schema epoch, automatic migration or
manifest-v1 recovery coverage. See [archive branches](ARCHIVE_BRANCH.md).
