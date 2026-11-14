# Validation record

Current release: `0.99.5-cli-version`, dated 2026-11-14.
This file is the current snapshot. Every dated entry since the first release is kept
unchanged and in order in [docs/VALIDATION_HISTORY.md](docs/VALIDATION_HISTORY.md).

## Latest change

2026-11-14 CLI version identity (0.99.5-cli-version):
adds recap.py --version as the public interface for the declared numeric program
version. The value is a code constant: version dispatch does not open the local
publication manifest, an archive or a network connection. It works from a different
working directory and without a manifest file. Release-identity tests bind the
numeric value to the manifest release, current validation label and final labeled
history entry using an exact value or value-plus-hyphen boundary, not a loose
prefix. The live command catalog includes the new global option. Existing command
JSON and archive behavior are unchanged. A version label is not proof of exact
file bytes, authenticity, compatibility or a stability promise. No tag, license,
branch deletion, release-frequency or changelog replacement decision is made.

Validation: full synthetic suite 1,449 tests passed (one existing skip); focused
17 and independent 21 checks passed. Representative existing successful JSON and
plain/structured execution errors remain byte-identical to the previous release.
Real subprocess checks cover other working directories, a manifest-free copy,
invalid version options and no archive access. A post-import/warmup audit forbids
file, SQLite and socket I/O during version dispatch; normal Python import reads
are not claimed to disappear. All 133 existing sh blocks remain unchanged.
Manifest 313 files, limited audit 314 files, compile, Python 3.10 syntax and
whitespace checks passed. Version information is not an integrity attestation.

Initial Python 3.15 CI (43609793700, head d8976d8) found one failure in the
new post-import I/O audit: argparse lazily imported its standard-library color
formatter only when formatting the version. The test now warms an independent
standard-library version parser before installing the unchanged open/SQLite/socket
audit. It does not call recap version during warmup or allow archive/manifest I/O.
Real missing-manifest and different-directory subprocess checks remain unchanged;
no production code change was needed for this test portability correction.

Previous change:

2026-11-14 Synthetic suite timing observer (0.99.4-test-timing):
adds the opt-in python -m tests.timing observer from roadmap #17. It executes
selected published synthetic test modules once, sequentially in one fresh worker,
and emits one strict JSON observation on stdout. Per-module time includes loading
and fixtures; the total includes worker orchestration, not process startup. All
unittest outcome counts remain visible, including fixture errors and skips, and
failure/error/unexpected success is exit 1. Diagnostics and incidental process
output are withheld rather than copied into the receipt. No automatic receipt
file, environment path, host, SQLite build or network operation is introduced.
Interpreter metadata is limited to major.minor. This is a measurement aid, not
identical discovery timing, a performance guarantee or a replacement CI gate.
Existing test bodies, CLI helpers and product code remain unchanged.

Independent review found two pre-publication protocol gaps: duplicate worker JSON
keys could overwrite a failure flag, and decoder RecursionError escaped the fixed
error path. The parent now uses the shared strict JSON reader, explicit UTF-8 and
fixed recursion failure handling. Duplicate keys, non-finite JSON, invalid UTF-8,
deep malformed JSON and injected decoder recursion are regression-tested.

Validation: full synthetic suite 1,443 tests passed (one existing skip), and the
actual full timing command independently reported 1,443 tests across 139 modules
with the same zero failures/errors and one skip. Focused and independent 15 tests
passed. Synthetic checks cover all unittest outcomes, fixture errors, empty suites,
selection refusal and hidden fd output; the small documented command runs as a
real process. All existing product and test files and 132 sh blocks are unchanged.
Manifest 312 files, limited audit 313 files, compile, Python 3.10 syntax and
whitespace checks passed. No private input or published timing receipt was used.

Previous change:

2026-11-14 Current Python CI coverage (0.99.3-current-python-ci):
adds Python 3.15 on Ubuntu and Windows to the existing Python 3.10/3.12
matrix, making six jobs, and allows explicit manual workflow dispatch. Existing
push branch filters, pull-request trigger, commit-pinned actions, read-only token
permissions, disabled credential persistence, timeout and all three verification
steps are preserved. The Python 3.10 compatibility floor is unchanged. No product
code, schema, default output, private input, network client or approval boundary
changes. Earlier deferred-lane records remain historical; a broader interpreter
support or retirement policy is not introduced. New static workflow regression
checks accompany the actual remote installation and full-suite CI gates.

Validation: local Python 3.12 full synthetic suite 1,434 tests passed (one existing
skip); focused nesting/import/title/workflow checks 69 passed (one existing skip).
Independent review passed all five workflow contract tests and detected eight
mutations of triggers, actions, permissions and verification gates. All 78 product
modules and 132 existing sh blocks are byte-identical. Manifest 309 files, limited
audit 310 files, compile, Python 3.10 syntax and whitespace checks passed. Remote
Python 3.15 installation and six-job PR/main outcomes must be checked separately;
no local result is claimed as new-interpreter or Windows evidence.

