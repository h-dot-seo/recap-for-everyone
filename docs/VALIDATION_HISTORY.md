# Validation history

This file holds every dated validation entry of recap-for-everyone, unchanged and in
the order in which it was written, beginning with the release preparation record of
2026-11-02. The current snapshot (release string, CI matrix, how to verify locally and
what the record does not claim) is [VALIDATION.md](../VALIDATION.md); new entries are
appended here. Test counts, runtimes and file counts in older entries describe the
tree at that time, not the current one.

Release preparation date: 2026-11-02.

- Python standard-library unittest: 5 synthetic tests passed.
- Limited public-file/type/secret-pattern scan: passed.
- Manual selected-content review: no actual conversation, researcher corpus, private
  configuration, credential, real experiment or article/book/figure asset selected.
- Examples: synthetic; no real-archive or personal-data validation claimed.
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

Fourth increment: CLI end-to-end scenarios and failure recovery added. Local tests: 12 passed. Remote CI status is recorded in the repository's GitHub Actions history.

Fifth increment: 14 local tests passed. New CLI paths, source boundaries, deterministic output and tamper/no-overwrite checks are covered. Remote matrix CI results are in the GitHub Actions history.

Sixth increment: read-only conversation inventory and detail views added. Local
Python standard-library suite: 20 synthetic tests passed, including CLI list/show,
missing database rejection, title override visibility without evidence mutation,
source isolation, pagination, byte-for-byte no-write checks, local/web provenance,
multiple export hashes, and compatibility without optional tables. No real corpus,
online collection, semantic title quality or active-branch reconstruction tested.

Integrated fifth/sixth increment: 22 synthetic tests passed in a separate workspace.
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


### 2026-11-04: consistent source signatures and physical lines

Twenty synthetic regressions cover one optional initial UTF-8 BOM across web,
legacy local, typed local and normalized ingestion. Shared decoding preserves
original byte hashes/sizes and all quoted Unicode characters. LF, CRLF, bare CR,
mixed boundaries and blank lines retain consistent physical locators. This fixes
supported bare-CR sessions that imported but failed replay/title reconstruction.

Tests cover inventory and selected import, branch/replay/attributed title input,
manual plans, adapter preparation, Unicode preview/apply/search, single source
reads, unchanged ZIP-member output bytes and existing empty-input policies.
Signature/newline changes still fail old hash leases and provenance; intentional
reimport preserves message identities and adds original occurrences. Changed
source framing also invalidates saved scoped request context after reimport.

Double/misplaced signatures, damaged UTF-8, UTF-16/32, duplicate keys and malformed
records fail before database or prepared-output mutation. Replay supplies no partial
text on failure. Generic proposal/response JSON contracts and replay grammar remain
unchanged. The complete suite passes 531 tests; publication and manifest checks
cover 127 files. No real corpus, repair, encoding guessing, model transmission or
merge is added. Exact-commit cross-platform CI is checked after publication.


### 2026-11-04: opt-in canonical Unicode conversation search

Thirteen independent synthetic regressions cover NFC/NFD Korean and accents,
canonical mark reordering, pre-fold Greek ypogegrammeni, Hangul composition and
existing case-fold expansion. Default matching and cursor scopes stay unchanged.
Canonical mode applies consistently to current titles, opted-in history and bodies,
with source/export filters, normalized equivalent queries and mode/Unicode-version
cursor rejection before archive access. Invalid option types also fail before reads.

Both web and typed-local synthetic exports complete import, canonical find, exact
message view, reviewed title application, current lookup and historical lookup.
Original exports, archived message evidence, provenance and read-only database
bytes are preserved. ASCII-output CLI parity and unchanged source slices are
checked, including reordered covering intervals longer than the excerpt. A mapper
check over 100,000 ordinary Hangul characters stays below 512 KiB traced allocations;
pathologically long combining sequences are explicitly not constant-memory.

The suite includes 1,000 seeded transform/mapping trials. Separate local checks
compared all 1,112,064 Unicode scalar values and 20,000 mixed-character cases with
the runtime normalization transform (Unicode 15.0.0); an independent 10,000-case
randomized check over decomposition/case-fold-changing characters also passed.
These checks do not claim exhaustive multi-character sequence verification.

The complete suite passes 544 tests. Publication scanning and exact byte-manifest
verification cover 130 files. No corpus, network/model integration, source repair,
compatibility normalization or merge is introduced. Exact-commit Ubuntu/Windows
Python 3.10/3.12 CI is verified separately after publication.


### 2026-11-04: malformed local records and detached title inputs

Nineteen independent synthetic regressions cover malformed known response records
and Python title-input snapshot isolation. Both local profiles reject nonobject
response payloads, missing/invalid/blank type discriminators and malformed message
roles before archive creation or mutation. Valid nonmessage types and unsupported
roles retain existing skipped counts and warnings. Inspection, inventory, conflict
checks, title helpers, BOM/physical-line diagnostics and clean CLI errors are covered.
No actual sessions or private configuration were read; typed structure is checked
against the pinned public response definitions cited in the input-scope guide.

Preview copies nested proposal/evidence/context values before reads; apply copies
the reviewed envelope before validation and writing. Regression hooks change the
caller objects during reads or after validation and verify that the original
independent snapshot is used. Replacement wording and unsigned advisory behavior
remain unchanged. Nonfinite/unsupported/cyclic/invalid-Unicode metadata fails before
archive access. Numeric/boolean IDs cannot match text archive IDs by SQLite coercion;
valid literal Unicode, quoted, padded and whitespace conversation IDs stay exact.

Excessively nested title JSON fails without traceback in both CLIs and all four
preview/apply commands, preserving missing/existing database boundaries. The complete
suite passes 563 tests; publication scanning and byte-manifest verification cover
132 files. No new signature/approval claim, partial import, repair, real corpus,
model transmission or merge is introduced. Remote matrix CI is checked separately
for the exact pushed commit.


### 2026-11-04: opt-in evidence at the title review step

Thirteen independent synthetic regressions cover `preview-title --with-evidence`
and its standalone/Python equivalents. Default response structure remains unchanged.
Opt-in output selects the first five distinct cited user messages, preserves raw
2,000-code-point prefix slices, and reports duplicate/omitted/truncated counts.
It excludes uncited and nonuser messages, keeps exact original offsets, and does
not treat scoped proposal metadata as a verified passage selection.

Provenance sampling unions legacy/additive ledgers, returns at most three sorted
occurrences per selected message with exact counts, and preserves source/conversation
isolation. Tests cover absent/single ledgers, Unicode/controls/whitespace, exact
excerpt boundaries, empty legacy bodies, invalid/stale evidence, strict boolean
validation, detached inputs, ASCII CLIs and preview-only flag rejection on apply.

One read transaction now covers validated content, current title/revision and
optional provenance. A WAL writer changes body/artifact metadata/title/provenance
mid-preview; all returned evidence remains from the earlier consistent snapshot,
and subsequent preview/apply rejects the stale proposal. Explicit apply and repeat
rejection remain intact. Both shipped synthetic web-branch and attributed-local
fixtures run import through reviewed title application/search without source changes;
the local preview explicitly retains the raw harness prefix omitted by generation.

The complete suite passes 576 tests. Publication scanning and byte-manifest
verification cover 135 files. Body caps are not a total document/memory/work bound;
raw excerpts are not semantic support or privacy clearance. No real corpus, model
call, transmission, automatic approval or merge is added. Exact-commit four-job
CI is checked separately after push.


### 2026-11-04: bounded neighbors around an exact message identity

Thirteen independent synthetic regressions cover the new explicit around-message
view. Default/exact/page behavior remains unchanged for valid identities. Context
resolves two neighbors per side by default, accepts each count from zero through
50, and clips at conversation boundaries. The 101-message maximum, actual/omitted
counts, anchor/window offsets and continuation offset are verified across interleaved
primary keys, descending timestamps and nonlexical/quoted/Unicode message IDs.

Source/conversation/anchor scope is exact. Invalid identity types, counts and mode
combinations fail before database access, and accepted padded strings stay literal.
Row-factory instrumentation verifies that only window bodies/provenance materialize;
legacy/additive/no-provenance behavior and ASCII-output CLI parity are covered.
A concurrent WAL write after window selection does not mix changed title/body or
provenance with the current snapshot. Subsequent calls correctly see the new state.

Synthetic web/local flows cover import, search, around-message navigation and an
explicit revision-checked title change while preserving source bytes and message
evidence. An export-scoped search regression confirms the intentionally broader
neighbor scope: it is not silently filtered to the search export or presented as
an active branch, retained history, chronological turn or reply relationship.

The complete suite passes 589 tests. Publication scanning and exact byte-manifest
verification cover 136 files. Message-count bounds do not bound text/provenance
bytes or all native database work. No private corpus, model call, external transfer,
automatic title mutation or merge is introduced. Exact-commit four-job CI is checked
separately after publication.


### 2026-11-04: explicit bounded local title-history review

Eighteen independent synthetic regressions cover the new read-only history API
and both CLI routes. They verify newest-first local change events, global sparse
revision IDs, exact source/conversation scope, repeated/no-op/reversal events,
current versus historical revisions, offset boundaries, total/remaining counts
and optional stale-page rejection. Other conversations' writes and new message
imports do not invalidate the title-only guard; a no-op title write does.

Original titles remain verbatim, including empty, multiline and overlength legacy
values. Missing history tables are not created, missing databases stay missing,
and orphan history cannot create an unknown conversation. Invalid identity/count/
revision types are rejected before database access. SQL authorizer instrumentation
denies message-body/role reads, and a row-factory check bounds materialized rows
while reading a small page from 2001 events. A concurrent WAL rename does not mix
the old current title with a new count or page.

Synthetic web/local imports run through Unicode CLI history reads and deliberate
revision-checked reversal. The reversal adds an event, preserves earlier labels,
and rejects replay of the stale current revision. History itself performs no write
and is not a content-bound proposal or approval. Existing title/suggestion behavior
is retained; there is no new automatic undo operation.

The full suite passes 607 tests. Publication scanning and byte-manifest checks
cover 139 files. Row caps do not bound individual strings, native query work or
latency, and old labels can expose removed private information. No private corpus,
model call, external content transfer, automatic title mutation or merge is added.
Exact-commit four-job CI is verified separately after push.


### 2026-11-04: meaningful Unicode title excerpts

Sixteen independent synthetic regressions and one explicit review/apply/search
regression cover the shared excerpt rule. All built-in Korean greetings match
canonically decomposed forms while selected requests and greeting fallbacks retain
their original normalization. Compatibility forms, lookalikes and unlisted
punctuation do not silently gain greeting status.

ZWJ/ZWNJ remain in short emoji/text-shaping labels. Other Cc/Cf characters keep the
existing space-replacement behavior, including emoji tags. The actual cleaned
80-code-point prefix must contain an alphanumeric code point: retained invisible,
punctuation, combining-mark or non-alphanumeric emoji prefixes do not become usable
because a letter exists beyond the cap. Tests distinguish the last included and
first excluded positions and confirm that cleaned-away controls consume no space.
The tests explicitly retain code-point slicing behavior that can split a combining
or emoji sequence; no complete grapheme or rendering support is claimed.

Raw suggestions, informational title reads, review queues, web-branch proposals,
local replay, source-attributed proposals and the offline local adapter agree.
Replay/attribution use separate supported synthetic fixtures, preserving the replay
metadata restriction. Five ASCII CLI paths, source bytes, archived text, IDs,
original hashes and content fingerprints are checked. Format-character privacy
hints remain visible. Canonically equivalent edits to raw content still invalidate
saved proposals. Explicit application creates only a local title event, exact-emoji
and canonical Korean title searches succeed, and repeat apply is rejected as stale.

The complete suite passes 624 tests, and public audit/manifest checks cover 140
files. No source repair, added dependency, live model call, private corpus, automatic
approval or merge is introduced. The small built-in greeting list and heuristic
excerpt remain review aids, not semantic summaries or privacy clearance. Exact
commit Ubuntu/Windows Python 3.10/3.12 CI is checked separately after publication.


### 2026-11-04: unambiguous source identities before archive work

Ten independent synthetic regressions cover one shared resolver for web
id/conversation_id and local id/session_id fields. Conflicting nonempty strings
and malformed primary or secondary values reject the source, including empty-text
and unselected records. Missing/null/empty-string alias fallback remains explicit
compatibility. Equal decoded strings retain their exact spelling; whitespace,
padding and canonically distinct Unicode identities are not normalized together.

Supported local user/assistant message IDs reject nonstring values before text
omission. Missing/null/empty values retain basename/physical-line IDs and coverage
warnings. Unsupported role/nonmessage skips and the stricter replay grammar remain
unchanged. BOM and physical-line diagnostics preserve original locations without
echoing conflicting identities or message contents.

Tests verify inspection, selected import, inventory, source conflict checks, web
branch proposals and manual title plans agree. Malformed source cannot create a
new archive or mutate an existing one, and a conflicting source cannot produce a
proposal/plan for a silently chosen target. Valid alias-only/matching/fallback
inputs retain source bytes, hashes, locators and evidence IDs through the local
workflow. Existing archives are not migrated or automatically invalidated.

The full suite passes 634 tests; publication audit and byte-manifest checks cover
142 files. No UUID/prefix inference, source repair, private corpus, model call,
external transmission, remote rename or merge is introduced. The previous
80-code-point title limit and its documented rendering limitations are unchanged.
Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked separately after push.


### 2026-11-04: clean nested-JSON and incoming-conflict failures

Fifteen synthetic regressions cover decoder recursion errors and contradictory
incoming identities. Shared JSON decoding translates RecursionError into a fixed
ValueError without raising the interpreter limit or echoing input. Deep arrays in
web/local/normalized metadata fail cleanly, including unselected web content and
late JSONL rows. Replay reports INVALID_JSON at the physical line without partial
text. Long bracket strings and ordinary nesting remain accepted. Tests deliberately
do not assert a universal object/array depth threshold across Python runtimes.

