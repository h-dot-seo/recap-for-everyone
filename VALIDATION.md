# Validation record

Current release: `0.94.0-normalized-export`, dated 2026-11-10.
This file is the current snapshot. Every dated entry since the first release is kept
unchanged and in order in [docs/VALIDATION_HISTORY.md](docs/VALIDATION_HISTORY.md).

## Latest change

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