Initial six-job CI (43605504317, head 91ad1a3) installed Python 3.15
successfully and exposed a remaining fixed-depth adapter test: Ubuntu 3.15 accepted
the depth-10,000 JSON, so three expected-error subtests failed. No product failure
or new nesting restriction was inferred. That case now uses the existing bounded
decoder-failure probe in a separate test, so an unavailable failing depth skips
only nesting and cannot hide encoding/strict-JSON checks. The other invalid cases
and all three adapter error-code expectations are preserved. Product code is
unchanged; the corrected head requires all six CI jobs again.

Previous change:

2026-11-14 Opt-in MCP supplied-proposal review (0.99.2-mcp-supplied-proposals):
adds proposal paths and supplied_only to review-titles only for servers launched
with allowed input directories. Default schemas, protocol bytes and raw review
results remain unchanged. Every path is admitted before loading; file count and
aggregate preflight use existing 1000-file and combined 1 MiB limits, additionally
bounded by the lower configured byte budget. The existing loader retains its
actual combined 1 MiB bounded-read check. Reduced preflight limits are not atomic
against concurrent file growth or replacement. Existing exact-source, duplicate,
stale-evidence, collision and partial-page checks are reused without new trust
semantics. No checkpoint, output, application, title or review-state write is
exposed; successful queues remain private and READY is not approval. Only invented
proposals and local subprocess clients were used; no external client was connected.

Validation: full synthetic suite 1,428 tests passed (one existing skip); focused
and independent 76 tests passed. Default wire bytes and schemas remain unchanged
across alternating opt-in/default sessions. Real subprocess supplied queues match
existing CLI JSON and preserve the complete scratch tree. Independent connection
tracking checked 41 SQLite connections, all explicitly closed; proposal loss after
preflight returns a fixed error before DB access. All 132 prior sh blocks remain
unchanged. Manifest 308 files, limited audit 309 files, compile, Python 3.10 syntax
and whitespace checks passed. No personal proposal or external connection used.

Previous change:

2026-11-14 Opt-in MCP input-directory inspection (0.99.1-mcp-file-inspection):
adds five explicit file-read tools only when input directories are selected at
launch. The default six archive tools and their results remain unchanged. Strict
canonical containment, regular-file status and a lowerable 1..64 MiB admission
budget precede existing readers; no directory scan, staging copy, source rewrite,
proposal/checkpoint input, output writer or per-call DB selection is exposed.
These are preflight checks, not a hostile-filesystem sandbox, immutable snapshot,
strict parsing-memory bound or consent guarantee. Private success results can
contain file text and identities; admission errors do not echo supplied paths.
ZIP inspection retains existing directory/member budgets without decompression.
Unsupported replay returns its unchanged document with isError=true. No actual
external client, registration, network endpoint or private input is used.

Validation: full synthetic suite 1,418 tests passed (one existing skip); focused
33 tests passed. Independent checks confirmed default protocol bytes unchanged,
no unnecessary DB access, path admission before readers and fixed value-free
errors. All five file tools were exercised through real EOF-terminated subprocess
calls and compared with existing CLI JSON. Whole-tree inventories include empty
directories and node types; review caught a Windows separator assumption in the
new inventory assertion, corrected to portable keys before publication. Existing
132 sh blocks were preserved. Manifest 307 files, limited audit 308 files, compile,
Python 3.10 syntax and whitespace checks passed. Only synthetic inputs were used.

Previous change:

2026-11-14 Explicit read-only MCP stdio access (0.99.0-readonly-mcp):
adds an operator-launched foreground stdio entry point with six fixed archive-read
tools and protocolVersion 2025-06-18. It directly invokes existing read functions,
not a generic CLI, SQL or shell dispatcher. Calls cannot select a DB, supply files,
write outputs or change titles/review state. Private result text is not sanitized
or approved for disclosure; the client controls subsequent transmission/retention.
Strict framing, parameter/type checks, finite JSON, request/response bounds and
an explicit request-ID admission limit are tested. No installed/connected client,
network service, private archive or external model is involved in validation.
Existing CLI outputs, archive writes, source bytes and provenance remain unchanged.

Pre-publication independent review found three protocol defects in the first
implementation: notification-named requests with IDs were silently dropped;
a large Unicode request ID could be replaced by null after response expansion;
and standard object-valued params._meta was rejected. These were corrected before
publishing. Notifications now depend only on absent ID; accepted IDs are preserved,
over-limit IDs are refused before execution and close the session; _meta is
validated and ignored without enabling progress notifications. Regression checks
cover these cases. The server does not promise query time/memory bounds, absence
of SQLite sidecars, client data protection or full protocol extension support.