Incoming role/timestamp/original-title/text conflicts are detected before SQLite
connection for normalized ingest, web duplicate conversation/node records and
repeated explicit local message IDs. A mocked connection proves rejection precedes
schema creation; missing paths remain absent and existing archive bytes stay equal.
BOM/LF/CRLF/CR physical normalized-line diagnostics and clean CLI failures omit
private synthetic values. Export-adapter conflict lines remain selected normalized
occurrence numbers, not original source locations.

Identical repeats preserve record counts, first source-line behavior, FTS deduplication
and distinct provenance occurrences. Absent message IDs remain distinct physical
occurrences. The check covers only the selected incoming batch; parser-only
inspection and read-only conflict reporting retain their earlier roles. An archive-
only conflict test verifies BEGIN IMMEDIATE precedes comparisons and the entire
batch rolls back, so preflight does not replace the existing write-lock checks.

The complete suite passes 649 tests. Publication audit and byte-manifest verification
cover 143 files. This does not add a fixed input/depth/memory budget or promise that
unrelated database/I/O failures leave no files. Existing empty archives are not
removed. No actual corpus, model transmission, automatic repair, source mutation
or merge is added. Exact-commit four-job CI is checked separately after publication.

### 2026-11-04: choose meaningful user-message title evidence explicitly

Fifteen independent synthetic regressions verify the optional exact message selector
on suggest-title and the standalone generator. A later concrete user request can
supply the excerpt instead of a generic first request. Default proposal shape and
first-non-greeting behavior remain unchanged. Invalid selector shapes reject before
archive access; unknown, nonuser or unusable selected messages never substitute
another message. Literal padded/NFC/NFD IDs remain distinct and source/conversation
scope is exact.

The generator reads one full content snapshot and retains its full fingerprint,
so later imports outside the chosen evidence invalidate proposals and reviewed
previews. Shared cleanup, greeting advisory and 80-code-point truncation stay
unchanged, including the documented combining/emoji cut limitations. The optional
selection metadata describes raw archive evidence, not authenticated authorship,
branch/replay filtering, semantic quality or approval.

Tests cover ASCII CLI parity and clean failures, supplied review queues, bounded
review evidence, explicit operator wording, checked apply and current-title search.
The shipped synthetic web example runs the documented commands exactly, with
argument parsing before platform path substitution. It verifies no title change
before the separate apply step, source/message/provenance preservation and stale
reapply rejection. Web, legacy local, local-codex and basename/physical-line fallback
IDs are covered. Explicit abandoned-branch and rolled-back raw message choices do
not acquire branch/replay claims.

The complete suite passes 664 tests. Publication audit and byte-manifest checks
cover 145 files. No real conversations, model execution, remote mutation, automatic
relevance inference, bulk approval or merge is added. The selector still reads the
whole conversation content snapshot; it is not a resource bound or privacy filter.
Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked separately after push.

### 2026-11-04: reject malformed typed parts before losing user evidence

Thirteen independent synthetic tests reproduce and prevent a typed local content
part with an array type from silently disappearing while an earlier greeting is
imported and proposed as the title. Present null/boolean/number/container/empty/
whitespace type values now reject supported user/assistant messages in local-codex.
A malformed later part rejects even after valid text and when its own text is
absent, empty or whitespace. A mocked SQLite connection proves no database access
occurs first; missing archives remain absent and existing source/archive bytes stay
equal on rejection.

Whole-file inspection, inventory, conflict checks, selected import and source-backed
attributed proposals reject malformed later or unselected content without partial
results. Fixed diagnostics locate the physical line across BOM, LF, CRLF, CR and
blank lines without echoing the tag or text. Existing malformed content-array,
item-object and text-value failures also gain physical-line context. Five ASCII
CLI error paths produce no traceback, payload or partial JSON.

Missing type tags intentionally remain counted compatibility skips. Valid unknown,
media and padded nonempty tags remain unsupported without coercion or metadata
stringification. Legacy profile extraction, unsupported roles/nonmessage variants
and metadata-only utility paths retain their earlier contracts. Valid raw bytes,
text and variant hashes, physical provenance and idempotent imports are unchanged.
The public pinned ContentItem model informs this narrow shape check, not a claim
of universal producer-schema validation or complete replay compatibility.

The full suite passes 677 tests; publication audit and byte-manifest checks cover
146 files. Existing archives and saved proposals are not retroactively repaired or
invalidated. No actual corpus, model call, source rewriting, remote mutation or
merge is added. Exact-commit four-job CI is checked separately after push.

### 2026-11-04: first-run branch, launcher and SQLite checks

Read-only repository inspection confirmed that main exposed only normalized ingest,
search and stats, while the workflow guides described the development branch.
An independent synthetic first-run reproduction also found a valid Python/FTS5
installation with only python3 on PATH: the literal documented python command
failed before the demo, while launcher substitution succeeded. Installation guidance
now selects the exact workflow branch, explains source ZIP versus conversation ZIP,
chooses one launcher consistently and links official Python/SQLite documentation.
The normalized quickstart uses a new portable scratch directory instead of /tmp.

Fourteen independent tests cover the new standalone runtime_check.py and documented
entry arguments. The check verifies the Python compatibility minimum, then imports
SQLite and performs a synthetic create/insert/MATCH round trip using only :memory:.
Simulated old versions return before SQLite import; missing modules, SQLite failures
at connect/create/insert/query/fetch/close and unexpected results return fixed codes.
Connections close on failure, no disk-DB fallback or extension loading is attempted,
and diagnostics do not expose underlying paths or error text. Non-SQLite programming
errors still propagate rather than being silently classified as compatibility errors.

Tests cover ASCII JSON, status/usage exit codes, temporary working directories and
an audit hook that rejects disk/network/process/extension operations during the
probe after standard-library imports are preloaded. This is not a claim that Python
startup/module loading performs no filesystem reads. The real memory probe also
passed with a second available interpreter; the complete suite ran with the
primary interpreter, not every possible runtime.

The explicit clone branch/repository are checked as documentation, without a network
clone or OS/Python installation. Documented checker/help and normalized mkdir/ingest/
search/stats arguments run with synthetic files and preserved source bytes. The
walkthroughs now state that tests substitute the test interpreter and control UTF-8
output, rather than certifying literal launcher availability or every shell's
redirection behavior. Runtime READY likewise does not certify checkout authenticity,
filesystem permissions, source compatibility, shell encoding or full application
support. The minimum Python version is not a security-lifecycle recommendation.

The complete suite passes 691 tests; publication audit and byte-manifest checks cover
149 files. No actual exports, account collection, model transmission, installation,
settings changes, remote rename or merge occur. Exact-commit Ubuntu/Windows Python
3.10/3.12 CI is checked separately after push.

### 2026-11-04: portable in-memory audit assertion

CI for 1fab1fc found one test-only portability assumption: both Ubuntu and Windows
Python 3.10 reported sqlite3.connect audit arguments as (b':memory:',), while the
test accepted only the string tuple. Both Python 3.12 jobs passed. The production
runtime checker still passed its string :memory: argument and made no file database;
the failed commit is not recorded as four-platform CI success.

The audit test now accepts exactly one built-in str or bytes :memory: argument.
Its child-process self-check exercises both forms and rejects string/bytes file
names, memory-style URIs, empty or extra arguments, null, lists, bytearrays and
memoryviews. Disk, network, process and extension audit guards remain unchanged.
No production code or installation behavior changes, no arbitrary decoding is
introduced, and the broad guard is not removed to make CI pass.

The full local suite passes 691 tests after the correction; final focused and
manifest checks also pass. Publication audit and manifest cover the same 149 files.
All four jobs for the new exact commit are checked separately after publication.

### 2026-11-04: native no-overwrite title documents

An independent synthetic reproduction confirmed that shell redirection to an input
proposal truncates that file before the CLI can reject it, and a simulated UTF-16
shell-produced document fails the existing UTF-8 reader. Supported read-only title
commands now accept an explicit --output path for a new UTF-8 JSON file. Generation,
validation and serialization happen before a private same-directory staged write;
flush, fsync and close precede atomic no-overwrite hard-link publication. There is
no replacement fallback. Existing files, directories and symlinks are refused.

The saved proposal, preview or queue retains the original document shape. Stdout
becomes an ASCII-safe receipt with byte count, SHA-256 and staging cleanup status,
without deliberately printing title/body text, source/conversation IDs or the output
path. The receipt is not a reviewed document or approval. Default stdout behavior,
archive read-only behavior, explicit apply and stale-preview checks remain intact.
Only the six documented unified read-only title commands and their existing
standalone equivalents get this option. Mutation commands and provider adapters do
not; prepare-web-export keeps its distinct existing --output behavior.

Seventeen independent synthetic tests cover serialization, Unicode/newline/hash,
POSIX staging permissions, existing and aliased input/database destinations, missing
parents, competing publishers, write/flush/fsync/link and short-write failures,
closed-stage publication, cleanup outcomes, invalid input and missing archives,
all supported CLI forms, queue selection, selected evidence, explicit apply and
stale rejection. One additional test exercises Unicode, spaces, # and % in native
output paths under an ASCII CLI, same-target refusal and separate explicit apply.
The two primary walkthrough suites now test CLI-created files and receipt hashes
rather than constructing equivalent files from captured stdout. They retain exact
argument validation with the available test interpreter, not shell certification.

If staging cleanup fails after publication, the complete output is reported SAVED
with a leftover basename; pre-publication failures remain errors. A crash can leave
staging/output files. Hard-link support and a controlled private parent directory
are required. These tests do not establish hostile-directory resistance, universal
filesystem support, encryption or full power-loss durability. Shell redirection can
still truncate a file before the program runs if combined with these commands.

The final complete local suite passes 709 tests. Focused native-output, walkthrough
and runtime checks pass 39 tests. Publication audit and byte-manifest checks cover
152 public files. All fixtures remain synthetic; no real session, account access,
model transmission, remote rename or merge occurs. Exact-commit Ubuntu/Windows
Python 3.10/3.12 CI is checked separately after push.

### 2026-11-04: portable staging-directory identity test

CI for 66f4bb5 passed both Ubuntu jobs but failed one test assertion on both Windows
3.10 and 3.12. The temporary directory used a Windows 8.3 parent alias while the
writer resolved it to the full spelling. The test compared path text, not directory
identity. The real native-file and web/local walkthrough tests passed; no production
writer change is needed or made for this failure. That commit is not claimed to have
four-platform CI success.

The test now verifies that both staging and output parents identify the requested
filesystem directory and that the destination basename remains exact. It also runs
through an existing nested-directory/.. alias on every platform, checks saved
content and retains the closed-stage, private POSIX mode, no-replace/no-rename and
staging-cleanup assertions. The correction does not skip Windows or weaken the
same-directory requirement.

All 709 local tests pass again, including 18 native-output tests; final publication
and manifest checks cover 152 files. Exact-commit four-platform CI is rechecked after
publishing this test-only correction. No real data or additional runtime behavior
is introduced.

### 2026-11-04: editor-saved title document compatibility

Synthetic reproduction showed that adding a single initial UTF-8 BOM to an otherwise
valid title proposal made both the single-document and supplied-candidate readers
reject it. Title proposal/preview reading, supplied proposal reading and saved queues
for explicit review-state decisions now use the existing strict UTF-8 source decoder.
Only one signature at the beginning is consumed. Embedded U+FEFF string data remains
exact; files are not rewritten, and native output still writes UTF-8 without a BOM.

Fourteen synthetic tests exercise both encodings with Unicode, leading JSON
whitespace and embedded signature characters; repeated/noninitial signatures,
UTF-16/UTF-32, invalid UTF-8, duplicate keys, unpaired surrogates and excessive
nesting remain failures. The supplied-file cumulative byte limit counts original
BOM bytes, including at its exact boundary. Shared in-memory JSON decoding and the
provider/consent/transfer/title-plan file contracts are not broadened.

The web-branch and typed local-attribution journeys generate native proposal files,
simulate editor-added signatures, preview private evidence without archive changes,
then explicitly apply and search. Standalone preview/apply parity, mixed supplied
queues, explicit deferred state, stale state/revision/content rejection, output
absence on failure, receipt misuse and original file preservation are covered.
The supplied-candidate guide now uses actual native --output files; its command
test validates saved contents and receipt hashes rather than writing captured stdout.

A related reproduction found that a JSON queue could decode successfully but exceed
recursion capacity while detaching a selected item. Selected queue items/proposals
and supplied candidates now turn deepcopy RecursionError into a fixed ValueError,
without private exception text or traceback. Tests cover the clean CLI failure
with and without a BOM and both detached selection stages with injected errors.
There is no universal numeric nesting promise or increase to interpreter limits.

The complete local suite passes 723 tests; the final focused encoding, supplied
queue and native-output suites pass 49 tests. Publication audit and byte manifest
cover 153 files. The new tests were authored in this task, not independently
reviewed. No real exports, account collection, model transmission, original-session
rename or merge occurs. Four-platform exact-commit CI is verified after publication.

### 2026-11-04: parse local source snapshots directly

A synthetic inspection reproduced one full source-sized temporary write even though
normalization already held the immutable input bytes. A malformed record then
reported a removed temporary session.jsonl path instead of the selected filename.
Local/local-codex normalization now passes the existing snapshot directly to a
JSONL byte parser. It does not create that extra source copy or depend on a writable
temporary directory for inspection, export inventory, conflict checking or scoped
local title evidence. Record diagnostics use the source basename and physical line.

The existing file-based parse_artifact routes remain supported, including SQLite
integrity checking and path-based diagnostics. New parse_jsonl_bytes accepts immutable
bytes and a nonempty source-relative text label; the label is not opened or resolved.
Both entry points share the unchanged record/content extraction logic. Metadata-only
utility policies, raw record order, profile differences and all admission guards
remain in force; this is not format discovery or broader extraction.

