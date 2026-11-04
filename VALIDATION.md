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


### Verified branch title proposals

Seven synthetic cases cover current/alternate-path excerpts, unchanged source/database
bytes during generation, whole-archive fingerprint equivalence, unimported byte-hash
rejection, changed role/text/timestamp/parent or missing archived text, legacy ledger
compatibility, missing provenance and missing database rejection, no-user paths,
stale title revision and off-path content additions. Subprocess tests exercise both
entry points through preview/apply, repeat-apply rejection, search, all-branch detail
and title restoration. Real model quality and website mutation remain untested.


### Manual title plan export and recheck

Seven synthetic cases cover the explicit-title prerequisite, metadata-only plan fields,
unchanged database/source bytes, same-title revision changes, reformatted exports before
and after import, content additions, altered values/types/extra keys, restored-title
no-change semantics and local-session CLI equivalence. Duplicate JSON plan keys are
rejected. All execution statuses remain NOT_EXECUTED; no remote title state is tested.

### Typed local text profile

Seven synthetic cases cover typed text selection, exact nonblank whitespace, ignored
nontext/untyped metadata and counts, malformed known shapes before DB creation,
legacy compatibility, conflicting profile changes without rewriting evidence,
idempotent reimport and inspection/receipt parity. A CLI workflow covers typed import,
local title suggestion, preview/apply and manual plan export/recheck while preserving
source bytes. Public Codex ContentItem definitions inform the profile; actual private
sessions, encrypted records and full rollout reconstruction are not tested.

### Rollout context diagnostics and plan warnings

Five synthetic cases cover fixed-key metadata counts without private marker leakage,
compaction/rollback/inherited-history warnings, unchanged raw text and source-line
provenance, unknown record/unsupported-role categorization, basename fallback warnings,
import/inspection parity, idempotence and read-only version-2 plan checks. Old plan
versions fail closed. These tests intentionally do not reconstruct effective replay
history or follow parent references.

### Restricted completed-turn projection

Ten synthetic cases cover media/unknown-field allowlists, session/causal-root boundaries, task/turn aliases, matched explicit boundaries and user
events, rollback then new turns, zero/repeated/all-turn rollback, out-of-range/bool/
float counts, unresolved history/compaction/unknown event rejection, incomplete or
nested turns, ID reuse and mismatches, nontext rejection, no partial text on failure,
original line/hash provenance, standalone/unified CLI equivalence and no database
creation. Full model replay and general Codex rollout compatibility are not established.


### Representative projection coverage

A fixed 13-case synthetic schema matrix originally recorded 3 supported and 10 rejected cases in v2,
without estimating usage prevalence. The v3 accounting increment changes that matrix to 4/9. Additional cases check that scoped context
metadata is not emitted or counted as a user turn, rollback counts remain turn-based,
and missing/repeated/unscoped/mismatched/unknown or malformed context fails closed.


### Token accounting metadata

Four synthetic cases cover repeated scoped events without extra user turns, private
rate-limit metadata not emitted, unscoped/unknown fields, malformed shapes and integer
counter boundaries, and unsupported tool/abort/compaction mixtures. The 13-category
matrix uses a schema-valid nullable accounting payload and verifies 4 supported/9
rejected cases. Nested accounting semantics are not validated or used.


### Optional source message IDs

Six synthetic cases cover absent/null IDs, distinct hash/line projection identity,
rename stability versus byte changes, explicit-ID namespace and invalid/duplicate
rejection, identical text retained without merging, rollback preservation, and strict
encryption/status/nested-turn/unknown metadata rejection. Matrix v4 supports 5 of 13
chosen categories; it is not a real-world usage measurement.

### Retained-turn title bridge

Eight synthetic cases, including discarded explicit-ID consistency, connect typed raw import to retained-turn title suggestion,
preview/apply, title search and manual plan export/check. They verify real archive
IDs rather than projection IDs, whole-raw-content fingerprints, original/DB byte
preservation during generation, one source read, renamed-byte provenance matching,
ambiguous double-import rejection, missing evidence including discarded turns,
unsupported/empty projections, legacy ledger compatibility, stale revision/content
rejection and continued raw discarded-text search. No real rollout or remote title
operation is exercised.

### 2026-11-04: located search evidence and local metadata boundaries

