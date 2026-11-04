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
passed with the available Python 3.13 launcher; the complete suite ran with the
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