Fourteen new synthetic tests cover byte/file parity and explicit expected message
IDs, physical lines, timestamp zero, text/variant hashes, BOM/mixed newlines and
Unicode content. They exercise metadata-only labels, invalid byte/profile/label
arguments, malformed records, unchanged SQLite routes, original-path versus label
diagnostics, and checks with temporary staging and filesystem entry points blocked.
This is code-path regression coverage, not an OS sandbox or a claim about all Python
startup/import and SQLite filesystem activity.

Workflow tests confirm one source read even when the file is deliberately replaced
after that read; hashes, selection and fallback IDs still refer to the same captured
bytes. Invalid input fails before database/staging work. Import still uses exactly
one existing normalized-JSONL staging directory, preserves original provenance and
is idempotent. Retained-turn and source-attributed title generation work with source
staging disabled and still require a separate checked apply. Source files remain
unchanged; web normalization remains separate.

The final complete local suite passes 737 tests, and the adjacent parser/import/
inventory/title suite passes 122 tests. Publication audit and byte manifest cover
154 files. The new tests were authored in this task, not independently reviewed.
Full-file memory use and import's normalized staging are explicitly retained. No
real sessions, account discovery, model transmission, remote title change or merge
occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked after push.

### 2026-11-04: ingest normalized export bytes without staging

The remaining export-import handoff previously wrote normalized JSONL to a temporary
file only for the archive writer to read it again. Export adapters now use an
immutable byte-ingestion entry point shared with the existing file API. They no
longer require Python temporary-file creation for that handoff. SQLite archive,
journal and internal temporary-storage behavior is unchanged, and the archive
location must still be writable. This is not a disk-free import or memory bound.

The normalized bytes deliberately use the same UTF-8 text writer and native newline
translation as the former file stage. Tests construct a real file using the old
serialization and compare bytes, receipts, logical archive/FTS/provenance tables and
search results with the new import for web, legacy local and typed local, both whole
and selected input. This runs on each CI platform rather than assuming Unix LF or
silently changing Windows normalized artifact hashes. Original-export hashes remain
separate from derived normalized artifact hashes; the documentation clarifies both.

Fourteen new synthetic tests cover raw file/byte parity including BOM and mixed
newlines, one source read, invalid/mutable raw input, exact source labels, empty and
identical reimports, incoming contradictions before database creation, archive
conflict rollback, provenance-trigger rollback, additive original occurrences and
preservation of first accepted message provenance. Source labels now explicitly
require non-whitespace text, rejecting nontext Python inputs without coercion or
uncaught attribute errors. No accepted text label is normalized or trimmed.

Three-format import/preview/explicit-apply workflows and actual CLI dispatch run
with Python temporary-file factories denied. Tests block input-file writes while
allowing the intended SQLite work. Existing export-hash guards were moved to the
actual ingest_bytes boundary, not removed or left patching an unused function.
The architecture guide also now describes current additive provenance and the
separate schema/data-transaction boundary instead of obsolete initial-CLI limits.

The final full local suite passes 751 tests; 133 focused import/hash/provenance/
parser/title tests and final manifest checks pass. Publication audit and byte
manifest cover 155 files. New tests were authored in this task, not independently
reviewed. No real exports, account collection, model transmission, remote rename
or merge occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked after push.

### 2026-11-04: reject invalid source labels before source or archive access

An independent synthetic reproduction found that a source label containing a
surrogate code point passed the nonempty-text check, opened SQLite and created the
archive schema before insertion failed with a Unicode encoding error. Source labels
come from Python/command arguments rather than decoded JSON, so the existing JSON
Unicode check did not cover them. This could leave an empty database after a failed
import, especially for Python callers or Unix arguments decoded from invalid bytes.

The shared source-label check now rejects surrogate code points with a fixed,
content-free ValueError. Normalized file/byte ingestion, all three export-import
formats and read-only import diagnostics validate before source reads or SQLite
access. Invalid source labels also fail before other source parsing/selection
checks; there is no silent replacement, repair or guessed source identity.

Eight independently authored synthetic tests cover high/low and adjacent surrogate
values, empty/nontext labels, malformed byte payload precedence, new/existing
archives and guards denying all source reads and SQLite connections. Korean, emoji,
combining sequences, padding and previously accepted embedded-NUL labels retain
exact identities, with idempotent imports and unchanged sources. Distinct Unicode
normalizations and padded labels remain distinct. A Unicode import/proposal/preview
roundtrip verifies that only explicit apply creates a searchable Korean display
title, and stale reapply still fails. The actual invalid-byte argv regression runs
five unified/standalone commands under UTF-8 mode on POSIX and is explicitly skipped
on Windows, whose argv does not represent that POSIX input form. The API validation
and valid-Unicode workflows run on both platforms.

The full local suite passes 759 tests; the focused import/label/CLI suite passes
60 tests, and the final source-label module passes all eight. Publication audit
and byte manifest cover 156 public files. The export-inventory and input-scope
guides also remove two obsolete references to temporary JSONL copies. This does not
make all SQLite/schema or filesystem failures atomic, remove older empty databases,
or change title review, source content, Unicode spelling or valid import hashes.
No real sessions, automatic discovery, external model calls, remote title changes
or merge occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked after push.

### 2026-11-04: find export titles and IDs before choosing an import

A synthetic 1,050-conversation web export demonstrated a first-use gap: a known
late-sorted title required 21 default metadata pages, or two maximum-size pages,
with the full source parsed again on each call. The inventory now accepts optional
--contains text in both CLIs and a keyword-only Python argument, filtering existing
web titles or exact session/conversation IDs before pagination. It still creates
no database, prints no message-body fields and imports nothing automatically.

Matching is one case-folded literal substring within a single metadata field, not
split-term, regex, wildcard, fuzzy or body search. Local formats match IDs only.
Optional --canonical-unicode uses the existing canonical search-copy function and
records the runtime Unicode version. Original spelling, distinct composed/decomposed
IDs, source bytes and hashes remain unchanged. The filter requires valid Unicode,
non-whitespace text up to 256 code points; meaningful spaces are preserved. Invalid
options reject before reading. Omitting the filter preserves existing output.

Whole-file parsing, grouping and validation precede filtering. An alternate title
matching a repeated web ID retains all that ID's titles/counts and ambiguity
blocker; media-only records keep their no-text blocker. Malformed unmatched content
still fails, including zero-result searches. Top-level totals and coverage retain
whole-file meanings. The optional filter summary supplies matching totals, and
next_offset indexes only the matching ID-sorted list. Operators must keep the same
filter/mode and expected source hash across pages; no cursor or automatic lease is
added. Filtering does not reduce full-file read/extraction scope or bound memory.
Queries and returned metadata can be private.

Eighteen independently authored tests cover the late 1,050th match, sparse/empty
pages, exact counts, literal punctuation/spaces, casefold expansions, canonical
Korean/accented spelling, separate canonical-equivalent IDs, local metadata/body
exclusions, duplicate/empty-text blockers, invalid unmatched data, option validation,
one source read, original hash checks and no database calls. Tests execute the
three exact documented filter commands, compare both CLIs with the API, and follow
all three formats through filtered discovery, exact-ID/hash-bound selected import,
preview, explicit title apply and title search. A prepublication regression caught
next_offset still using the whole-file count; it was corrected to the matching
count and the final tests pass.

The final full local suite passes 777 tests in 110.638 seconds; 78 focused inventory,
hash, selected-import, Unicode and CLI tests pass. Publication audit and byte manifest
cover 157 public files. No real conversation data, automatic collection, external
model call, remote rename or merge occurs. Exact-commit Ubuntu/Windows Python
3.10/3.12 CI is checked after push.

### 2026-11-04: select a useful message without leaving verified title scope

Synthetic web and retained-local examples reproduced a title-quality gap: a generic
first non-greeting request kept supplying the excerpt even when a later verified
user request named the actual topic. Raw --message selection could choose it, but
without the original branch/replay verification contract. Both scoped suggestion
commands now accept an optional exact archived --message ID; Python APIs append
message_id=None without changing existing positional arguments or default output.

The full original branch/replay evidence verification runs before narrowing the
excerpt candidate. Exactly one in-scope user row is required. Off-branch, rolled-back,
non-user, missing and ambiguous choices fail without fallback; an unusable prefix
still fails, while an explicitly chosen greeting keeps its existing advisory.
Malformed selector shapes reject before source/archive access. Entire branch-path
verification and all raw replay source-occurrence checks remain, including removed
turns. Whole raw-conversation fingerprints and normal scope context are retained.
The added evidence_selection is descriptive/unsigned, not approval or authenticity.

Eighteen independent synthetic tests cover later-request quality, default/None
parity, exact scope and roles, pre-I/O validation, no fallback, greeting/Unicode/
80-code-point behavior, ambiguous rows, other-scope content/provenance failures,
whole-fingerprint stale apply, one source read and byte-for-byte read-only checks.
ID-less replay tests select the original archive ID after renaming identical source
bytes and reject a projection ID as an archive selector. CLI tests compare unified
and standalone entry points, native saved proposals/previews, explicit apply/search,
stale reapply and no output file after a rejected choice.

A new invented 17-record local fixture has six raw messages, two retained turns and
one removed turn. The documentation's 14 exact commands (including directory
creation) are executed with private temporary-path substitution after tokenization.
Tests inspect actual UTF-8 documents and receipt hashes, require both conversations
to remain at revision zero until their own explicit apply, preserve source/raw
snapshots, and verify retained/rollback counts and final title search. The test
records returned global title-history revision IDs rather than assuming each
conversation's first write receives revision 1. The existing raw-selection guide
still executes its original seven commands; its section boundary now stops at the
next level-two heading.

The final complete local suite passes 795 tests in 163.363 seconds. The focused
scoped/raw/adapter/attribution/output/CLI suite passes 116 tests, and the independent
documentation bundle passes 40. Publication audit and byte manifest cover 159 public
files. The 80-code-point cap can still cut graphemes. Source-attributed generation,
provider preparation, narrow replay grammar, and separate preview/apply checks are
unchanged. Apply checks the archive snapshot, not later source/current_node changes.
No real sessions, model transmission, automatic semantic ranking, remote rename or
merge occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked after push.

### 2026-11-04: close test-owned SQLite handles before cleanup

The first scoped-message commit's CI run 41819049829 passed Ubuntu Python 3.10/3.12
and Windows Python 3.10, but Windows Python 3.12 failed four new test cleanups with
WinError 32. The mutation fixtures used SQLite's transaction context manager, which
commits/rolls back without closing the connection. Garbage-collection timing had
hidden the open handles locally; this was not a successful four-platform run.

All four test-owned mutation contexts now explicitly close connections while
retaining their transaction contexts and every content/provenance/staleness
assertion. A deterministic nineteenth module test holds strong references to
connections opened by those four cases, checks that each is closed before temporary
cleanup, and closes handles before cleanup even if a regression is detected. Nested cleanup
success is asserted rather than silently ignored.
It does not rely on garbage collection, sleeps, skipped assertions or ignored
cleanup errors. An independent in-memory reversion probe restored the old leaking
contexts and produced the expected four closure failures with zero cleanup errors.

Production parsing, selection, title review and output behavior are unchanged.
The final complete local suite passes 796 tests in 143.672 seconds; the scoped and
documentation bundle passes 41. The public audit and manifest still cover 159 files.
A new exact-commit four-platform CI run is checked after this correction is pushed;
the failed earlier run is not reclassified as successful.

### 2026-11-04: bind ZIP inventory pages to the inspected archive

A synthetic three-candidate ZIP replacement reproduced duplicate pagination:
page one returned conversations-001.json, then a replacement with a different first
entry and the same candidate count returned conversations-001.json again at offset
one. Each unpinned response exposed its own hash, but the inventory had no option
to enforce equality. Explicit preparation already rejected a changed archive.

The optional inspect-web-zip --expected-archive-sha256 and fourth Python API
argument now bind later candidate pages to the first bounded whole-ZIP snapshot.
Inspection and preparation share strict lowercase digest validation and mismatch
checking. Invalid syntax fails before file I/O; a mismatch fails before ZIP metadata
parsing, including requests beyond the last candidate. One read supplies both the
metadata and returned digest. Existing calls, explicit None and matching hashes
produce the same result shape. Unpinned behavior and all existing bounds remain.

Nine independent synthetic tests cover stable pages, replacement/reordering,
unrelated entries and archive comments, malformed digest types and text, invalid
ZIP error ordering, one-read source replacement, no decompression/database/output
writes, limits, and CLI failures with no JSON result. Exact documented pagination
commands are executed after tokenization and temporary-path substitution. A pinned
two-part workflow imports 12 invented web conversations and 12 local sessions,
saves separate UTF-8 queue/preview files with verified receipt hashes, stays at
revision zero until explicit apply, then finds the selected Unicode title. Original
source bytes, archived messages/provenance and the saved queue remain unchanged.
Successful inventory ignores both absent and opaque existing database paths.

The complete final local suite passes 805 tests in 127.021 seconds; the focused ZIP,
export-hash, inventory and first-run bundle passes 64 tests. The public audit and
byte manifest cover 160 files. The first-page digest must also be used for explicit
preparation; a mismatch requires restarting inventory rather than mixing pages.
Hash equality is not authentication, content validation, part completeness or an
atomic multi-part import. No real sessions, model transmission, automatic member
selection, remote rename or merge occurs. Exact-commit Ubuntu/Windows Python
3.10/3.12 CI is checked after push.

### 2026-11-04: reject malformed web content tags before partial extraction