The full synthetic suite passes 288 tests. Nine new excerpt cases cover late
message hits, source-order match selection, Unicode case-fold expansion, Korean
and non-BMP code-point offsets, bounded partial long-term excerpts, title-only
results, export provenance, unchanged archive bytes and both CLIs under ASCII
stdout. The existing archive-scaling and snapshot/concurrency regressions pass.

Nine new local-input cases cover both profiles, corrupt initial/intervening session
metadata, valid alias boundaries, physical line diagnostics, missing/null/zero
and invalid timestamps, unchanged archive bytes after failure, legacy-zero conflict
protection and clean CLI rejection without echoing malformed values. No actual
conversation history, account, model or external service was used. Publication
scanning and byte-manifest verification pass for the selected 96-file candidate.
Remote CI outcomes are checked separately for the exact pushed commit.

### 2026-11-04: Unicode JSON rejection before archive access

Eight additional synthetic cases exercise lone surrogate values and object keys,
including unused nested metadata, across normalized JSONL, web and both local
profiles. They check no database creation, byte-for-byte preservation of existing
archives, inspection/import consistency, valid escaped pairs/emoji/Korean round
trips and clean CLI errors without input content. The complete suite now passes
296 tests. Publication scanning and byte-manifest verification cover the selected
97-file candidate. No original text is repaired or replaced by this decoder.

The earlier web-branch ASCII-output fixture now uses valid Korean/emoji text.
A separate regression explicitly rejects the formerly accepted lone-surrogate
branch input without altering the export or echoing its content.

### 2026-11-04: selected conversation evidence

Fourteen new synthetic tests cover exact-message and paginated detail views,
validation before database access, empty pages, source/conversation isolation,
quoted IDs, legacy/absent provenance, current/original title preservation, CLI
parity and rejection, Unicode output under ASCII terminals and no-write checks.
SQLite row-factory instrumentation verifies that only selected bodies and
provenance are materialized. A WAL regression mutates title/body/provenance during
the read and confirms that the current result retains one consistent snapshot. A search-to-detail round trip retains exact snippet
offsets and source-artifact provenance. The complete suite passes 310 tests. Publication scan and byte-manifest verification
cover the selected 99-file candidate. Pagination limits message count, not bytes
or occurrences; separate requests do not share a durable snapshot. No real corpus
or external service is tested.

### 2026-11-04: bounded search sample coverage

Fifteen new synthetic tests cover late rare-term evidence, deterministic streaming
coverage/tie behavior, insertion-order output, duplicate case-folded query terms,
exact matching-body counts, explicit unsampled terms, current/historical title-only
results, unchanged AND/ranking/limit behavior, source/export isolation, ASCII-safe
CLI parity and no-write checks. A 51-body export fixture verifies that only four
entering candidates need excerpt/provenance retrieval while the final sample stays
at three. Coverage is measured on full selected bodies, not visible excerpts, and
no globally optimal or semantic sample selection is claimed. The complete suite
passes 325 tests; publication scanning and manifest verification cover 100 files.


### 2026-11-04: source-attributed local titles and Unicode writes

Nineteen new synthetic tests cover exact per-content producer attribution, media
positions, explicit/legacy variants, malformed/unknown labels, fixed coverage
counts, single-read source bytes, whole-conversation archive consistency, source
isolation, repeated IDs, renamed fallback identities, duplicate-import ambiguity,
preview/apply freshness the documented example and LF/CRLF/CR physical line alignment (including embedded Unicode separators and excluded-event locator drift). Raw imports remain unchanged
and searchable. The pinned official Codex source is documented; labels are not
authenticated authorship, trust, permission or semantic validation. No private
conversation, undocumented web schema or external model call is used.

Four replay tests accept absent/null/explicit legacy history mode while retaining
paginated, unknown and inheritance rejection. Four CLI tests cover Unicode title
write acknowledgments, suggestion and listing parity under ASCII stdout. This
prevents a successful title commit from appearing to fail when printing its
Unicode JSON result. The complete synthetic suite passes 352 tests. Publication
scanning and byte-manifest verification cover 106 selected files. Remote CI is
checked separately for the exact pushed commit.


### 2026-11-04: discover export identities before import

