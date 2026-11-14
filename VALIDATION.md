# Validation record

Current release: `0.97.4-safe-cli-diagnostics`, dated 2026-11-14.
This file is the current snapshot. Every dated entry since the first release is kept
unchanged and in order in [docs/VALIDATION_HISTORY.md](docs/VALIDATION_HISTORY.md).

## Latest change

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

`.github/workflows/tests.yml` runs on every push to `main` and on pull requests, on
`ubuntu-latest` and `windows-latest` with Python 3.10 and 3.12 (four jobs, `fail-fast:
false`, ten-minute timeout each), in this order: `python -m unittest discover -v`,
`python audit_publication.py`, `python verify_manifest.py`. Actions are commit-pinned,
token permissions are read-only, checkout does not persist credentials, and no secrets
or deployment steps are used. Remote results are the public GitHub Actions history;
this file does not restate or certify them.

This bounded maintenance increment retains Python 3.10 compatibility and the
existing CI matrix and triggers. A newest-interpreter lane and broader interpreter
policy are deferred; no local run here establishes Python 3.15 compatibility.

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