A synthetic greeting followed by a substantive text-field request with
content_type: ["code"] previously imported only the greeting and could suggest
"Hello!" as the title. Malformed tags paired with string parts could also import
without warnings. Present null, boolean, numeric, array, object, empty and
whitespace-only tags now reject the whole input with a fixed field-only diagnostic.
The shared web extractor performs this check before returning parsed output or
accessing the archive. It does not guess, trim or repair a tag.

Missing tags retain the existing string-parts compatibility path. Unknown nonblank
strings, exact code/execution_output behavior, raw text, omissions and provenance
remain unchanged. Full-file validation still includes unselected conversations and
branch nodes; ZIP preparation rejects malformed selected web JSON before staging.
Existing partial archives, archive-only suggestions, saved proposals and title
history are not retroactively repaired or invalidated.

Eleven independent synthetic tests cover all malformed tag categories and four
supported roles, every shared whole-file reader, off-path nodes, no database
connection/creation, unchanged existing archive/source bytes, and fixed ASCII CLI
errors without text leakage, traceback or partial JSON. They preserve absent,
unknown and padded-tag behavior, exact Unicode string-parts text/provenance, and
code/output shape rejection. A corrected synthetic source imports deliberately,
generates a substantive native UTF-8 proposal, stays read-only through preview,
then explicitly applies the title and finds the conversation. The test checks the
positive applied revision and exact display title, unchanged original title/body/
provenance, and idempotent reimport. Malformed input cannot save a partial branch
proposal; ZIP rejection occurs before output staging.

The final complete local suite passes 816 tests in 100.362 seconds. The focused
web/branch/ZIP/typed-local bundle passes 64 tests, and the independent affected
suite passes 139. The publication audit and byte manifest cover 161 public files.
This is a narrow supported-input contract, not proof of a universal or stable
vendor export schema. No real sessions, model transmission, automatic repair,
remote title changes or merge occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12
CI is checked after push.

### 2026-11-04: compare CLI diagnostics across native line endings

The first web-content-tag commit's CI run 41824981222 passed both Ubuntu jobs but
failed Windows Python 3.10 and 3.12. Each Windows run reported two assertion
failures among 816 tests: the new byte-captured stderr checks compared native CRLF
against a literal LF. Production rejected the malformed input with the correct
fixed diagnostic; the four-platform run was not successful.

The two test assertions now normalize only CRLF to LF before requiring the exact
ASCII diagnostic and one final newline. Extra content, other changed whitespace,
non-ASCII payloads, traceback, stdout output, database writes and proposal-file
creation remain failures. No production behavior or diagnostic is changed.

A deterministic twelfth module test executes the two original failure workflows
under an idempotent CRLF stderr adapter. It runs five actual CLI failures, retains
stdout and return codes, and checks nested temporary-resource cleanup explicitly.
Before the two assertion changes, this test reproduced both failures on a second
platform. The corrected module passes 12 tests; the final complete suite passes 817
tests in 103.746 seconds. Public audit and manifest still cover 161 files. A new
exact-commit four-platform CI run is required after this correction is pushed;
the earlier failed run remains recorded as failed.

### 2026-11-04: discover a session by remembered message text before import

Two synthetic local sessions with opaque IDs reproduced the next usability gap:
metadata-only --contains could not find a remembered phrase present in extracted
message text, and archive find required importing first. list-export now offers
explicit --text-contains in both CLIs and the keyword-only Python API. It is
mutually exclusive with metadata --contains, which retains its existing behavior.

Text mode matches one literal case-folded substring inside one normalized message,
with optional existing canonical-Unicode matching. It never joins separate messages
or searches source metadata as body text. Returned identities add matched_messages
and sorted matched_role_counts; each matching normalized occurrence counts once,
not each repeated substring. Full identity metadata and selection blockers remain.
The filter reports global matching counts while pagination uses matching-ID offsets.
Default and metadata-filter output matched the previous published implementation
exactly in twelve independent comparisons across all three formats.

The output contains no extracted body/excerpt/message-ID/locator fields, but the
echoed query can itself reveal message text. Matching includes all supported
extracted roles, alternate web branches and raw local rollback/harness text. It is
not a user-intent, active-history, title-quality, privacy or completeness guarantee.
The chosen parser's extraction rules, whole-file validation, original hash lease,
one-read snapshot and lack of database access remain unchanged. No automatic
selection or import occurs; selected import still keeps the whole chosen identity.

Twenty independent synthetic tests cover opaque IDs, role/occurrence counts,
literal punctuation and whitespace, Unicode expansion and canonical matching,
legacy/typed parser differences, supported web text fields, omissions, duplicate
web-ID ambiguity, off-path/rollback text, sparse matches beyond the first 1000 IDs,
invalid arguments before reads, malformed unmatched content, no-body result fields,
source/hash integrity and both CLI entry points. All three formats complete
hash-bound selected import, native UTF-8 proposal/preview and explicit title apply.

The documentation's three discovery commands and eight walkthrough commands run
exactly, with tokenization before platform-path substitution. The walkthrough
finds one user match among six raw local messages, imports the checked full hash,
selects the retained focus-user message, verifies saved UTF-8 receipt hashes, and
keeps title revision zero until explicit apply. Original messages, provenance,
occurrence records and source bytes remain unchanged. Test SQLite handles close
explicitly and subprocess text mode handles native line endings.

The final full suite passes 837 tests in 141.148 seconds; the focused inventory,
source-hash, first-run and scoped-title bundle passes 96. Public audit and byte
manifest cover 162 files. No real data, model transmission, source modification,
remote title mutation or merge occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12
CI is checked after push.

### 2026-11-04: bridge omitted search samples to reviewed user evidence

A read-only synthetic audit found a navigation gap, not a missing parser or an
inaccessible-message defect: find could show three assistant samples and a null
conversation cursor while a later matching user request remained unsampled.
Existing scoped show pages reached that request. A new filtering flag was not
needed; the guide now connects existing paging to exact user-message title choice.

The new invented local fixture has 68 records and 67 messages: one generic opening
user request, 65 assistant status notes, and a final substantive user request.
The query cobalt orchard matches 66 bodies, while the three retained samples are
assistant messages. Query-term coverage is complete even though useful user evidence
is not sampled. The guide distinguishes conversation cursors from message pages,
explains that increasing find's conversation limit does not increase body samples,
and links from search excerpts, pagination, title-review hints and the README.

Five synthetic regression tests cover fixture structure, equivalent web/local
flows, exact documentation commands, fresh later-page behavior and valid guide
links. Four existing show pages return 20/20/20/7 messages and reach focus-user.
Assistant evidence selection rejects; default wording remains the generic opener;
explicit focus-user selection produces the substantive excerpt. The eleven exact
guide commands execute after tokenization and temporary-path substitution, verify
native UTF-8 proposal/preview receipts and byte hashes, keep revision zero and
archive bytes unchanged until explicit apply, then verify the new display title.
Original message, artifact and provenance rows and source bytes remain unchanged.
SQLite test handles close explicitly and subprocess output uses text mode.

The guide labels raw branch/rollback/export-version scope, full-message privacy,
message-count versus byte bounds, and fresh snapshots across offset pages. The
fixture has no completed-turn replay grammar; it demonstrates raw paging only.
Production parsing, search sampling, pagination and title behavior are unchanged.
The final complete suite passes 842 tests in 160.432 seconds; the focused sample,
cursor and title-selection bundle passes 61. Public audit and byte manifest cover
165 files. No real source data, model transmission, automatic approval, remote title
mutation or merge occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked
after push.

### 2026-11-04: select meaningful source-attributed occurrences

A synthetic audit reproduced a generic first user-labeled request hiding a later
specific request in source-attributed title generation. Raw, branch and replay
generators already allowed explicit message selection, but the attributed path did
not. Repeated identical raw messages can also label different content positions as
user text, so an archive ID alone does not always identify the intended evidence.

The attributed API and both CLI entry points now accept an optional exact archived
message ID and physical origin locator. A locator requires a message ID and strict
positive ASCII line:N syntax. Argument-shape failures precede source/database I/O.
Selection occurs only after existing attribution and full selected-conversation
source/archive verification. Exactly one eligible occurrence must match; missing,
non-user, unattributed, empty and ambiguous choices reject without fallback. Equal
raw text or equal candidate excerpts do not resolve duplicate occurrences.

The chosen evidence retains the complete raw-conversation fingerprint, original
file hash, extraction warnings and full user-role coverage, while evidence parts
narrow to its physical occurrence. Default output and behavior remain unchanged;
a direct comparison with the previously published standalone command also matched.
The existing deterministic 80-code-point excerpt rules, unsigned metadata limits,
raw preview text and explicit checked apply remain unchanged. Source labels are not
verified human authorship, and no retained-history reconstruction is added.

Twenty-six independently authored synthetic tests cover exact IDs, early argument
validation, duplicated positional labels, absent/noneligible/unusable selections,
BOM/blank/mixed-newline physical locators, renamed ID-less source association,
malformed other attribution, changed source bytes, missing or altered nonselected
archive content/provenance, stale content/title previews and fixed non-leaking
errors. Both CLI entry points match the API and save native UTF-8 output.

The new fixture has six records, five message occurrences and four archived
messages. Its ten documented commands select a meaningful later request, save and
review it, then apply explicitly. A second repeated-occurrence proposal is previewed
but not applied. Tests verify revision zero before the first apply, revision one
afterward, exact saved receipt hashes, unchanged source bytes and immutable raw
message/provenance rows. Test SQLite connections close explicitly, CLI text mode
handles native newlines, and documentation tokens are split before substituting
platform paths. The guide warns that preview evidence still shows raw text and
that attribution fields are not independently authenticated at apply time.

The full final suite passes 868 tests in 130.635 seconds; the focused attribution,
scoped selection, native output, review evidence and offline adapter bundle passes
122 tests. Public audit and byte manifest cover 168 files. No actual personal data,
model transmission, source rewrite, automatic approval, live title mutation or merge
occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked after push.

### 2026-11-04: respect metadata-only admission in export inventory

A synthetic audit reproduced a parser/inventory disagreement. The exact basename
session_index.jsonl is intentionally validated as index metadata, but list-export
then reparsed additional type:session_meta fields as rollout envelopes. A missing
payload could fail with KeyError; a valid extra payload could instead invent a
conversation ID unrelated to the validated index entry.

Inventory now skips rollout interpretation when the parser already admitted the
input as accepted_metadata_only. It preserves the established zero-conversation
inventory rather than exposing index IDs/titles or inferring messages. Whole-file
validation, byte hashes, filtering, warnings and original source bytes remain
unchanged. Genuine zero-message rollouts still report their actual session ID and
NO_EXTRACTED_TEXT because their admission status is accepted_zero_message.

Sixteen independently authored synthetic tests cover both local formats, missing
and malformed extra payloads, misleading rollout/body fields, metadata/text filters,
canonical matching, malformed required fields and duplicate JSON keys, hash leases,
exactly one source read without database access, empty/BOM/blank indexes, exact
basename behavior, ordinary zero-message rollouts and both CLI entry points.
Whitespace-only required index strings retain the existing nonempty-string contract.
A renamed hybrid with valid rollout fields can legitimately have a different parser
interpretation; a renamed plain or empty index still rejects. In-memory restoration
of the old inventory branch produced 38 failing and 34 erroring subtests, confirming
that the tests detect the regression without modifying production for that check.

Separate tests and documentation preserve the existing zero-record import policy:
it can create schema and an empty normalized-input artifact, but does not persist
index IDs, names, timestamps or original metadata. The coverage receipt still
contains the original hash. This is not a metadata backup, new index inventory,
automatic session collection, title inference or change to import admission.

The final full suite passes 884 tests in 221.931 seconds; the focused metadata,
inventory/filter, byte-snapshot and selected-import bundle passes 95. Public audit
and byte manifest cover 169 files. All data is synthetic, SQLite test handles close
explicitly, and CLI tests normalize platform newlines via text mode. No real data,
model transmission, source rewrite, remote title mutation or merge occurs.
Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked after push.

### 2026-11-04: reject damaged local tags before identity assignment

An independent synthetic audit reproduced identity contamination: a valid session A
and message followed by a record with malformed present type and an apparent B
payload, then a valid message, caused both messages to be imported under A. The
damaged payload does not establish a valid B boundary, so silently skipping it is
not a sound basis for continuing identity assignment. A damaged response tag could
also drop the substantive request and leave only an earlier generic title candidate.

After metadata-only utility admission, both local parser profiles now reject a
present top-level type unless it is a nonblank string. Errors use a fixed label
and physical line, without tag/payload/text values. This deliberately narrows an
older compatibility case that accepted an object tag as unknown. Its old coverage
test now checks still-supported missing-tag behavior instead; malformed tags have
dedicated failure regressions. Missing tags, nonblank unknown strings and exact
untrimmed tag semantics remain unchanged, so this is not a complete boundary or
producer-schema validator. The pinned public Codex RolloutItemWire definition in
history/src/rollout_payload.rs uses a string-tagged enum; the guide links the exact
verified revision and distinguishes Recap's looser compatibility policy.

Fifteen new synthetic tests exercise both profiles, repeated malformed boundaries,
malformed response tags, early database avoidance, unchanged existing archives and
title revisions, selected/unmatched content, direct byte/path parsers, BOM/blank
physical lines and LF/CRLF/CR handling, literal missing/unknown tags, valid multiple
sessions, metadata-only index/agent-raw/SQLite exceptions, hash-check precedence,
source-backed title rejection and fourteen CLI failure paths with no partial JSON,
new database or saved proposal. All SQLite handles close explicitly and subprocess
text mode handles native line endings. An in-memory load of the previous parser
produced 40 failing subtests across three methods; production files were not swapped.

Independent review found no blocking code issue and independently passed 43 tests.
The focused local validation, byte parsing and metadata-inventory bundle passes 66;
the final full suite passes 899 tests in 187.398 seconds. Public audit and byte
manifest cover 170 files. Documentation explicitly identifies the changed malformed
input contract, retained unknown-tag caveats and lack of retrospective repair.
Existing archives and previously saved titles are not automatically rescanned or
moved, and the stricter replay path can reject under its own earlier grammar.