Validation: full synthetic suite 1,407 tests passed (one existing skip); focused
22 tests passed. Independent checks reproduced and then verified fixes for the
three pre-publication protocol issues, including a large Unicode ID and accepted
ID boundary values. All six tool results match existing CLI JSON on the synthetic
archive; the DELETE-mode scratch tree is unchanged. The documented configuration
was parsed and launched with fictional data. Existing 132 sh blocks were preserved.
Manifest 306 files, limited audit 307 files, compile, Python 3.10 syntax and
whitespace checks passed. No real client connection or private DB was used.

Previous change:

2026-11-14 Agent task routing and write stop points (0.98.2-agent-task-routing):
reorganizes SKILL.md around the README's 17 task categories, documented result
fields, DB policies and guide links. Separate archive and new-file write tables
cover current default/conditional resources and the adapter's two native saves.
Source import, wording, review decisions and output destinations remain explicit
operator choices. Error/partial-publication stop points do not authorize retry.
All prior 43 prose paragraphs, the frontmatter and eight principles are preserved;
regressions bind navigation and write declarations to actual parser/catalogue
metadata and verify guide links/anchors. No production code, output format,
archive write, source/provenance semantics or common instruction template changes.

Validation: full synthetic suite 1,396 tests passed (one existing skip); eight
focused document tests passed, with independent boundary extraction and deliberate
command/write/link/boundary fault checks. Recognizable command/option fragments
are checked against parsers; arbitrary prose or unknown bare fragments are not
a complete command grammar. All 132 existing sh blocks remain unchanged. Manifest
302 files and limited audit 303 files passed, as did compile, Python 3.10 syntax
and whitespace checks. This documentation is not permission or proof of review.

Previous change:

2026-11-14 Selected in-process CLI regression checks (0.98.1-cli-test-harness):
adds a test-only direct-call harness with write-time ASCII stdout, escaped stderr,
SystemExit/integer-return handling, unexpected-exception tracebacks and restored
argv/cwd/streams. The first five repeated title/adapter modules retain their 101
tests; nine new tests check the harness and all 20 root CLI entry points through
real processes. Saved-response guide commands and all other guide/interpreter/
fd/audit-hook checks remain actual subprocesses. No production module, output,
archive, provenance, consent or partial-publication behavior changes. A bounded
local comparison observed less repeated interpreter startup, not a portable speed
claim or complete test-process isolation. Remaining test families are not migrated.

Validation: full synthetic suite 1,388 tests passed (one existing skip); focused
110 tests passed. Independent review retained all 101 migrated test-method ASTs
and tracked 679 SQLite connections, all explicitly closed. All 132 existing sh
blocks were preserved. Manifest: 301 files; limited publication audit: 302 files;
compile and Python 3.10 syntax checks passed. No portable timing claim is made.

Previous change:

2026-11-14 Opt-in structured execution errors (0.98.0-json-execution-errors):
adds unified global --json-errors for the existing caught-error exit-1 stderr
path only. Explicit ValueError subclasses mark selected source, stale-state,
identity-lookup and identity-conflict checks without changing messages or order.
Standard exception families map to coarse filesystem/SQLite codes; the remainder
is UNCLASSIFIED without message matching. Default and standalone text, successful
stdout, negative result documents and argparse exit 2 remain unchanged. Synthetic
actual failures, private diagnostic markers, partial rebuild publication and the
executed guide are tested. No catch-set expansion, automatic retry, rollback,
privacy-sanitization or recovery-readiness guarantee is added.

Previous change:

2026-11-14 Synthetic command effect matrix (0.97.9-command-effect-matrix):
checks every unified command declared to have no default write through an actual
successful CLI invocation before comparing the complete synthetic scratch tree
and file bytes. Conditional document outputs and explicit local title/review
writes are checked separately for their declared effects. The matrix case set is
bound to the command catalogue, so new or reclassified commands require a case.
Synthetic inputs and an explicitly closed DELETE-mode archive bound the claim;
this is not an arbitrary-archive, hostile-filesystem or WAL-sidecar guarantee.
Negative-result paths and oracle fault injections prevent failure-only or vacuous
read-only assertions. Existing command outputs, write authorization, provenance,
recovery and partial-publication boundaries remain unchanged.

Previous change:

2026-11-14 Static command discovery (0.97.8-command-catalog):
adds describe [COMMAND] for unified parser arguments, explicit DB policies,
conditional write effects, existing output labels, result exits and guide links.
Parser construction is separated from execution without changing existing command
results. The catalogue is also the DB-requirement source; the missing-DB diagnostic
adds describe to its exception list. Selected standalone workflows have scoped
static effects rather than duplicated option parsers. The optional manifest
release is a declaration, not verification, and unreadable metadata yields null.
Command/option coverage, no archive opening, release fallbacks, write conditions,
usage-document drift and the executed guide are checked with synthetic fixtures.
No JSON error envelope, document relabelling, schema migration, permission grant,
review authentication or provenance/rights expansion is introduced.

Previous change:

2026-11-14 Private synthetic scaling observations (0.97.7-synthetic-scaling-observations):
adds a deterministic bounded fictional fixture generator and a standalone local
benchmark. Exact regeneration, strict manifest bytes and file hashes gate every
input; a caller-supplied synthetic flag alone is not trusted. A new scratch
archive receives real title revisions and review decisions, and 19 import/query/
review/recovery operations run separately for time and Python allocation peaks.
Private exclusive receipts bind code and fixture identities, archive size/counts,
repetitions and uncontrolled-cache/native-memory limitations; stdout is counts-only.
Deterministic ZIP bytes, tampered fixtures, path collisions, traced failures,
SQLite connection closure and the N50 executed guide are covered. No existing
archive, new schema/index, streaming, timing threshold, speed guarantee, rights
inference or publication of local measurements is introduced.

Previous change:

2026-11-14 Single-pass adapter admission (0.97.6-single-pass-adapter-import):
removes the repeated normalized JSON decode after web/local/local-codex adapters
have produced rows. Shared row validation and input-conflict preflight precede
SQLite; direct normalized ingest still strict-parses its byte snapshot. The same
writer retains artifact bytes/hashes, native or explicit replay newline behavior,
physical source lines, original occurrences, receipts, rollback and FTS semantics.
Synthetic differential tests compare serialized-byte ingestion with adapter rows,
including Unicode, duplicate identities, conflicts, empty input and both newline
forms; a work-count oracle and executed guide cover the removed decode pass.
No new CLI flag, schema, provenance meaning, authorization, streaming, timing or
bounded-memory guarantee is introduced. Source, rows and derived bytes still
remain in memory. Newly owned SQLite test connections close explicitly.

Previous change:

2026-11-14 Private message provenance cards (0.97.5-message-provenance-cards):
adds export-provenance and check-provenance for one exact source/conversation/
message tuple. A private unsigned bounded card contains text hashes and byte
counts, normalized locators and the same legacy/complete occurrence UNION as
show, without message bodies, titles or title revisions. A shared caller-snapshot
helper preserves show pagination and context selection. Rechecks compare exact
current metadata, reporting PASS or STALE without private values and without
changing the archive or card. Exclusive creation, schema/size gates, deterministic
bytes, legacy/plain ingest, changed occurrences, Unicode, exact identities and
executed guide are tested. A locator is not evidence of validity, authorship,
consent, retrieval or publication status; no cross-repository mapping is added.

Previous change:

2026-11-14 Safe low-level CLI diagnostics (0.97.4-safe-cli-diagnostics):
shares fixed diagnostics for already-caught OS, SQLite, JSON-decoder and Unicode-
decoder errors across unified and existing standalone entry points. Established
validation messages, adapter codes, caught exception sets, exit statuses and
stdout result-level failure documents remain unchanged. Exact code-authored safe
publication/protection messages are retained; rebuild receipt failure after DB
publication retains the published/preserved warning without the destination path.
Synthetic actual and injected failures, output collisions, missing parents,
private markers, fixed-message parity and the executed error guide are tested.
No JSON envelope, new flag, global data-sanitization or no-mutation-on-error claim
is introduced. Argparse and unexpected programming-error behavior are unchanged.

Previous change:

2026-11-14 Reviewed manifest candidate builder (0.97.3-reviewed-manifest-builder):
adds public build_manifest.py with read-only added/removed/changed-path plans and
exact plan-hash leases for exclusively new outside-tree candidates. Base bytes
and complete candidate bytes bind each plan; existing metadata is retained except
explicit release/date text. The existing verifier accepts a candidate object for
shared validation without changing its default CLI. Limited audit, portable paths,
CR/symlink/special-file refusals and repeat scans guard publication. A fictional
contributor guide exercises plan review and candidate creation. No manifest is
overwritten, no privacy/rights approval or license/tag policy is inferred, and
no Git, deployment or CI permission change is performed. This is not an atomic
filesystem snapshot or a hostile concurrent-namespace sandbox.

Previous change:

2026-11-14 Accepted-artifact import cutoff (0.97.2-accepted-artifact-cutoff):
adds declare-checkpoint and counts-only changed-since for one explicit source.
A private unsigned artifact declaration binds original accepted message rows with
recovery-compatible logical digests. Comparison verifies the declared subset in
one read snapshot before reporting mutually exclusive conversation classes; any
mismatch returns CUTOFF_NOT_VERIFIED with no delta and CLI exit 1. New artifacts
are permitted without changing ingest receipts or recovery-manifest semantics.
No source/conversation IDs or excerpts enter stdout, no DB mutation, approval,
completeness, review completion, archive identity or automatic advancement is
claimed. Exact bounded schemas, exclusive output, tamper refusal, CLI parity,
executed guide and explicit SQLite connection closure are checked.

Previous change:

2026-11-14 Source-wide review view cutoff (0.97.1-review-view-checkpoint):
adds declare-review-checkpoint and opt-in review-titles --since-checkpoint.
One read snapshot binds sorted source identities, existing content fingerprints
and local title revisions in a private unsigned file. Exact bounded validation,
deterministic bytes, source-wide comparison counts, filter intersections and
full-source existing-title collisions are tested. Saved queues remain usable for
HTML and fresh previews. No archive mutation, approval, completion, batch skip,
authentication, provenance comparison or automatic checkpoint advancement is
claimed. Existing no-checkpoint outputs and tested guide commands are preserved.

2026-11-14 Windows CI follow-up: PR29 head ee86fc40c53048e592beb98f44fd4ef6c066a253, run 43571478278, passed both Ubuntu lanes but Windows Python 3.12 reported one temporary-directory cleanup error (WinError 32). The new missing-entry test used SQLite transaction context management without closing its connection. It now explicitly closes the connection after committing and asserts that further SQL is rejected. No product code, fsync, data checks or cleanup assertion is weakened.

Previous change:

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

Previous change:

2026-11-14 Explicit export byte replay (0.96.6-export-byte-replay):
adds import_export_bytes with explicit original parsing label and LF/CRLF output,
sharing exact conversation selection and provenance logic with path imports.
Eight synthetic tests cover all adapters, file/API parity, label identity,
newline-sensitive digest failure, selection refusal, transactions and executed
guide. Existing CLI serialization and output stay unchanged. No replay-plan
validation, exclusive DB creation or automatic recovery claim is introduced.

Previous change:

2026-11-14 Fresh normalized-object rebuild rehearsal (0.96.5-rebuild-rehearsal):
adds the roadmap #10 first-stage executable guide. Two independent ingests of
retained synthetic JSONL create separate databases, then existing manifest checks
verify logical rows and the newly built FTS index. Tests assert original DB
immutability, real fresh destination, positive checks, changed-source failure and
missing-object failure. No automatic rebuild command, replay plan, exclusive DB
creation, local title/review recovery or remote backup guarantee is added.

Previous change:

2026-11-14 Exact conversation JSON files (0.96.4-saved-conversation):
adds show --output NEW_JSON to unified and standalone views. The unchanged view
object, selection and provenance are serialized as readable UTF-8 to one exclusive
private file; stdout becomes a body/ID-free byte/hash receipt. Default show stays.
Eight synthetic tests cover Unicode, selections, provenance, no-overwrite,
invalid/oversized output, lone-surrogate escapes, CLI parity and executed guide.
No database mutation, sidecar, vendor export, approval or memory-bound guarantee.

Previous change:

2026-11-14 Explicit title-review identity selection (0.96.3-selected-review):
adds repeated review-titles --conversation ID and a validated API selection list.
Unrenamed/selected/supplied/state filters intersect before pagination, with binary
order and explicit exclusion accounting. Source-wide existing-title collisions
remain visible; default output, title/state writes and approval boundaries stay.
Nine synthetic tests cover scope, counts, unknown/invalid IDs, page order,
excluded-body reads, collisions, saved-queue rendering/preview, CLI/read-only behavior and an executable guide.
No automatic delta ingestion, checkpoint, completion claim or title application.

Previous change:

2026-11-14 Bounded-reader regular-file admission (0.96.2-input-admission):
adds pre-open regular-file/type and existing-size-budget checks to ZIP archives,
recovery manifests, supplied proposals and adapter document readers. Existing
symlink-follow behavior, byte budgets, read-once/post-read checks and errors stay.
Eight synthetic tests cover directory/device/FIFO refusal, size and cumulative
budgets, growth after stat, regular symlinks and missing-file/error behavior.
A read-once adapter test now supplies a real file for stat before mocking open.
Not universal admission, an atomic filesystem lease or a process-memory guarantee.

Previous change:

2026-11-14 Read-only SQLite protections (0.96.1-sqlite-read-safety):
adds connection-local trusted_schema OFF, cell_size_check ON and available
DEFENSIVE to read-only archive and metadata-only SQLite artifact inspection.
Actual read-back states appear in recovery integrity-check detail; unsupported
features are not claimed active. Existing top-level output, schema and writes stay.
Eight synthetic regressions cover settings, non-innocuous hostile views, FTS and
continued ingest, local parser, receipt detail, unavailable APIs and setup cleanup.
These controls are defense in depth, not a hostile-DB sandbox or resource budget.

Previous change:

2026-11-14 Re-import conversation delta (0.96.0-import-delta):
adds mutually exclusive conflicting/new/has_new_identities/no_new_identities
conversation counts to check-import in its existing read snapshot, plus optional
exclusive --delta-output private bounded ID samples. Existing message comparisons,
source/selection boundaries and conflict exit1 remain; ingest/provenance unchanged.
Eight synthetic tests and a two-file walkthrough cover priority, duplicates,
scope, snapshot consistency, byte bounds, no-overwrite, privacy and CLI parity.
No activity inference, automatic import, checkpoint or archive-only category.

Previous change:

2026-11-14 ZIP directory-budget admission (0.95.5-zip-directory-budget):
replaces whole-archive signature counting with bounded EOCD/ZIP64 and actual
central-directory record traversal before ZipInfo construction. Stored attachment
signatures no longer inflate entry counts. Hash lease comparison precedes parsing;
the same immutable bytes, archive/member ceilings and CRC/JSON staging order remain.
Seven synthetic tests cover nested signatures, empty/prefix/comment/ZIP64 archives,
declared/actual count budgets, malformed lengths/offsets and hash-before-parse.
No streaming, bound increase, schema or provenance changes are introduced.

Previous change:

2026-11-14 Lower-only ZIP member budget (0.95.4-zip-member-budget):
adds --max-member-bytes to inspection/preparation, restricted to 1..the existing
16 MiB hard ceiling and validated before archive access. Metadata diagnostics,
actual limit+1 member read and receipts share the effective value. No archive,
ratio or entry bound is raised; byte snapshot and CRC/JSON-before-staging remain.
Eight synthetic regressions cover validation, no-read rejection, exact bound/read
budget, runtime constants, ratio protection, defaults, hash/CRC and both CLIs.

Previous change:

2026-11-14 ZIP fixed-limit disclosure (0.95.3-zip-limit-disclosure):
adds effective fixed limits to both existing v1 ZIP receipts and metadata-only
exceeded_limits to inventory candidates. Existing reason codes/precedence,
byte snapshots, CRC/JSON-before-staging, hard bounds and error behavior remain.
Six synthetic regressions cover default/call-time constants, size-only/ratio/both,
exact boundaries, unsafe/duplicate priority and pre-construction budget rejection.
This is diagnostics only, not streaming, adjustable bounds or an EOCD rewrite.

Previous change:

2026-11-14 Per-source time coverage (0.95.2-time-stats):
adds stats --by-source while preserving the default two-key stats output.
Source-union rows expose stored messages, distinct within-source conversations,
ISO/epoch/unparsed counts and nullable UTC extrema in one read-only snapshot.
Eight synthetic tests cover empty/artifact-only archives, binary identities,
repeated imports, numeric policy and extremes, missing artifact records,
CLI/default/read-only behavior, missing DB and interleaved snapshot consistency.
No schema, ingestion ledger or source activity claim is added.

Previous change:

2026-11-14 UTC search windows (0.95.1-time-search):
adds opt-in find message-row UTC day filters and window-bound cursor scope.
Default output/cursor scope, stored timestamps, schema and provenance are unchanged.
Nine synthetic tests cover boundary/offset/epoch behavior, original-title refetch,
role/export intersection, pre-open validation, legacy cursor compatibility,
window continuation/rejection, read-only bytes and standalone/unified CLI parity.
See [browse by time](docs/BROWSE_BY_TIME.md).

Previous change:

2026-11-13 Opt-in time listing (0.95.0-time-listing):
adds a deterministic timestamp rule and list-only UTC windows/recent/oldest order.
Default inventory SQL/output, stored values and provenance remain unchanged.
Nineteen synthetic tests cover strict grammar, numeric-policy disclosure, offsets,
truncation, calendar boundaries, ties, missing times, same-snapshot counts/titles,
page-only title lookups, read-only behavior, standalone parity and guide execution.
No find cursor, stats extension, schema migration or ingestion ledger is added.
See [browse by time](docs/BROWSE_BY_TIME.md).

Previous change:

2026-11-13 Invented adapter illustration (0.94.3-adapter-illustration):
adds a standalone stdlib converter for one synthetic shape, an exact-byte receipt,
exclusive LF output, a tested walkthrough and maintainer checklist. Eighteen
synthetic tests cover rejected structure, identity, Unicode, no-overwrite behavior,
private errors, standalone execution and native-path placeholder handling.
Core modules and existing examples remain unchanged. No vendor compatibility,
new format dispatch, rights grant or community contribution invitation is added.
See [the guide](docs/ADAPTER_GUIDE.md).

Previous change:

2026-11-13 Normalized inspection (0.94.2-normalized-inspection):
adds database-free normalized inspection and existing-archive conflict diagnostics,
plus optional exact-byte ingest hash guards. Twenty-two synthetic regression tests
cover silent acceptances, conflict counts, preserved early ingest errors, privacy,
read-only behavior, hash mismatch before writes and standalone CLI parity.
Shared export/title-plan adapters remain closed to normalized input. No converter,
selection, origin-ledger change or accepted-input tightening is introduced.
See [the contract and diagnostics](docs/NORMALIZED_JSONL.md).

Previous change:

2026-11-13 Normalized input contract (0.94.1-normalized-input-contract):
consolidates existing accepted/rejected input, repeated identity behavior, titles
and normalized-file provenance. Twelve synthetic characterization tests exercise
these boundaries. Production modules, CLI choices and existing examples are
unchanged. No dry-run, converter or runtime behavior change is claimed.
See [the contract](docs/NORMALIZED_JSONL.md).

Previous change:

2026-11-10 Normalized-export test connection cleanup correction:
the first remote Windows Python 3.12 run failed during temporary-directory cleanup
because seven test SQLite connections were committed but not explicitly closed.
The test contexts now close handles deterministically while preserving transactions.
Production code and export behavior are unchanged. Remote validation remains
pending until the corrected exact commit passes CI; see the validation history.

Previous change:

2026-11-10 Normalized text export (0.94.0-normalized-export):
`export-normalized` streams whole-source or selected-conversation JSONL from one
read-only snapshot, with exclusive publication and a private-file receipt.
Synthetic tests cover round trips, Unicode, global ordering, omitted provenance,
legacy ledgers, snapshot consistency and bounded buffering. See
[the guide](docs/EXPORT_NORMALIZED.md). No origin-ledger round trip, backup,
active-branch reconstruction or privacy clearance is claimed.

Previous change:

2026-11-10 Saved queue HTML (0.93.0-saved-queue-html):
`render-queue QUEUE.json --output NEW_FILE` renders one bounded saved title queue
without a database. Original-file SHA-256, supplied metadata, order and advisory
warnings remain visible in inert HTML. See [the tested guide](docs/RENDER_QUEUE.md)
and the dated validation history. No freshness, approval or privacy clearance is
claimed. Existing conversation renderers and title JSON output are unchanged.

Previous change:

2026-11-10 Archive schema inspection (0.92.0-archive-schema):
`describe-schema` inventories a single read-only metadata snapshot without lazy
schema creation. The current-layout reference includes tested SQL and a column
drift check. See [SCHEMA.md](docs/SCHEMA.md) and the dated validation history.
No layout stability, integrity, authenticity or completeness claim is made.

Previous change:

2026-11-10 Native stdout compatibility tests (0.91.1-markdown-newline-tests):
the new show-compatibility assertion now respects native text-stream line endings
(CRLF on Windows, LF on POSIX). A deterministic test exercises both translations.
No production output, rendering, publication behavior or guide block changed.
See the dated validation history entry.

Previous change:

2026-11-10 Read-only Markdown views (0.91.0-markdown-views): `render --format
markdown` extends the existing snapshot, selection and no-overwrite output path.
All metadata and bodies are fenced, controls follow the shared display rule and
the encoded cap includes fence bytes. HTML bytes and show JSON remain unchanged.
See [the Markdown guide](docs/RENDER_MARKDOWN.md) and the dated validation history.

Previous change:

2026-11-10 Read-only HTML views (0.90.0-html-views): `render --format html`
uses the existing conversation snapshot and selectors, writes an inert Unicode
HTML file exclusively, and emits a private saved-view receipt. See
[the guide](docs/RENDER_VIEWS.md) and the dated validation history entry.

Previous change:

2026-11-10 Portable nesting tests (0.89.2-portable-nesting-tests): synthetic depth
fixtures now probe the running decoder within the smallest exercised byte budget.
Local variant hashing catches encoder recursion errors without leaking private
metadata or a traceback. Deterministic error-injection checks remain unconditional;
only runtime-dependent depth cases may skip. Full entry and verification counts:
[validation history](docs/VALIDATION_HISTORY.md#2026-11-10-portable-nesting-tests-0892-portable-nesting-tests).

Previous change: 2026-11-09 Environment hints removed (0.89.1-environment-hints-removed): the local
session parser now accepts any tool directory under `agents/<tool>/raw/` instead of
a fixed list of tool names, an index comment no longer describes how often or how
long a private re-ingest ran, three fixtures use neutral tool names, and five
sentences of the validation history no longer name a time zone, an operating
system pairing, a local interpreter version or a workspace. No behavior for the
documented formats changed; 1012 tests before and after. Full entry:
[validation history](docs/VALIDATION_HISTORY.md#2026-11-09-environment-hints-removed-0891-environment-hints-removed).

## What CI runs

`.github/workflows/tests.yml` runs on pushes to `main` and the preserved
`codex/core-workflows-20261103` branch, on pull requests and manual dispatch, on
`ubuntu-latest` and `windows-latest` with Python 3.10, 3.12 and 3.15 (six jobs,
`fail-fast: false`, ten-minute timeout each), in this order: `python -m unittest discover -v`,
`python audit_publication.py`, `python verify_manifest.py`. Actions are commit-pinned,
token permissions are read-only, checkout does not persist credentials, and no secrets
or deployment steps are used. Remote results are the public GitHub Actions history;
this file does not restate or certify them.

This increment preserves the Python 3.10 compatibility floor and existing CI
triggers while adding the Python 3.15 lane and manual dispatch. A broader
interpreter support or retirement policy remains a separate decision. Local checks
do not establish Windows or Python 3.15 success; inspect the exact-commit remote
six-job result before merging.

## How to verify locally

From the repository root, with your chosen launcher in place of `python`
([installation and runtime checks](docs/INSTALL.md)):

1. `python -m unittest discover -v` runs the synthetic standard-library suite, the
   `tests/` package (one module runs as `python -m unittest tests.test_recap`). On
   restricted Windows hosts set `TMP` and `TEMP` to a writable scratch directory. The
   tests use temporary synthetic data and never read your conversations. Documented
   sh blocks (for example in `docs/START_HERE.md`, `docs/INSTALL.md` and
   `docs/RECOVERY_REHEARSAL.md`) are executed exactly as written.
2. `python verify_manifest.py` must print `{"valid": true, "errors": []}`. It also
   rejects files outside the manifest, so run it on a clean checkout without private
   working files.
3. `python audit_publication.py` must report `"pass": true` for the limited prohibited
   file-type and secret-pattern scan.
4. `python -m compileall -q .` must be silent.

## What this record does not claim

- No real conversation export, archive, account, title history or backup system was
  used in any entry; every fixture is synthetic and says so.
- Passing tests, audit and manifest checks show only that the generic code and the
  synthetic fixtures behave as documented on the tested interpreters. They are not
  proof of anonymity, copyright or legal clearance, semantic title quality, model
  behavior, remote renaming or remote recovery.
- A local pass does not establish that a push, a remote CI run or a remote backup
  succeeded. Exact-commit CI results are checked in the GitHub Actions history after
  publication, and recovery is never marked verified from a Git ref or push message.
- The supported runtimes are the CI interpreters. Observations under other interpreters
  are recorded in the history as observations, not as support.

Windows repair validation follow-up: the first repair passed rebuild success paths but exposed one remaining link-failure injection error on Windows. The test compared an unresolved TEMP alias with the resolved publication path. Its matcher now resolves both paths and asserts exactly one injected failure; production publication code is unchanged.

New-test portability checklist: enumerate every new sqlite3.connect/readonly call; require closing or try/finally close for owned connections, verify caller-owned wrappers are closed by the production caller, and retain an explicit closed-connection regression assertion. All new checkpoint test connections were checked; the WAL setup now also closes on errors.

Contributor inventory entry point: `build_manifest.py` plans by default and only
creates new outside-tree candidates with an exact reviewed plan hash.

Prepublication independent review caught a candidate-metadata audit gap: supplied release/date text had not been checked against publication patterns. Candidate encoded bytes now receive the same pattern checks, with value-free errors and plan/write regression coverage. Nothing was published before this correction.

Prepublication independent review found a SQLite BLOB locator escaping the intended stale-check boundary as a serialization TypeError. The bounded card projection now converts only serialization/type failures to a fixed ValueError so a valid saved card recheck reports STALE; genuine SQLite/query errors still propagate and unbounded show behavior is unchanged. A BLOB-anchor regression verifies no output or database mutation.

Round-34 CI correction: the first PR head passed both Ubuntu jobs but a new
Windows cwd assertion failed; its captured traceback was hidden by the assertion
diff. Directory equality now uses actual filesystem identity rather than lexical
resolved-path equality, with an alias-path regression and a different-directory
negative check. Original cwd-string restoration checks remain. Failures now expose
the captured diagnostic to the test runner. This changes no product code; the
Windows result must be established by the corrected-head CI, not inferred locally.
