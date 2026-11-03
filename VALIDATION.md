# Validation record

Release preparation date: 2026-11-02 (Asia/Seoul).

- Python standard-library unittest: 5 synthetic tests passed.
- Limited public-file/type/secret-pattern scan: passed.
- Manual selected-content review: no actual conversation, researcher corpus, private
  configuration, credential, real experiment or article/book/figure asset selected.
- Examples: synthetic; no scientific or persona-predictive validation claimed.
- Private history import: none; new public repository with a separate initial history.

The scanner is not a complete secret detector, anonymizer or legal clearance tool.
Framework-level code/tests and general methods were selected; private source DBs
and third-party source materials were excluded rather than redacted and republished.
Remote publication is verified separately after committing; this file does not
claim an upload has succeeded merely because local tests passed.

## 2026-11-03 increment

Run `python -m unittest discover -v` and `python audit_publication.py`.
New tests exercise the documented synthetic workflow and rejection boundaries.
On restricted Windows hosts, set TEMP and TMP to an authorized writable directory.
No real corpus, account data, or scientific fidelity evaluation was used.

Second increment: 8 tests passed; failure boundaries and deterministic repeated results covered.

Third increment: 10 tests passed, including supplied-evidence rejection and deterministic output. No external model/search integration tested.

Fourth increment: CLI end-to-end scenarios and failure recovery added. Local tests: 12 passed. Remote CI status is recorded separately in the private development log.

Fifth increment: 14 local tests passed. New CLI paths, source boundaries, deterministic output and tamper/no-overwrite checks are covered. See private development log for remote matrix CI.

Sixth increment: read-only conversation inventory and detail views added. Local
Python standard-library suite: 20 synthetic tests passed, including CLI list/show,
missing database rejection, title override visibility without evidence mutation,
source isolation, pagination, byte-for-byte no-write checks, local/web provenance,
multiple export hashes, and compatibility without optional tables. No real corpus,
online collection, semantic title quality or active-branch reconstruction tested.

Integrated fifth/sixth increment: 22 synthetic tests passed in the cloud workspace.
Both conversation title search and structured read-only list/detail views preserved.
Publication scanning and manifest verification passed for the exact selected files.

Seventh increment: 27 synthetic tests passed. Search regression checks preserve
cross-message AND semantics, title-first ranking, exact match totals, truncation,
and three-snippet caps. An archive with over 8 MB of synthetic message text stays
below 2 MB of traced Python search allocations at limit=2; this excludes SQLite
native memory. SQL trace tests verify page-only title fetches and exact detail
filtering. Empty archives and noninteger search limits are covered.
Latest-title cursor tests cover repeated revisions, source filters, orphan history
entries and a single history query across multiple conversations.

Windows CI exposed a test-fixture connection left open after a transaction. The
fixture now closes it explicitly before temporary-directory cleanup. No production
query logic was changed in this correction. All 27 local tests pass again.

Eighth increment: 36 synthetic tests passed. New web checks cover self/disconnected
cycles, invalid parent/node shapes, duplicate object keys, malformed authors and
timestamps, clean CLI rejection, epoch-zero preservation, unchanged existing archive
bytes on validation failure, a 4,000-node chain, and valid fork order/provenance.
Legacy epoch-zero conflict regression confirms old archive bytes are preserved.

Ninth increment: 38 synthetic tests passed. A regression reproduces the former
null-revision stale-write bypass and now verifies rejection without changing title
history or archive bytes. Missing, boolean, fractional, string and negative leases
are rejected. CLI null-revision and missing-database failures contain no traceback.

Tenth increment: 44 synthetic tests passed. Local excerpt proposals cover English/
Korean greeting skip, explicit greeting fallback, control removal, truncation,
user-only evidence, deterministic/no-write generation, CLI output, and stale-content
rejection. Existing preview/apply handles the proposal; semantic title quality and
external model integration are not tested or claimed.