No actual personal data, model transmission, source rewriting, guessed boundary,
remote title mutation or merge occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12
CI is checked after push.

### 2026-11-04: save offline adapter requests and responses natively

A workflow audit identified a deliberate capability gap rather than a parser
regression: the separate provider-neutral adapter's prepare and complete-response
commands still required shell redirection, although the downstream title workflow
already supported native no-overwrite UTF-8 documents. The saved-response guide
therefore retained shell truncation and Windows encoding hazards on its first steps.

Those two offline/read-only commands now accept --output. Preparation saves the
same logical request envelope with a request-kind receipt; completion saves the
same validated proposal with a proposal-kind receipt. The shared writer retains
same-directory closed/synced staging, atomic hard-link publication, existing-target
refusal and truthful SAVED status when post-publication staging cleanup fails.
Request receipts explicitly deny transmission permission and contain no payload,
source identity or destination path. Older receipt kinds are unchanged. Native
save failures return fixed OUTPUT_FAILED, including the RuntimeError raised by
looping output parents on supported Python versions, without private diagnostics.

The seven-command saved-response walkthrough now uses native saving for request,
proposal and preview. Its existing regression executes the exact commands, verifies
all three receipt byte hashes/kinds, forbids shell redirection, keeps the archive
unchanged until explicit apply and checks the final searchable display title.
Documentation distinguishes saved-file hashes from canonical payload hashes and
retains existing input-encoding, source freshness, evidence and consent boundaries.
The adapter's request/response/consent readers have not gained BOM tolerance.

Fifteen independently authored synthetic tests cover fresh-archive raw, web-branch,
local-replay and local-attributed flows; local/mock preparation parity; private
Unicode files and ASCII-safe receipts; protected database/export/request/response
paths and aliases; missing or looping parents; invalid/stale input; receipt misuse;
source read-once behavior; no generation or transport; link/fsync failures; and
post-publication cleanup status. SQLite handles close explicitly and Windows
canonical-parent comparisons use samefile plus filename. Independent production
review found no substantive blocker and identified the now-covered parent-loop
error refinement. Four no-option preparation/completion cases also match the prior
published stdout byte-for-byte, with no archive changes.

The final full suite passes 914 tests in 287.426 seconds. The focused adapter,
completion, scoped evidence and document-output bundle passes 99 tests. Public audit
and byte manifest cover 171 files. External generate remains disabled/unconfigured,
does not accept --output, and transfer simulation remains unchanged. No actual user
data, model execution/transmission, automatic title approval, remote mutation or
merge occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked after push.

### 2026-11-04: accept editor-saved UTF-8 adapter input files

A remaining file-workflow gap was explicit rather than a regression: exports and
saved title/review documents accepted one initial UTF-8 signature, but the separate
adapter rejected editor-saved prepared requests, supplied responses, mock responses
and consent files with that framing. The bounded file reader now uses the shared
strict UTF-8 signature decoder only after checking the original raw byte limit.
This supersedes the preceding release's deliberately unchanged adapter input rule.

Exactly one initial signature is optional; embedded quoted U+FEFF remains data.
Native output remains signature-free. Repeated/misplaced/partial signatures,
UTF-16/32, malformed Unicode, duplicate keys and excessive JSON nesting still fail.
Canonical object budgets and completed-response finite-value checks remain intact.
No in-memory JSON, canonical PreparedRequest payload or direct mock string contract
was relaxed. A saved-envelope signature leaves canonical payload hashes unchanged,
whereas a signature added to the original export still changes required source
provenance and the freshly reverified preparation. Consent remains an exact local
contract, never evidence of a transmission or approval to apply a title.

Fourteen new self-authored synthetic tests cover all four evidence scopes through
completion, preview, explicit apply and search; native output; unchanged originals;
one bounded file read; embedded Unicode; raw and canonical size boundaries; fixed
errors before archive access/output creation; stale preparations; forged evidence;
source hash changes; mock file versus direct-string behavior; and disabled or
unconfigured external execution with consent. Tests use ASCII subprocess transport
with universal newlines and no real provider. Restoring the previous decoder only
in memory caused six failing subtests across three new methods. Four no-signature
CLI preparation/completion cases match the previous published stdout byte-for-byte.

Independent review found no blocker and independently passed the 14 new tests and
54 existing adapter tests. The focused encoding, scoped adapter, completion and
native-output bundle passes 109 tests. The final full suite passes 928 tests in
222.497 seconds. Public audit and byte manifest cover 172 files. Documentation
separates input-file framing from source hashes, canonical payloads, budget checks
and explicit review. No actual private data, external model execution/transmission,
automatic title approval, remote mutation or merge occurs. Exact-commit
Ubuntu/Windows Python 3.10/3.12 CI is checked after push.

### 2026-11-04: validate direct title identities and revision types

Independent synthetic reproduction found that the lower-level Python titles API
could target a literal text identity through SQLite coercion: source=True and
conversation=1 matched imported source/conversation strings "1"/"1". A supplied
False revision matched zero, and 1.0 matched integer revision one. CLI identities
already arrive as strings, and reviewed-proposal revisions were already checked;
this gap was in direct library calls, not evidence of a live remote rename.

The title entry point now validates source and conversation string identities and
Unicode scalars before resolving/opening the database. It reuses the existing
source-label validator, preserves accepted string values exactly, and rejects a
supplied revision unless its exact Python type is int and it is nonnegative.
This deliberately narrows malformed direct calls. The documented omitted/None
lower-level revision compatibility remains; a valid supplied revision on an
informational read remains ignored. Write comparison still uses the selected
conversation's latest globally allocated history ID inside the existing immediate
transaction. It is not a global-maximum guard or per-conversation counter.

Twenty-nine independently authored synthetic regressions cover pre-path/pre-read/
pre-write validation, boolean/numeric identity coercion, bool/float revision zero
and one, integer subclasses, invalid Unicode, unchanged database bytes and core
provenance, existing/absent history, exact numeric-looking and Unicode/NUL/whitespace
identities, optional None, valid informational reads, stale and very large revisions,
interleaved history IDs, normal proposal preview/apply, and both title CLI entry
points. SQLite handles close explicitly. CLI tests use universal newlines and
code-point-array argument transport to preserve invalid literal surrogate pairs
without relying on the OS encoding or JSON's surrogate-pair normalization.

Independent review found no blocker and separately reproduced the old coercion,
34 malformed API cases and 24 malformed CLI cases. The focused new suite passes 29;
the combined title validation/review/concurrency bundle passes 72. An early test
harness normalized a surrogate pair and was corrected before final validation.
Overlapping full runs also produced subprocess timeouts, including unchanged
inventory/import tests; no production timeout was loosened. After both runs ended,
the complete final suite was run alone and passed 957 tests in 196.353 seconds.
Future full-suite runs should not overlap in this workspace.

Public audit and byte manifest cover 173 files. This adds no schema migration,
automatic repair of existing ledger entries, inferred approval or new title
semantics. Existing source evidence and the 80-code-point excerpt limit are
unchanged. No actual personal data, model transmission, remote mutation or merge
occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked after push.

### 2026-11-04: carry a selected request through the offline adapter

A synthetic end-to-end audit found a missing bridge, not a parser regression: an
older meaningful user-attributed request was found by search and accepted by the
direct excerpt selector, but twenty later Thanks messages displaced it from the
adapter's documented recent-user window. A supplied response citing the omitted ID
correctly failed, and editing the saved preparation correctly became stale.

The adapter now accepts an optional exact message selector in preparation,
local/mock generation and supplied-response completion. It verifies the existing
entire source scope first, then requires one eligible user occurrence before
applying the unchanged request limits. Attributed repeats require an exact original
physical locator even when selected text agrees. An explicit occurrence may choose
one valid attribution variant without the default duplicate-ID ambiguity, but
malformed or mismatched evidence elsewhere in the verified scope still rejects.
Raw, web branch, retained replay and source-attributed boundaries are preserved.

A bounded immutable evidence_selection field records scope, exact archive ID,
requested locator and resolved attributed locator, with authenticated false. It is
local envelope/proposal context, not provider payload. Completion rebuilds the
recipe and compares the entire preparation, so changing or dropping a selector
stales it even when the resulting payload would be identical. Full raw-content
fingerprints and source provenance checks remain. Scoped counts still describe all
eligible source evidence and omitted distinct IDs, not omitted occurrences; full
context may describe unchosen occurrences. These metadata checks are not source
authentication for manually constructed PreparedRequest values. The normal saved-
response path rechecks actual evidence before producing a proposal.

No-selector outputs remain unchanged. Independent baseline comparisons covered all
four scopes, repeated attributed IDs and truncation. A review also identified an
invalid-call error-precedence change; early option validation was narrowed to new
selector paths, and a regression preserves the previous no-selector order. Existing
raw reads do not gain an unnecessary ID set. Payload/context/response byte limits,
BOM file framing, native no-overwrite saves, external-disabled behavior and the
80-code-point local excerpt cap remain unchanged.

Twenty-eight independently authored synthetic tests cover the old-topic bridge,
all scopes, role/membership failures, repeated occurrences, complete source
verification, provenance and whole-content staleness, immutable selection,
selector syntax before I/O, literal Unicode IDs, exact 65,536-byte acceptance and
65,537-byte rejection, existing text limits, fixed errors, native/BOM files,
local/mock execution and the disabled/unconfigured external path. The new ten-
command guide is executed exactly: all four saved receipts are checked, the archive
stays unchanged until separate apply, and the applied title is found afterward.
Its two fixtures contain only invented data. The earlier raw exact-message guide
also now uses native saving instead of shell redirection, with its existing
regression verifying both actual files and receipts rather than simulating writes.

Independent review found no supported-workflow blocker and passed 78 focused tests.
The adapter/document bundle passed 137 tests before the final added precedence
regression; the final new suite passed all 28. The complete final suite, run alone,
passes 985 tests in 349.846 seconds. Public audit and byte manifest cover 177 files.
No actual personal data, model transmission, automatic title approval, remote
mutation or merge occurs. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked
after push.

## Role-scoped pre-import discovery (0.87.0)

Added optional exact extracted-role filtering to remembered-text inventory queries
in both CLI entry points. The selector narrows match occurrences before pagination,
while full-file parsing, original hashes, grouping, ambiguity blockers, coverage and
whole-conversation counts stay unchanged. Default all-role results remain unchanged.
Web supports the four existing extracted roles; local system/tool searches honestly
return no extracted matches. Role labels do not authenticate human authorship.

Nine synthetic regressions cover web/local profiles, assistant echoes, repeated
substrings, all web roles, noncurrent branches, unsupported local roles, pagination,
hash leases, canonical Unicode, literal matching, invalid options before I/O,
unmatched malformed records, default compatibility and both CLI entry points.
The documented example was run successfully. Independent review found no blockers
and passed 67 focused inventory tests. The full suite passes 994 tests in 230.153
seconds. Publication audit and manifest cover 178 public files. No real source
corpora, external model calls, remote title changes or merges were performed.
Exact-commit cross-platform CI is checked after publication.

## 2026-11-08 Public boundary cleanup (0.87.1-public-boundary-cleanup)

Removed references to a private development log from this record; remote CI
results are the public GitHub Actions history. Rewrote PUBLICATION.md and the
boundary boilerplate for this project's scope instead of the persona wording that
had been copied between repositories. The README tagline, scope table, SKILL.md
description and architecture boundary now state that reviewed local display-title
changes are in scope while remote renaming stays out. Installation and start-here
guides point at `main`, and the documented-command regression follows the new
clone line. The test workflow now also runs on `main`, and this cleanup precedes
merging the workflow branch into `main`. No code path or fixture changed; the
manifest was regenerated for the edited text files.

## 2026-11-08 Recovery rehearsal (0.88.0-recovery-rehearsal)

Added `recovery.py` behind two read-only `recap.py` commands with standalone entry
points. `declare-recovery` reads the live archive in one `mode=ro`/`query_only`
snapshot and writes a `recap.recovery-manifest.v1` file by exclusive creation: the
exact `artifacts` rows, per-source message and conversation counts, a logical
`messages_sha256` over canonical identity-ordered rows, the export-occurrence count
with sorted distinct original hashes per source, the title-history count and digest,
the FTS index row count read from its docsize shadow table, `declared_at` as supplied
text, and boundary text. It also lists `optional_artifacts`: normalized artifacts whose
message rows are all covered by original-export occurrences, because the adapters
derive those bytes in memory and only the original exports exist as files.
`rehearse-recovery` hashes the restored file, opens it read-only and reports
`integrity_check`, expected tables, exact artifact rows, per-source counts, the
messages digest, both optional ledgers (match or both absent), the FTS row count and a
quoted `MATCH` on the first token of the restored archive's own first message. With
`--objects DIR` it hashes at most 10,000 regular files of at most 1 GiB each and
reports every declared hash `PRESENT` or `MISSING`, refusing symlinks and recording
unreadable entries as refusals rather than aborting. The receipt
(`recap.recovery-receipt.v1`) is written by exclusive creation and records the
manifest digest, the supplied restored path with its size and SHA-256, every check
and fixed negative claims; exit status 1 means `RECOVERY_REHEARSAL_FAILED`, and a
corrupt or non-SQLite file yields a FAILED receipt rather than a traceback. The new
shared `text_summary.py` renders `--text` summaries as quoted ASCII so archive data
cannot spoof labels or lines. No import, ingest or title write path changed.