Twenty new synthetic tests exercise the read-only export inventory for web, legacy
local and typed local formats. Coverage includes exact IDs and existing web titles,
zero-text/media-only identities, duplicate web IDs, repeated local metadata and
message occurrences, full-file/off-page validation, body-field exclusion, source
hashes and single reads, Unicode/newline parity, pagination and both ASCII-safe
CLIs without a database. The documented examples and discover-to-selected-import
workflow pass. A conflict regression distinguishes parser selection support from
successful database insertion. No title or ID redaction, memory bound or vendor
schema completeness is claimed. The full suite passes 372 tests; publication
scanning and byte-manifest verification cover the selected 109-file candidate.


### 2026-11-04: optional original-export hash consistency

Sixteen new synthetic tests bind inventory pages, inspections and imports to an
operator-supplied whole-file SHA-256. All formats and CLI routes cover matching
receipts, exact provenance, original no-option compatibility, syntax rejection
before source reads, mismatch rejection before parsing/database access, changed
unselected content and newline bytes, unchanged existing/new database safety,
renamed source files, immutable read snapshots and continued format/selection validation.
The copyable documentation command verifies the shipped fixture's actual hash.
The complete suite passes 388 tests. Publication scanning and byte-manifest
verification cover 110 files. This hash check is not authenticated authorization,
a persistent snapshot, a completeness claim or an external service.


### 2026-11-04: consistent title excerpts and read snapshots

Ten new synthetic regressions align the informational title command with ordinary
local excerpt proposals for greetings, Korean/control cleanup, truncation and
no-usable-user fallback. They verify read/write receipt parity, raw text and
original/current/history preservation, source isolation, ASCII-safe CLIs and
read-only/missing-database behavior. A WAL concurrent mutation test verifies that
content, original/current title, revision and history share one read snapshot;
removing the read transaction makes that regression fail. The unchanged excerpt
algorithm now lives in one pure helper and is reexported for existing callers.
No semantic summary or new branch/source filtering is introduced. The complete
suite passes 398 tests; publication scan and manifest verification cover 112 files.


### 2026-11-04: read-only reimport conflict diagnostics

Sixteen synthetic tests cover archive/source identity comparisons, title-only,
text, role, timestamp and mixed changes, repeated-input counts, bounded samples,
new rows preceding conflicts, local profiles, selected/hash-bound input, one
source read, no database creation, unchanged schema/provenance/title history,
canary-value exclusion and both CLI exit/report paths. A WAL test holds all
comparisons to one read snapshot, and a later-change test confirms real import
still rejects conflicts after a previously clear advisory report. The documented
commands run against a new synthetic scratch archive. No conflict override,
repair, title-value output or import policy change is introduced. The complete
suite passes 414 tests; publication scan and manifest verification cover 115 files.


### 2026-11-04: supplied web/local/model candidate review

Sixteen independent synthetic regressions cover explicit supplied proposal files
in the existing title queue: mixed web-branch/local-attributed evidence, retained
metadata, operator/mock/external provider labels, unchanged default behavior,
missing/stale/invalid candidates without fallback, source/duplicate rejection,
state/history filters, collisions and one-at-a-time fresh preview/apply. Two WAL
regressions keep metadata and content validation in the queue's single snapshot.
Loader tests cover bounded single file reads, combined 1 MiB input, Unicode,
duplicate JSON keys and nonfinite values. The latter revealed a decoder gap that
was fixed before publication. The exact documented mixed web/local workflow runs
with explicit review assertions before apply and source-byte preservation.

The complete suite passes 430 tests; publication scan and manifest verification
cover 117 files. Supplied context/provider labels remain unsigned and unverified;
only selected page candidates receive archive-content validation. This increment
adds no semantic model call, automatic fallback, bulk apply or remote mutation.


### 2026-11-04: Windows walkthrough path substitution

Remote Windows CI exposed a portability error in the documented-command test:
it inserted an absolute Windows scratch path before POSIX shell tokenization,
which consumed backslashes and split spaces. The test now tokenizes the published
relative command first, then replaces complete argument values. A platform-neutral
regression exercises Windows and POSIX paths containing spaces, redirection and
a quoted multiword query. This is a test-harness fix, not an application path
rewrite. The full local suite passes 431 tests; 117-file publication and manifest
checks pass. The corrected commit's Windows/Linux CI is checked separately.


### 2026-11-04: review explicit candidates before pagination