Eleventh increment: 50 synthetic tests passed. Shared duplicate-key decoding covers
nested/escaped keys, valid Unicode values, local CRLF physical line numbers,
no-create/no-change archive failure boundaries and clean proposal CLI errors.
No real conversation files or private folders were read.

Twelfth increment: 58 synthetic tests passed. Inspection checks web/local counts,
original hashes, omitted message text/identities, empty/nontext warnings, coverage
receipt equivalence, CLI operation without database access and required DB arguments
for mutations. Counts describe parser extraction only, not corpus completeness.
Malformed web title types are rejected during inspection.

Thirteenth increment: 63 synthetic tests passed. Shared title validation covers
control/Unicode line separators, surrogate code points, valid Korean/emoji, length
boundaries and no-history-change rejection across manual/proposal paths. API and
CLI title updates leave nonexistent database paths uncreated.
Existing database paths containing percent/hash characters are covered.

Fourteenth increment: 72 synthetic tests passed. Publication verification rejects
unexpected/hidden files, changed or missing bytes, unsafe and case-aliased paths,
malformed metadata, invalid JSON and symlinks (where supported). Generated bytecode
and Git metadata exclusions are tested explicitly. Exact selected candidate passes
both publication scan and complete manifest verification.
Windows-reserved path components, manifest symlinks and duplicate metadata keys
are also rejected. Concurrent hostile filesystem replacement is outside this check.

Concurrency regression increment: 75 synthetic tests passed. Two simultaneous title
writers sharing one revision produce exactly one change and one stale-preview
rejection. WAL tests commit a title change during inventory/search reads and verify
the current result retains its snapshot while the next read sees the new title.
These are local SQLite guarantees under the tested flows, not distributed locking.
The search snapshot test is sensitive to removing the explicit read transaction.
Concurrent-writer coverage is a smoke test, not exhaustive scheduling proof.

Unified CLI increment: 79 synthetic tests passed. Subprocess workflows cover
inspection without DB, export import, list/show/find, title suggestion and checked
title updates through recap.py. Standalone command equivalence and existing
normalized ingest/message-level FTS behavior remain covered.

Occurrence-ledger increment: 84 synthetic tests passed. Duplicate local message IDs
on different lines preserve both locators while message insertion stays idempotent.
Legacy-only reads, retained-export recovery, other-source backfill, trigger-induced
full rollback and rollback of the additive schema upgrade are covered. Existing
message/title data and legacy provenance rows are preserved.

Provider-neutral adapter increment: 99 synthetic tests passed. Local/mock generation
is separate from preview/apply; exact-payload consent mismatches and disabled external
configuration fail closed, and no external transport exists. Tests cover bounded
user-only payloads, response whitelisting/evidence subsets, content/revision guards,
fixed-code errors, malformed Unicode/JSON, response-size expansion, endpoint/timeout
edges, subprocess stderr capture and termination/reaping after timeout or worker exit.
Actual external provider behavior, cost, cancellation and semantic quality remain
unverified. No credentials or private conversations were used.
Adapter CLI Unicode proposals also work under an ASCII stdout encoding.

### Web text variants and offline title round trip

Synthetic tests cover exact code/output text, unsupported fields, skipped attachment
metadata, ambiguous/malformed shapes rejected before database creation, and fork
coverage without content leakage. A subprocess CLI scenario exercises inspect,
import, local-adapter generation, preview, checked apply, stale rejection, current-title
search, detail and title restoration. Generation/preview preserve database bytes and
the original export is unchanged. No external service or actual model quality is tested.


### Read-only web branch selection

Eight synthetic cases cover ASCII-stdout Unicode escaping and shuffled mapping order, current versus explicit alternate
and interior nodes, null roots, parent-path order/provenance, invalid pointer rejection,
ambiguous conversation records, off-path cycles, 4,000-node iterative traversal,
unchanged all-branch normalization and standalone/unified CLI equivalence without
creating a database. Original file bytes remain unchanged.