Seventeen synthetic tests cover the declaration and a passing rehearsal with objects,
a tampered message row (digest only), a stale FTS index, a removed row, missing and
unexpected artifact rows, changed title history, both-absent and one-sided ledgers,
missing required objects with the file-count, size and symlink refusals, unreadable
or vanished object files and an unlistable object directory recorded as refusals in
a FAILED receipt instead of aborting the run, garbage, truncated and empty restored
files, exclusive outputs and dangling symlinks, byte-identical restored copies with
no sidecar files, ASCII CLI parity with the standalone script and exit codes, control
and format characters in `--text`, manifest validation including an unknown schema
label, `declared_at` validation, and the guide's sh block executed exactly with
`OUTPUT` replaced by a space-named directory. With the available Python 3.15
interpreter on Windows (SQLite 3.53.4) the full suite ran 1012 tests in
297.924 seconds with TMP and TEMP in a scratch directory: every new test and
every other module passed, with the one existing Windows-only skip in
`test_source_label_validation`, while 15 failures and 1 error remained in three existing
deep-JSON-nesting tests (`test_import_failure_boundaries`,
`test_title_file_encoding`, `test_title_preview_freeze`) that fail identically on the
unchanged `main` tree under that interpreter, whose json module no longer raises the
recursion errors those tests expect; the supported runtimes remain the CI
interpreters. The new module also passed under a second interpreter with SQLite 3.50.4, where
a lost FTS5 index is reported as `malformed inverted index for FTS5 table` rather
than the `fts5: corruption found` row of SQLite 3.53; the test accepts either
wording. `python -m compileall`, the publication audit and manifest verification
pass: 181 manifest entries, 182 audited files. The documented rehearsal was also run
by hand once, and `VACUUM INTO` and plain file copies of a synthetic archive were
rehearsed successfully.

Not claimed: no remote backup, fetch, decryption, key custody or scheduling exists;
a passing rehearsal verifies one restored copy against one manifest and cannot tell a
restored copy from the live archive; the FTS checks are not a complete FTS5 audit and
older bundled SQLite versions report index loss through the FTS checks rather than
`integrity_check`; the legacy `export_provenance` ledger and review-state tables are
not declared; no real archive, account export or backup system was used. Exact-commit
Ubuntu/Windows Python 3.10/3.12 CI is checked after publication.

## 2026-11-08 Documentation restructure (0.88.1-documentation-restructure)

Restructured the documentation without changing any Python module, fixture, test or
executed sh block. README.md shrank from 73,714 to 11,760 bytes and now holds, in this
order: the link to the Korean guide, both taglines, the scope table, the start-with-your-
export paragraphs with the `main` sentence, the quick start and one-CLI sh blocks verbatim,
a twelve-row "Commands at a glance" table, a documentation index with one line for each of
the 35 guides, the design and boundary links (now including RIGHTS.md and VALIDATION.md)
and the rights paragraph. Four guides were added: `docs/COMMANDS.md` (the 30 `recap.py`
subcommands, 16 standalone scripts, the three checks, the test runner and the demo
generator, each with the exact `--help` usage line, a one-line purpose and its guide link),
`docs/WORKFLOWS.md` (the 43 per-feature README sections moved verbatim and grouped into
nine workflow groups, each group naming its topic guides; links were made relative to
`docs/`), `docs/README.ko.md` (Korean guide: purpose, scope, installation and quick start,
main commands, boundaries and what the tool does not do, documentation index; commands and
identifiers unchanged) and `docs/VALIDATION_HISTORY.md` (every earlier entry of this record
verbatim and in order under a one-paragraph preface). VALIDATION.md became the current
snapshot: release, CI matrix, local verification steps, what is not claimed and a pointer
to the history. SKILL.md and the prose of docs/START_HERE.md, docs/TITLE_WALKTHROUGH.md
and docs/INPUT_SCOPE.md now point at the new guides instead of README sections that no
longer exist; their sh blocks and the protected strings are unchanged.

Verification: a paragraph-level comparison confirmed that all 141 paragraphs of the
previous README survive verbatim in README.md or docs/WORKFLOWS.md, except the rewritten
design-links paragraph. A local link checker resolved every local Markdown link, with
or without an anchor, in the 41 Markdown files at the root and under docs/ (380 local
links, no missing file or anchor) and every `docs/*.md` guide named in SKILL.md. With the available
Python 3.15 interpreter on Windows the full suite ran 1012 tests in 317.031 seconds
with TMP and TEMP in a scratch directory: every documented-command test
(`test_start_here`, `test_runtime_check`, `test_recovery_rehearsal`,
`test_export_hash_lease`, `test_title_walkthrough` and the guide-reading tests) passed,
while 15 failures and 1 error remained in the three existing deep-JSON-nesting tests
(`test_import_failure_boundaries`, `test_title_preview_freeze`, `test_title_file_encoding`)
that fail identically on the unchanged `main` tree under that interpreter, as recorded in
the previous entry; the supported runtimes remain the CI interpreters.
`python -m compileall`, the publication audit and manifest verification pass:
185 manifest entries, 186 audited files. The sh blocks of docs/README.ko.md (runtime check,
help, manifest verification, normalized quick start and the one-CLI block) were run by hand
once against a scratch directory.

Not claimed: no behavior, limit or boundary changed and none was re-verified against the
code beyond the guides that tests execute; the Korean guide is a translation of the English
documentation, not an independent specification; no real archive, export or backup system
was used. Exact-commit Ubuntu/Windows Python 3.10/3.12 CI is checked after publication.

## 2026-11-08 Package layout (0.89.0-package-layout)

Moved the code into packages without changing any documented command, CI command,
fixture, usage line or behavior. The 32 implementation modules moved from the repository
root into the new `recaplib/` package (`recaplib/__init__.py` plus the modules, bytes
unchanged except their import lines, which became `from recaplib.<name> import ...`). The
archive core of `recap.py` (`SCHEMA`, `_validate_source`, `ingest`, `ingest_bytes`,
`readonly`, `search`) moved verbatim into `recaplib/archive.py`; `recap.py` stays at the
root as the unified CLI, imports the core from `recaplib.archive` and re-exports those
names, so `from recap import ingest` keeps working and no `recaplib` module imports a
root script. The 92 `test_*.py` modules moved into the `tests/` package
(`tests/__init__.py`); their imports of moved modules, cross-test imports
(`from tests.test_x import ...`), `unittest.mock.patch` targets
(`recaplib.<name>.<attribute>`, including the three targets built from module-name
strings) and repository-root references (`Path(__file__).resolve().parents[1]` in all 28
`Path(__file__)` occurrences, each of which named a script, `docs/` or `examples/` at the
root; the three `runtime_check.__file__` uses in `tests/test_runtime_check.py` were already
root-relative and are unchanged) were updated, and the embedded `-c` program of
`tests/test_title_adapter.py` imports `recaplib.title_adapter`. Sixteen thin
compatibility entry points stay at the root for
every script that has a `__main__` block and is documented in a guide or executed by a
test: `attributed_title.py`, `branch_title.py`, `conversation_search.py`,
`conversation_view.py`, `export_inventory.py`, `import_check.py`, `recovery.py`
(executed by `tests/test_recovery_rehearsal.py`), `replay_local.py`, `replay_title.py`,
`session_workflow.py`, `title_adapter.py`, `title_history.py`, `title_plan.py`,
`title_proposal.py`, `title_suggestion.py` and `web_branch.py`; each imports `main` from
the module of the same name in `recaplib/`, which keeps its own `main()` and `__main__`
block, so `--help` usage lines and behavior are unchanged. Deliberately not moved:
`recap.py`, `runtime_check.py`, `verify_manifest.py` (now importing
`recaplib.strict_json`) and `audit_publication.py` remain real modules at the root because
they are the documented and CI entry points and `tests/test_runtime_check.py` locates the
root through `runtime_check.__file__`; `examples/make_review_demo.py` stays where
`docs/START_HERE.md` executes it. `.github/workflows/tests.yml` is unchanged:
`python -m unittest discover -v` from the root loads the `tests` package.

Documentation: README "Commands at a glance", `docs/COMMANDS.md` (a layout section, the
standalone-script introduction, the test-runner entry and the library-module list),
`docs/README.ko.md`, `docs/ARCHITECTURE.md` (a code-layout section and
`recaplib/recovery.py`) and `docs/WORKFLOWS.md` (`recaplib/local_parser.py`,
`tests/test_replay_coverage.py`) describe the layout; VALIDATION.md names
`python -m unittest tests.test_recap` as the single-module form. No guide named
`python -m unittest test_x`, so no such prose needed rewriting, and no fenced sh block of
any guide changed (checked block by block against the previous tree).

Verification: with the available Python 3.15 interpreter on Windows and TMP/TEMP in a
scratch directory, `python -m unittest discover -q` ran 1012 tests before the move
(407.568 s) and 1012 tests after it (309.485 s); the unittest loader reported no
failed module load, all 92 modules loaded as `tests.<name>`, and the same 15 failures and
1 error remained in the three existing deep-JSON-nesting tests
(`tests.test_import_failure_boundaries`, `tests.test_title_preview_freeze`,
`tests.test_title_file_encoding`) with identical assertion messages; they fail the same way
on the unchanged `main` tree under that interpreter, as recorded in the previous entries.
No test was added, removed or newly failing, and the documented-command tests
(`tests.test_start_here`, `tests.test_runtime_check`, `tests.test_recovery_rehearsal`,
`tests.test_export_hash_lease`, `tests.test_title_walkthrough` and the guide-reading tests)
passed through the root entry points. For all 18 root scripts the `--help` usage block,
joined onto one line, equals the usage line recorded in `docs/COMMANDS.md`, and each script
also ran by absolute path from a foreign working directory without creating a file there.
A local link checker resolved every local Markdown link and anchor in the 41 Markdown
files. `python -m compileall -q .`, the publication audit and manifest
verification pass: 204 manifest entries, 205 audited files.

Not claimed: no behavior, limit, boundary or output format changed and none was
re-verified beyond the test suite and the `--help` comparison; the package layout is a
reading aid, not an import-compatibility promise for code outside this repository; the
supported runtimes remain the CI interpreters, and exact-commit Ubuntu/Windows Python
3.10/3.12 CI is checked after publication; no real archive, export or backup system was
used.

## 2026-11-09 Environment hints removed (0.89.1-environment-hints-removed)

A public review of this repository for information about the maintainer's own
environment found no host name, user name, path, address or account anywhere in the
tree or its history, and five low-severity hints. This release removes them without
changing any documented behavior:

- `recaplib/local_parser.py` classified raw agent session files by a fixed list of
  tool directory names under `agents/<tool>/raw/`. It now accepts any tool directory
  name made of letters, digits, `_`, `.` or `-` at that position; the classification
  of such files as retained raw evidence is unchanged.
- The comment on the `local_occurrences` canonical-message index no longer states how
  often or how long a private re-ingest ran.
- Three fixtures (`tests/test_local_record_discriminator.py`,
  `tests/test_local_byte_snapshot.py`, `tests/test_typed_content_shapes.py`) use the
  neutral tool names `tool-a`, `tool-b` and `tool-c`.
- Five sentences of this history no longer name a time zone, an operating-system
  pairing, a local interpreter version or a workspace; the facts they recorded (which
  checks ran and passed) are otherwise unchanged. The snapshot file drops its time zone.

Verification: the full suite ran on Ubuntu with Python 3.12 before publication
(1012 tests, unchanged count); `verify_manifest.py` and `audit_publication.py` pass
after the manifest was regenerated. Not claimed: the review was a reading of this
repository's text, not a guarantee that no inference about the maintainer is possible;
commit metadata and the public GitHub account remain as they are.

## 2026-11-10 Portable nesting tests (0.89.2-portable-nesting-tests)

- Replaced interpreter-specific failure depths in import, title-file encoding and
  title-preview tests with cached synthetic decoder probes. Twice a failing probe
  depth fits below the supplied-title 1 MiB budget, including wrapper/BOM headroom.
  Only the runtime-dependent case skips if no bounded failing depth is available.
- Kept duplicate-member, surrogate and unconditional injected-RecursionError checks
  separate from skippable fixtures. The fixed long bracket-string and depth-600
  queue-copy fixtures remain unchanged. Probe tests cover caching, the accepted-cap
  skip, byte headroom and unchanged recursion limits.
- Local/local-codex variant hashing now translates encoder RecursionError into a
  fixed nesting error with source path and physical line, suppressing the original
  diagnostic. Deterministic tests cover inspect, inventory and import APIs and CLI
  failures without private keys, tracebacks, source mutation or database creation.
  An actual decoder/encoder-gap test runs when a gap with a 32-frame safety margin
  is available; that case skips on the interpreter used for this validation.

Verification on Python 3.12.14 with synthetic fixtures only:

- `python -m unittest tests.test_nesting tests.test_import_failure_boundaries tests.test_title_file_encoding tests.test_title_preview_freeze -q`:
  `Ran 49 tests in 5.773s`; `OK (skipped=1)`.
- `python -m unittest discover -q`: `Ran 1020 tests in 68.153s`;
  `OK (skipped=1)`. No failures or errors. The one skip is
  `test_actual_local_decoder_encoder_gap_fails_cleanly`, not the deterministic
  encoder failure or strict JSON security checks.
- `python -m compileall -q .`: passed silently. Manifest regenerated with the
  explicit date 2026-11-10; `verify_manifest.py` and `audit_publication.py` passed.
- Existing tested guide sh blocks, CI matrix/triggers and Python 3.10 compatibility
  floor are unchanged. No license decision, release tag or branch deletion.

Not claimed: Python 3.15 or Windows was not run for this entry; adding a newer CI
lane is deferred. A conditional gap test does not establish that every decoder
and encoder limit combination has been exercised. No new production depth limit,
resource exhaustion guarantee, real-data validation, remote CI result, model call,
network access, remote rename or remote recovery is established by these tests.

## 2026-11-10 Read-only HTML views (0.90.0-html-views)

- Added `render --format html --output NEW_FILE`, sharing the existing single-read
  conversation snapshot and all show selectors without changing show JSON.