Sixteen independent synthetic tests cover the opt-in supplied-only title queue:
a late identity otherwise absent from the first 20 items, database ordering and
chunk boundaries, disjoint rename/unsupplied/state counts, empty/unknown/invalid
candidates, source isolation, outside-subset title collisions, effective review
state and snapshot consistency. SQL tracing verifies excluded message bodies are
not loaded even with a state filter. A 241-identity regression covers quoted/Unicode
chunk boundaries and last-identity continuation without repeated OFFSET scans.
CLI coverage preserves fresh individual
preview/apply and no-write review behavior. The mixed web/local documented flow
now uses this explicit subset option and retains the verified Windows path fix.

The complete suite passes 447 tests; publication and manifest checks cover 118
files. Default behavior is unchanged. Subset mode scans metadata and preserves
whole-source current-title collision checks; it is not an archive-memory bound
or authorization to apply candidates. No real corpus or model call is used.


### 2026-11-04: verified source scopes for title requests

Twenty-seven independent synthetic tests exercise provider-neutral preparation
from pinned web branches, retained local turns and explicitly source-attributed
local text. They reproduce and prevent abandoned paths, rolled-back requests and
harness parts reentering the bounded user payload. Selection precedes message and
character limits; all eligible evidence, not just a first excerpt, is considered.
Repeated identical attributed occurrences collapse at the most recent position,
while different selected text for one archive ID rejects as ambiguous.

Existing suggestion builders share the verified selection paths without changing
their supported outputs. Tests cover complete raw fingerprints, source/occurrence
changes, no fallback, readonly single source reads, malformed and capped local
context, consent hashes, Unicode CLI behavior for all three scopes, supplied-only
queue review, individual preview/apply and searchable local titles. Existing raw
adapter response shapes remain unchanged. No actual external transport, semantic
quality validation, source rewriting or remote title mutation is added.

The complete suite passes 474 tests; publication and manifest checks cover 119
files. Selection context remains private, descriptive and unsigned. Local replay
and attribution are separate alternatives, not a combined effective-human-history
reconstruction. Full source/archive reads remain necessary; outbound bounds do
not establish an archive memory bound. Exact-commit cross-platform CI is checked
separately after publication.


### 2026-11-04: complete locally supplied title responses

Twenty-four independent synthetic tests exercise saved-request completion without
any provider execution. The current archive and explicit source scope reconstruct
the complete preparation document; canonical comparison rejects changed bodies,
recomputed forged hashes, configuration, source/context changes and numeric-type
substitutions. Response evidence remains limited to the exact bounded user payload.

Tests cover raw and all three scoped requests, single-read bounded UTF-8 files,
nonfinite/duplicate-key/malformed inputs before database reads, repeatable readonly
completion, no sockets/subprocesses/automatic apply, provider-kind combinations,
Unicode review/apply/search and post-completion content/revision changes. The exact
new documented walkthrough uses invented request/response data, explicit pre-apply
review assertions and Windows-safe command tokenization. Existing prepare output
and disabled/unconfigured external generation remain unchanged.

The complete suite passes 498 tests; publication and manifest checks cover 122
files. The response is explicitly marked locally supplied with provider execution
not performed. Neither those labels nor payload/hash consistency prove model
execution, semantic title quality, actual prior transmission or consent. No real
model call, credential handling, private corpus, remote rename or merge is added.
Exact-commit cross-platform CI is checked separately after publication.


### 2026-11-04: continue ranked conversation searches

Thirteen independent synthetic tests traverse cursor pages across current-title,
historical-title and body matches without changing ranking or evidence excerpts.
They cover 1,207 matching conversations beyond the single-call limit, changing
page size, Unicode/quoted/control-character IDs, exact page counters and source,
query, history and export-scope binding. Malformed tokens reject before DB access.

A same-snapshot streaming digest binds matching identities and ranking groups.
Tests reject stale membership/rank and missing positions, while allowing explicitly
fresh wording when membership/rank is unchanged. WAL concurrency verifies that one
scan supplies both results and cursor consistency. SQL tracing checks one body scan,
no OFFSET and no writes; a 2,200-conversation late-page memory regression checks
that skipped results are not retained. Both CLIs, export provenance, deterministic
repeats and explicit oversized-identity pagination blockers are covered.

The complete suite passes 511 tests; publication and manifest checks cover 124
files. Cursors are private unsigned continuation data, not frozen content snapshots,
authentication or title approval. Every page still scans eligible evidence. No
private corpus, external transmission, source mutation or merge is introduced.
Exact-commit cross-platform CI is checked separately after publication.