- Extracted exclusive byte publication while preserving title staging prefixes,
  receipt schema and failure-injection patch points. Recovery and ZIP publishers
  retain their existing contracts in this slice.
- Added inert Unicode HTML, hash-bound CSP, no-referrer, isolated escaped values,
  visible control/format escapes, retained selection and provenance, canonical
  `view_sha256`, and an incremental 16 MiB encoded-output limit before publication.
- Eight synthetic tests cover hostile bodies and metadata, Unicode controls,
  markup, CSP hashes, snapshot selection and determinism, no mutation, exclusive
  publication and cleanup failures, size boundaries, unchanged show JSON and the
  executable guide under ASCII stdout. Existing title output tests also pass.
- `python -m unittest discover -q`: `Ran 1028 tests in 71.398s`;
  `OK (skipped=1)`. No failures or errors. The inherited skip is the
  runtime-dependent actual decoder/encoder depth-gap test.
- `python -m compileall -q .`: passed. New guide commands also executed separately.
  Manifest regenerated with explicit date 2026-11-10; manifest verification and
  publication audit passed. Protected executable guide blocks are unchanged.

Not claimed: active-branch reconstruction, vendor export, reversible transcript,
privacy clearance, browser-edit review authority, real-data validation, remote CI
results, model calls, network calls or authentication. Markdown and saved-queue
views remain deferred. No Windows or browser visual run is claimed locally.

## 2026-11-10 Read-only Markdown views (0.91.0-markdown-views)

- Added `render --format markdown --output NEW_FILE` as the next slice of the
  existing HTML command. It uses the same one-snapshot show object and selectors,
  self-contained metadata/provenance, canonical `view_sha256` and exclusive byte
  publication. Saved-view receipts identify the format without disclosing data.
- Every supplied value stays inside a fixed-info `text` fence. Each fence is
  longer than any consecutive backtick run in its content, including runs across
  display chunks. Only fixed headings, boundary text and message ordinals appear
  outside fences. Shared display escapes retain readable Unicode while exposing
  controls/format characters; no universal Markdown-viewer guarantee is claimed.
- The 16 MiB encoded-output bound counts Unicode, metadata, both fences and
  banners before publication. Large fences are checked before allocation. HTML
  fixture bytes and show JSON stdout are unchanged.
- Twelve new synthetic tests cover hostile metadata and bodies, long fences,
  empty/trailing-newline bodies, controls and surrogates, selected scope and every
  returned provenance occurrence, deterministic bytes, snapshot count, output
  bounds, no-overwrite/link/cleanup failures and ASCII-only receipts. A synthetic
  unfinished local-codex rollout also passes import to Markdown, retaining its
  known messages and provenance without inventing completeness metadata.
- Python 3.12.14: `python -m unittest discover -q` reported
  `Ran 1040 tests in 76.012s`; `OK (skipped=1)`. No failures or errors. The only
  skip is the inherited `test_actual_local_decoder_encoder_gap_fails_cleanly`:
  no decoder/encoder gap with a 32-frame safety margin on this runtime.
- Focused render/title-output checks:
  `python -m unittest tests.test_render_markdown tests.test_render_view tests.test_title_document_output tests.test_adapter_native_output tests.test_title_file_encoding -q`
  reported `Ran 68 tests in 13.230s`; `OK`.
- `python -m compileall -q .` passed. The new Markdown guide commands also ran
  separately with ASCII stdout and readable UTF-8 output. All existing Markdown
  sh blocks remain byte-identical to the preceding release, including the HTML
  guide. No protected quick-start, title, install or recovery block was edited.
- Manifest regenerated with explicit date 2026-11-10 (213 entries); manifest
  verification and the limited publication audit passed. Standard library only,
  existing Python 3.10-compatible syntax and CI matrix/triggers retained.

Not claimed: safety or identical display in all Markdown viewers, reversible
transcripts, completion of a source session or assistant turn, active-branch
reconstruction, privacy clearance, real-data validation, remote CI results,
model/network calls, authentication or review authority. No Windows or graphical
viewer run is claimed locally. Saved review-queue views remain deferred. No
license decision, merge, release tag or branch deletion is part of this change.

## 2026-11-10 Native stdout compatibility tests (0.91.1-markdown-newline-tests)

The [Markdown PR CI run](https://github.com/h-dot-seo/recap-for-everyone/actions/runs/42778716038)
passed both Ubuntu jobs but failed both Windows jobs solely in the new
`test_html_bytes_and_show_stdout_remain_compatible` assertion. It expected LF
bytes even though the unchanged `show` command uses a native text stream, which
emits CRLF on Windows. The HTML byte-hash assertion passed. This was a test
portability error, not a renderer or JSON-content regression.

- The compatibility assertion now compares exact expected JSON bytes with the
  native `os.linesep`, retaining its formatting, field ordering and Unicode-escape
  checks. Production code and output behavior are unchanged.
- Added an independent subprocess test that explicitly sets the real stdout text
  stream to LF and CRLF on every platform, runs the actual show CLI, and checks
  exact bytes, parsed evidence equality, empty stderr and unchanged archive bytes.
- Python 3.12.14 full suite: `python -m unittest discover -q` reported
  `Ran 1041 tests in 75.332s`; `OK (skipped=1)`. No failures or errors. The one
  inherited skip is the runtime-dependent actual decoder/encoder depth-gap test.
- Focused render/title-output suite:
  `python -m unittest tests.test_render_markdown tests.test_render_view tests.test_title_document_output tests.test_adapter_native_output tests.test_title_file_encoding -q`
  reported `Ran 69 tests in 14.116s`; `OK`.
- `python -m compileall -q .`, manifest verification, the limited publication
  audit and whitespace checks passed. Manifest regenerated for 2026-11-10 with
  213 entries. Every existing guide sh block remains unchanged.

The local explicit-CRLF exercise is not a native Windows run. Exact-commit remote
matrix results must be checked separately before merging. No production rendering,
message evidence, file publication, receipt, guide command, CI configuration,
license or release-tag behavior changed.


## 2026-11-10 Archive schema inspection (0.92.0-archive-schema)

Added `recap.py --db DB describe-schema`, a metadata-only inventory in one explicit
read-only snapshot. Known table columns and row counts, lazy-ledger presence,
FTS5 shadow-name classification, docsize-based FTS counts, NULL-safe legacy-only
provenance counts and bounded index/trigger/unknown names are exposed. Missing
FTS docsize means null rather than an external-content count. No lazy table is
created. No SQL definition, default, source label, message body or title is read
for output. Schema names/types may themselves contain private text; the report
warns about this and archive-size disclosure. Encoded output is capped at 16 MiB.

`docs/SCHEMA.md` describes the current seven-table layout, nullable columns,
identity and first-message insertion order, title revision order, external-content
FTS limitations and three tested read-only SQL examples. It explicitly leaves
schema stability and a possible user_version mechanism for a future owner decision.
Existing stats, rendering and title output contracts remain unchanged.

Verification on the final production/test tree:
- `python -m unittest discover -q`: Ran 1055 tests in 74.317s; OK (skipped=1).
  The existing runtime-dependent decoder/encoder depth-gap case was skipped.
- New focused inventory suite: 14 tests in 0.382s; OK. Coverage includes unchanged
  database bytes, one BEGIN/read trace, no lazy tables, missing/non-SQLite/unrelated
  input refusal, required-table view impersonation, hostile unknown names, metadata
  caps, no partial stdout on byte-limit failure, stale/missing FTS docsize, NULL-safe
  legacy comparison, column drift and executable SQL/sh documentation.
- A WAL concurrent commit regression proves counts and schema names remain from
  one snapshot; the next call sees the committed changes. SQL checks preserve empty
  latest titles by id rather than timestamp and retain legacy-only occurrences.
- The new guide was also executed manually with synthetic input; all four lazy
  ledger flags stayed false. Existing Markdown sh blocks were byte-identical.
- Python 3.10 syntax parsing, compileall, manifest verification, publication audit
  and whitespace checks passed. Native Windows execution is deferred to exact-head CI.

These are synthetic bookkeeping checks, not real conversation or service testing.
No archive integrity, index consistency, authentication, completeness, recovery,
privacy audit or schema stability claim is made. No license, tag or packaging
choice was made. Existing fixtures and historical validation entries are preserved.

## 2026-11-10 Saved queue HTML (0.93.0-saved-queue-html)

Added `render-queue QUEUE.json --output NEW_FILE`, a database-free view of one
explicitly saved title-review queue. The page retains original-file SHA-256,
metadata, item order, supplied proposals, advisories, collisions and unavailable
reasons. Current envelope/item shapes and counts are validated; retained proposal
metadata is displayed, not interpreted. Input and encoded output each have a
16 MiB bound. Shared escaping/isolation, fixed CSP style hash and exclusive
publication prevent data-driven markup and overwriting existing paths.

Verification on the final production/test tree:
- `python -m unittest discover -q`: Ran 1066 tests; OK (skipped=1).
  The existing runtime-dependent decoder/encoder depth-gap case was skipped.
- `python -m unittest tests.test_render_queue -q`: 11 tests passed.
- Queue, conversation HTML and title-document focused suites: 37 tests passed.
- Adversarial coverage includes Unicode/control/HTML injection in supplied keys
  and values, JSON duplicates/nonfinite/deep/surrogate failures, exact file/BOM
  hashes, deterministic bytes, empty/unavailable/supplied/page variants, malformed
  schemas and identities, input immutability, no-database ASCII CLI, input/output
  limits, exact output boundary, existing/dangling destinations, publication
  failure and post-publication staging cleanup failure.
- The new guide's exact sh block passed in an automated test and a separate manual
  synthetic execution. Existing changed-guide sh blocks are byte-identical.
- Python 3.10 syntax parsing, compileall, whitespace checks, manifest verification
  and the limited publication audit passed. Conversation renderer, title queue
  producer and shared publication engine bytes are unchanged.

No real conversations, database refresh, network, model, remote rename, approval,
authentication, semantic evidence validation or privacy clearance was tested or
claimed. Browser edits are not review artifacts. Native Windows execution and
remote publication are left to exact-commit CI and the publishing coordinator.

## 2026-11-10 Normalized text export (0.94.0-normalized-export)

Added `export-normalized --source SOURCE [--conversation ID] --output NEW_JSONL`.
One explicit read-only snapshot streams original message fields in global
insertion order to UTF-8 LF JSONL. The existing recovery publisher now delegates
to a streaming sibling with the same exclusive staging/link/cleanup contract.
A text-free receipt identifies the private derived file, reports omitted distinct
modern/legacy provenance rows and explicitly excludes local state and recovery.

Verification on the final production/test tree:
- `python -m unittest discover -q`: Ran 1078 tests in 78.603s; OK (skipped=1).
- Normalized-export and recovery focused suites: 29 tests passed (12 new export
  tests). Golden bytes, interleaved-conversation round trips, Hangul/emoji/control
  preservation, original per-message titles, modern/legacy occurrence omission,
  missing/invalid selection, existing/dangling paths, staged-write failure,
  publication race, damaged rows, cleanup reporting, concurrent-write snapshot
  consistency and tracemalloc-bounded source streaming are covered.
- The new guide's exact sh block passed under ASCII stdout and in an independent
  manual execution. Both archives had four messages; differing artifact counts
  correctly reflect the new derived input. Existing guide sh blocks are unchanged.
- Python 3.10 grammar parsing (160 Python files), compileall, whitespace/LF checks,
  manifest verification and the limited publication audit passed.

No original-export ledger import/export extension, original bytes, local display
history, review state, active-branch reconstruction, completeness, authentication,
privacy clearance or source-archive recovery is claimed. Data and licensing remain
unchanged. Native Windows execution and remote publication remain for exact-commit
CI and the publishing coordinator.

## 2026-11-10 Normalized-export test connection cleanup correction

The initial PR 11 Windows Python 3.12 job (run 42793812740, job 129753692607,
head f0d38f64) reported five temporary-directory cleanup errors with WinError 32
on `archive.sqlite`: duplicate-occurrence counting, invalid-row rejection,
concurrent-write snapshot, legacy provenance and streaming-memory tests.
SQLite connection context managers commit or roll back but do not close handles.
Seven new test connection contexts now use `contextlib.closing` around the
existing transaction context, so transactions finish before deterministic close.
No assertions were removed, and production code and documented export semantics
are unchanged. The release remains `0.94.0-normalized-export`.

The prior local pass did not establish Windows compatibility. The correction
requires a new exact-head Windows/Ubuntu CI pass before merge; this entry does not
claim that remote validation has already succeeded.

Local correction verification:
- `python -m unittest discover -q`: Ran 1078 tests in 73.674s; OK (skipped=1).
- Normalized-export and recovery focused suites: 29 tests passed.
- Manifest verification, limited publication audit, compileall, Python 3.10 grammar
  parsing of 160 files and whitespace checks passed. No production file changed.

## 2026-11-13 Normalized input contract (0.94.1-normalized-input-contract)

The contract names the existing ingest shape without requiring a new schema key.
It documents ignored fields/non-finite unused values, whitespace-only strings,
empty artifacts, byte/physical-line provenance, duplicate identity behavior,
per-line titles, insertion order and the distinction from original-export ledgers.
README/English and Korean indexes, SKILL and input/architecture notes link it.
Production modules, CLI choices and existing examples are byte-identical.

- Full suite: Ran 1090 tests in 66.337s; OK (skipped=1, existing conditional skip).
- Twelve new synthetic contract tests passed, including rollback and no-new-database
  rejection. An initial test assertion used `total` rather than the existing
  `total_matches` result key; the test was corrected, not the production API.
- Independent focused tests, manifest verification and publication audit passed.
  Review corrected an overly broad recovery sentence: only referenced artifacts
  lacking full export-occurrence coverage must be required; empty/unreferenced
  and fully covered artifacts may be optional. Existing guide shell blocks and
  fixture bytes were independently verified unchanged.
- Python 3.10 grammar parsing of 161 files and compileall passed. Final manifest,
  audit and exact-head CI are verified separately at publication time.

No converter, normalized dry-run, hash-bound ingest, selection, new license,
real vendor compatibility, authentication, completeness or privacy clearance is
claimed. Runtime and archive schemas remain unchanged. This is the first bounded
contract slice; dry-run and adapter illustration remain later increments.

## 2026-11-13 Normalized inspection (0.94.2-normalized-inspection)

Adds normalized inspect/check-import without expanding the shared adapter or title
plan dispatcher. Inspection reports conflicting repeats as counts, not admission;
check-import retains its occurrence-number samples and read-only archive snapshot.
The shared structural iterator preserves ingest's early conflict error order and
physical lines. Optional ingest/ingest_bytes expected_sha256 binds the one immutable
byte snapshot before SQLite access; default receipts and provenance stay unchanged.
Documentation explains ignored fields, whitespace text, empty artifacts, title
variation, no normalized selection and the distinction from export-origin ledgers.

- Initial full suite: Ran 1110 tests in 68.794s; OK (skipped=1).
- Final full suite after two additional regressions: Ran 1112 tests in 66.879s;
  OK (skipped=1, existing conditional skip).
- New focused suite: 22 tests passed. Independent code review ran 70 related tests,
  then independently reran the final 22-test set and checked final documentation.
  No blocking findings; clarified COMMANDS wording to refer to the format option,
  rather than suggesting normalized ingest itself was unsupported.
- Tests cover report privacy, silent acceptance counts, empty/BOM/newline input,
  matching structural rejections, early ingest error order, immutable bytes,
  archive/input conflicts, missing archives, source separation, selection rejection,
  closed import/list-export/title-plan dispatchers (including an edited plan),
  same-byte hash guards, no-write mismatch, one-read behavior and standalone parity.
- All existing example source bytes and English/Korean quick-start shell blocks
  remain unchanged. Five affected help usage lines match COMMANDS.md.
- compileall and Python 3.10 grammar parsing of 162 Python files passed. Manifest
  225 entries and publication audit 226 files passed before final history refresh;
  both are rechecked for the publication tree. Exact-head and main CI are checked
  separately before reporting remote completion.

No converter, normalized conversation selection, origin-ledger round trip, schema
migration, real-dataset testing, license choice or privacy clearance is claimed.

## 2026-11-13 Invented adapter illustration (0.94.3-adapter-illustration)

Completes the bounded bring-your-own-format sequence with an explicit invented
JSON shape, standalone stdlib conversion, exact source/normalized byte receipt,
exclusive UTF-8/LF output and a tested guide plus maintainer checklist. No real
vendor grammar, automatic detection, new core format dispatch or original-export
provenance is introduced. The rights document remains unchanged; the guide grants
no reuse license and does not invite contributions.

- Full suite: Ran 1130 tests in 67.153s; OK (skipped=1, existing local conditional skip).
- New focused suite: 18 tests passed. Independent review ran 52 related tests,
  manifest verification and audit; no blocking findings.
- Coverage includes valid conversion and ingest round trip, byte/BOM/hash handling,
  private receipt/error output, one source read, empty inputs, explicit roles and
  ordering, duplicate/unknown/malformed fields, identity scope, nonfinite/Unicode
  rejection, no-overwrite and final-symlink behavior, missing parents, standalone
  execution without repository imports and a fresh-copy walkthrough.
- Documentation tokens are parsed before OUTPUT/HASH substitution. Tests preserve
  spaces and Windows-style backslashes without reparsing native paths as POSIX
  shell syntax. The actual guide runs with a temporary checkout/output containing
  spaces and leaves the synthetic fixture unchanged. Host-restricted symlink
  creation is explicitly skipped only if unavailable.
- Core modules, existing example source bytes and English/Korean quick-start shell
  blocks are byte-identical to the previous release. New command usage matches
  COMMANDS.md. compileall and Python 3.10 grammar parsing of 164 Python files pass.
- Manifest: 229 entries valid. Publication audit: 230 files pass. Both are refreshed
  and rechecked after this append; exact publication-tree and post-merge CI are
  verified separately before remote completion is reported.

The illustration is intentionally non-streaming and not resource bounded. Hash
linkage does not prove authenticity, completeness, permission or losslessness.
Original foreign inputs must be kept separately; recovery declarations describe
normalized artifacts, not those untracked original inputs.

## 2026-11-13 Opt-in time listing (0.95.0-time-listing)

Adds the declared recap.timestamp.v1 interpretation and opt-in list UTC bounds and
recent/oldest ordering. Stored timestamp strings, message insertion order, hashes,
physical lines, export provenance and schema are unchanged. The default inventory
SQL/output and shared _inventory helper remain unchanged; find and stats stay out
of this first increment. Numeric strings use the explicitly disclosed epoch rule,
including date-looking 20260101. Fractional fields truncate before UTC arithmetic.

- Full suite: Ran 1149 tests in 67.204s; OK (skipped=1, existing local conditional skip).
- New focused suite: 19 tests passed. Independent review ran the initial 17 plus
  25 existing related tests, then the final 19. It also compared 10,000 randomized
  valid timestamps against datetime arithmetic and checked combined source/window
  SQL bindings. No blocking findings.
- Tests cover strict ISO/epoch grammar, UTC offset/calendar extremes, microsecond
  truncation, numeric-policy disclosure, whole-day bounds, tied/unknown ordering,
  conversation-level filtering with all-message extrema, source scope, pagination,
  unchanged database/provenance, page-only title lookup, standalone parity and the
  documented fresh-copy walkthrough. A concurrent WAL append proves counts and
  page/title reads retain the same snapshot. Maximum-date filters run end to end.
- Existing example source bytes and English/Korean quick-start shell blocks are
  unchanged; _inventory is byte-identical. New guide commands tokenize placeholders
  before native path substitution and run in paths with spaces. New list help lines
  match COMMANDS.md. compileall and Python 3.10 grammar for 167 Python files pass.
- Manifest 234 entries valid; publication audit 235 files pass. Both are refreshed
  after this history append, with full publication-tree and exact-head/main CI
  checked separately before remote completion is reported.

The query may scan source-scoped messages multiple times and creates no index.
Coverage is interpretation, not authenticity or complete activity. Missing a time
window is not evidence of no activity. Offset pages are not cross-command snapshots.
No clock, local-zone default, relative window, schema migration or write path is added.

2026-11-14 UTC search windows (0.95.1-time-search):
adds opt-in find message-row UTC day filters and window-bound cursor scope.
Default output/cursor scope, stored timestamps, schema and provenance are unchanged.
Nine synthetic tests cover boundary/offset/epoch behavior, original-title refetch,
role/export intersection, pre-open validation, legacy cursor compatibility,
window continuation/rejection, read-only bytes and standalone/unified CLI parity.
See [browse by time](BROWSE_BY_TIME.md).

2026-11-14 Per-source time coverage (0.95.2-time-stats):
adds stats --by-source while preserving the default two-key stats output.
Source-union rows expose stored messages, distinct within-source conversations,
ISO/epoch/unparsed counts and nullable UTC extrema in one read-only snapshot.
Eight synthetic tests cover empty/artifact-only archives, binary identities,
repeated imports, numeric policy and extremes, missing artifact records,
CLI/default/read-only behavior, missing DB and interleaved snapshot consistency.
No schema, ingestion ledger or source activity claim is added.

2026-11-14 ZIP fixed-limit disclosure (0.95.3-zip-limit-disclosure):
adds effective fixed limits to both existing v1 ZIP receipts and metadata-only
exceeded_limits to inventory candidates. Existing reason codes/precedence,
byte snapshots, CRC/JSON-before-staging, hard bounds and error behavior remain.
Six synthetic regressions cover default/call-time constants, size-only/ratio/both,
exact boundaries, unsafe/duplicate priority and pre-construction budget rejection.
This is diagnostics only, not streaming, adjustable bounds or an EOCD rewrite.

2026-11-14 Lower-only ZIP member budget (0.95.4-zip-member-budget):
adds --max-member-bytes to inspection/preparation, restricted to 1..the existing
16 MiB hard ceiling and validated before archive access. Metadata diagnostics,
actual limit+1 member read and receipts share the effective value. No archive,
ratio or entry bound is raised; byte snapshot and CRC/JSON-before-staging remain.
Eight synthetic regressions cover validation, no-read rejection, exact bound/read
budget, runtime constants, ratio protection, defaults, hash/CRC and both CLIs.

2026-11-14 ZIP directory-budget admission (0.95.5-zip-directory-budget):
replaces whole-archive signature counting with bounded EOCD/ZIP64 and actual
central-directory record traversal before ZipInfo construction. Stored attachment
signatures no longer inflate entry counts. Hash lease comparison precedes parsing;
the same immutable bytes, archive/member ceilings and CRC/JSON staging order remain.
Seven synthetic tests cover nested signatures, empty/prefix/comment/ZIP64 archives,
declared/actual count budgets, malformed lengths/offsets and hash-before-parse.
No streaming, bound increase, schema or provenance changes are introduced.

2026-11-14 Re-import conversation delta (0.96.0-import-delta):
adds mutually exclusive conflicting/new/has_new_identities/no_new_identities
conversation counts to check-import in its existing read snapshot, plus optional
exclusive --delta-output private bounded ID samples. Existing message comparisons,
source/selection boundaries and conflict exit1 remain; ingest/provenance unchanged.
Eight synthetic tests and a two-file walkthrough cover priority, duplicates,
scope, snapshot consistency, byte bounds, no-overwrite, privacy and CLI parity.
No activity inference, automatic import, checkpoint or archive-only category.

2026-11-14 Read-only SQLite protections (0.96.1-sqlite-read-safety):
adds connection-local trusted_schema OFF, cell_size_check ON and available
DEFENSIVE to read-only archive and metadata-only SQLite artifact inspection.
Actual read-back states appear in recovery integrity-check detail; unsupported
features are not claimed active. Existing top-level output, schema and writes stay.
Eight synthetic regressions cover settings, non-innocuous hostile views, FTS and
continued ingest, local parser, receipt detail, unavailable APIs and setup cleanup.
These controls are defense in depth, not a hostile-DB sandbox or resource budget.

2026-11-14 Bounded-reader regular-file admission (0.96.2-input-admission):
adds pre-open regular-file/type and existing-size-budget checks to ZIP archives,
recovery manifests, supplied proposals and adapter document readers. Existing
symlink-follow behavior, byte budgets, read-once/post-read checks and errors stay.
Eight synthetic tests cover directory/device/FIFO refusal, size and cumulative
budgets, growth after stat, regular symlinks and missing-file/error behavior.
A read-once adapter test now supplies a real file for stat before mocking open.
Not universal admission, an atomic filesystem lease or a process-memory guarantee.

2026-11-14 Explicit title-review identity selection (0.96.3-selected-review):
adds repeated review-titles --conversation ID and a validated API selection list.
Unrenamed/selected/supplied/state filters intersect before pagination, with binary
order and explicit exclusion accounting. Source-wide existing-title collisions
remain visible; default output, title/state writes and approval boundaries stay.
Nine synthetic tests cover scope, counts, unknown/invalid IDs, page order,
excluded-body reads, collisions, saved-queue rendering/preview, CLI/read-only behavior and an executable guide.
No automatic delta ingestion, checkpoint, completion claim or title application.

2026-11-14 Exact conversation JSON files (0.96.4-saved-conversation):
adds show --output NEW_JSON to unified and standalone views. The unchanged view
object, selection and provenance are serialized as readable UTF-8 to one exclusive
private file; stdout becomes a body/ID-free byte/hash receipt. Default show stays.
Eight synthetic tests cover Unicode, selections, provenance, no-overwrite,
invalid/oversized output, lone-surrogate escapes, CLI parity and executed guide.
No database mutation, sidecar, vendor export, approval or memory-bound guarantee.

2026-11-14 Fresh normalized-object rebuild rehearsal (0.96.5-rebuild-rehearsal):
adds the roadmap #10 first-stage executable guide. Two independent ingests of
retained synthetic JSONL create separate databases, then existing manifest checks
verify logical rows and the newly built FTS index. Tests assert original DB
immutability, real fresh destination, positive checks, changed-source failure and
missing-object failure. No automatic rebuild command, replay plan, exclusive DB
creation, local title/review recovery or remote backup guarantee is added.

2026-11-14 Explicit export byte replay (0.96.6-export-byte-replay):
adds import_export_bytes with explicit original parsing label and LF/CRLF output,
sharing exact conversation selection and provenance logic with path imports.
Eight synthetic tests cover all adapters, file/API parity, label identity,
newline-sensitive digest failure, selection refusal, transactions and executed
guide. Existing CLI serialization and output stay unchanged. No replay-plan
validation, exclusive DB creation or automatic recovery claim is introduced.

2026-11-14 Declared-object archive rebuild (0.97.0-declared-object-rebuild):
adds rebuild-archive with an exact strict-JSON ordered replay plan, source-bound
declared object hashes, explicit adapter labels/newlines and exclusive verified
new-DB publication. Existing recovery checks are shared without changing existing
receipt shape. Declared title history is explicitly not rebuildable; review state
is undeclared/unrestored. Twenty-four synthetic tests cover all formats, digest
mismatches, ordering, source authorization, limits, collisions, staging cleanup,
partial publication, private errors and an executed guide. No live DB access,
full archive restoration, two-file atomicity, hostile namespace defense or remote
backup guarantee is claimed. Windows prepublication fsync uses a writable
non-truncating staging descriptor; a zero-byte-write regression verifies that
requirement on POSIX as well as Windows. The initial PR CI passed both Ubuntu lanes but failed both Windows lanes before DB publication (seven failures and one error in Python 3.12); that failed run is retained as validation history. The repair does not skip fsync or publish an unverified DB.
