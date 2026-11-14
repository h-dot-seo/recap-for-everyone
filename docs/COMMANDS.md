# Command reference

Scripts and subcommands in this repository, with usage summaries, a one-line
purpose and a guide. Unified recap.py usage lines are checked against its parser
(joined onto one line); standalone nested parser prefixes can vary with Python
versions, so use that script's --help for the current rendered prefix. Run from the repository root with your chosen Python launcher in
place of `python` ([installation and runtime checks](INSTALL.md)). Every command
works on explicitly supplied local files and an operator-selected SQLite archive:
none contacts a network service, calls a model, discovers files in private
folders or renames a conversation in its original application. JSON output can
contain private text, titles and IDs; keep it outside the public repository.

## Layout

The repository root holds only the entry points: `recap.py`, the standalone scripts
listed below, `runtime_check.py`, `verify_manifest.py`, `audit_publication.py` and `build_manifest.py`. Each
standalone script at the root is a thin compatibility entry point that imports `main`
from the implementation module of the same name in `recaplib/`, so every command in
this reference runs exactly as written. The implementation lives in the `recaplib/`
package (the archive core behind `recap.py` is `recaplib/archive.py`, re-exported by
`recap.py`), and the synthetic test suite is the `tests/` package. Both are found
through the repository root, which is why the commands run from there.

## recap.py

```text
usage: recap.py [-h] [--db DB] [--json-errors] {ingest,search,stats,describe-schema,inspect,list-export,inspect-web-zip,prepare-web-export,replay-local,web-branch,suggest-branch-title,suggest-replay-title,suggest-attributed-title,preview-title,apply-title,review-state,render-queue,review-titles,title-adapter-dry-run,title-adapter-simulate,export-title-plan,check-title-plan,import,check-import,export-normalized,export-provenance,check-provenance,declare-review-checkpoint,declare-checkpoint,changed-since,declare-recovery,rehearse-recovery,rebuild-archive,list,find,show,render,suggest-title,title,title-history,describe} ...
```

The global `--db DB` precedes the subcommand. `describe` lists the current required,
ignored and rejected DB policies, including separate restored/new DB arguments.
Commands that
accept `--output NEW_JSON` create a UTF-8 file without overwriting an existing path
and print only a receipt ([saved title documents](TITLE_DOCUMENT_FILES.md)).
`export-normalized` also requires `--db`; its required `--output` writes private
JSONL, not a title document, and stdout carries a text-free receipt.

### Archive metadata inspection

#### `describe-schema`

```text
usage: recap.py describe-schema [-h]
```

Read-only, single-snapshot table/column inventory, counts, lazy-ledger presence,
FTS docsize count and legacy-only provenance count. Schema object names may be
private. No content output, mutation, validation or stability promise. See
[the current SQLite layout and read-only SQL examples](SCHEMA.md).

### Normalized JSONL archive

#### `ingest`

```text
usage: recap.py ingest [-h] --source SOURCE [--expected-sha256 EXPECTED_SHA256] input
```

Optionally require inspected bytes with `--expected-sha256 HASH` before database
access. Import one already-normalized UTF-8 JSONL file into the archive, hashing its
original bytes and retaining a line locator per message. Guide: README quick start
and [workflows](WORKFLOWS.md#normalized-jsonl-ingest-and-the-generic-session-parser).

#### `export-normalized`

```text
usage: recap.py export-normalized [-h] --source SOURCE [--conversation CONVERSATION] --output OUTPUT
```

Export one source or conversation in global insertion order from one read-only
snapshot to exclusive UTF-8 LF JSONL. Full private message text, original titles,
no origin ledger or local title history. Guide: [normalized export](EXPORT_NORMALIZED.md).

#### `search`

```text
usage: recap.py search [-h] [--limit LIMIT] query
```

Message-level FTS5 search with literal AND-connected terms; returns original
message titles. Guide: [workflows](WORKFLOWS.md#search-and-read-the-archive).

#### `stats`

```text
usage: recap.py stats [-h] [--by-source]
```

Read-only counts for the selected archive.

### Choose and inspect an export

#### `inspect-web-zip`

```text
usage: recap.py inspect-web-zip [-h] [--limit LIMIT] [--offset OFFSET] [--expected-archive-sha256 EXPECTED_ARCHIVE_SHA256] [--max-member-bytes MAX_MEMBER_BYTES] input
```

List conventionally named conversation JSON members of a downloaded ZIP with
metadata-only eligibility, without decompression. Guide: [ZIP inventory](WEB_ZIP_INVENTORY.md).

#### `prepare-web-export`

```text
usage: recap.py prepare-web-export [-h] --member MEMBER --output OUTPUT [--max-member-bytes MAX_MEMBER_BYTES] [--expected-archive-sha256 EXPECTED_ARCHIVE_SHA256] input
```

Validate one explicitly selected ZIP JSON member and copy its bytes to a new local
file. Guide: [prepare a web export](PREPARE_WEB_EXPORT.md).

#### `list-export`

```text
usage: recap.py list-export [-h] --format {web,local,local-codex} [--limit LIMIT] [--offset OFFSET] [--expected-export-sha256 EXPECTED_EXPORT_SHA256] [--contains CONTAINS | --text-contains TEXT_CONTAINS] [--text-role {user,assistant,system,tool}] [--canonical-unicode] input
```

List exact IDs, existing web titles, extraction counts and selection blockers
without a database or message bodies; `--contains` filters metadata and
`--text-contains` finds IDs by remembered message text. Guide: [export inventory](EXPORT_INVENTORY.md).

#### `inspect`

```text
usage: recap.py inspect [-h] --format {web,local,local-codex,normalized} [--conversation CONVERSATION] [--expected-export-sha256 EXPECTED_EXPORT_SHA256] input
```

Validate and extract in memory, reporting hash, counts, coverage and warnings
without opening or creating a database. Guide: [input scope](INPUT_SCOPE.md).

### Import

#### `import`

```text
usage: recap.py import [-h] --format {web,local,local-codex} --source SOURCE [--conversation CONVERSATION] [--expected-export-sha256 EXPECTED_EXPORT_SHA256] input
```

Import an explicitly selected web, generic local or typed Codex local export, or
only one conversation of it, retaining all text branches and raw records with
original hashes and locators. Guide: [input scope](INPUT_SCOPE.md).

#### `check-import`

```text
usage: recap.py check-import [-h] --format {web,local,local-codex,normalized} --source SOURCE [--conversation CONVERSATION] [--expected-export-sha256 EXPECTED_EXPORT_SHA256] [--limit LIMIT] [--delta-output DELTA_OUTPUT] input
```

Diagnose title-only, text and metadata identity conflicts against an existing
archive without importing. Guide: [import conflicts](IMPORT_CONFLICTS.md).

### Search and read

#### `list`

```text
usage: recap.py list [-h] [--source SOURCE] [--limit LIMIT] [--offset OFFSET] [--order {recent,oldest}] [--from FROM_DATE] [--until UNTIL_DATE]
```

Inventory of conversations with original title, current display title, revision
and message count. Guide: [message selection](MESSAGE_SELECTION.md).

#### `find`

```text
usage: recap.py find [-h] [--source SOURCE] [--limit LIMIT] [--export-sha256 EXPORT_SHA256] [--include-title-history] [--canonical-unicode] [--text-role {user,assistant,system,tool}] [--from FROM_DATE] [--until UNTIL_DATE] [--cursor CURSOR] query
```

Read-only search across current display titles and message text with bounded
samples and cursor pages. Guides: [search excerpts](SEARCH_EXCERPTS.md),
[search pagination](SEARCH_PAGINATION.md), [canonical Unicode search](CANONICAL_UNICODE_SEARCH.md),
[title history search](TITLE_HISTORY_SEARCH.md), [export-scoped search](EXPORT_SCOPED_SEARCH.md).

#### `show`

```text
usage: recap.py show [-h] --source SOURCE --conversation CONVERSATION [--output OUTPUT] [--limit LIMIT] [--offset OFFSET] [--message MESSAGE] [--around-message AROUND_MESSAGE] [--before BEFORE] [--after AFTER]
```

Read one conversation, one exact message, a bounded page or neighbors around a
message, with provenance. Guides: [message selection](MESSAGE_SELECTION.md),
[omitted search messages](OMITTED_SEARCH_MESSAGES.md).

#### `title-history`

```text
usage: recap.py title-history [-h] --source SOURCE --conversation CONVERSATION [--limit LIMIT] [--offset OFFSET] [--expected-revision EXPECTED_REVISION]
```

Bounded local title-change events without message-body columns. Guide:
[title history view](TITLE_HISTORY_VIEW.md).

### Propose a local title

#### `suggest-title`

```text
usage: recap.py suggest-title [-h] --source SOURCE --conversation CONVERSATION [--output NEW_JSON] [--message MESSAGE]
```

Deterministic user-text excerpt proposal from the raw archive, optionally from one
exact message. Guide: [title review hints](TITLE_REVIEW_HINTS.md#choose-a-more-informative-user-message).

#### `suggest-branch-title`

```text
usage: recap.py suggest-branch-title [-h] --source SOURCE --conversation CONVERSATION [--node NODE] [--message MESSAGE] [--output NEW_JSON] input
```

Proposal from the verified path of an archived web export (default endpoint
`current_node`). Guide: [title walkthrough](TITLE_WALKTHROUGH.md).

#### `suggest-replay-title`

```text
usage: recap.py suggest-replay-title [-h] --source SOURCE --conversation CONVERSATION [--message MESSAGE] [--output NEW_JSON] input
```

Proposal from the retained turns of a narrow local replay projection, matched to
archived occurrences. Guide: [title walkthrough](TITLE_WALKTHROUGH.md).

#### `suggest-attributed-title`

```text
usage: recap.py suggest-attributed-title [-h] --source SOURCE --conversation CONVERSATION [--message MESSAGE] [--origin-locator ORIGIN_LOCATOR] [--output NEW_JSON] input
```

Proposal from explicitly user-labeled parts of a verified local-codex export.
Guides: [source-attributed titles](SOURCE_ATTRIBUTED_TITLES.md),
[attributed message selection](ATTRIBUTED_MESSAGE_SELECTION.md).

### Review, decide, apply

#### `review-titles`

```text
usage: recap.py review-titles [-h] --source SOURCE [--limit LIMIT] [--offset OFFSET] [--conversation CONVERSATION] [--since-checkpoint SINCE_CHECKPOINT] [--state {open,skipped,deferred}] [--unrenamed-only] [--proposal PROPOSAL] [--supplied-only] [--output NEW_JSON]
```

Read-only page of proposals with current titles, advisory hints and collision
counts, optionally from supplied proposal files. Guides: [title review queue](TITLE_REVIEW_QUEUE.md),
[supplied title review](SUPPLIED_TITLE_REVIEW.md).

#### `review-state`

```text
usage: recap.py review-state [-h] --source SOURCE --conversation CONVERSATION [--set {open,skipped,deferred}] [--expected-state-revision EXPECTED_STATE_REVISION] [--expected-title-revision EXPECTED_TITLE_REVISION] [--expected-content-sha256 EXPECTED_CONTENT_SHA256] [--from-queue FROM_QUEUE]
```

Read or explicitly record an open, skipped or deferred decision under revision and
content checks. Guide: [title review state](TITLE_REVIEW_STATE.md).

#### `preview-title`

```text
usage: recap.py preview-title [-h] [--output NEW_JSON] [--with-evidence] [--conversation CONVERSATION] [--title TITLE] input
```

Read-only preview of a proposal or of one queue item, optionally with explicit
replacement wording or cited evidence; returns the expected revision. Guides:
[title review hints](TITLE_REVIEW_HINTS.md), [title review evidence](TITLE_REVIEW_EVIDENCE.md).

#### `apply-title`

```text
usage: recap.py apply-title [-h] input
```

Apply a reviewed preview as one local display-title change under content and
revision checks. Guide: [title walkthrough](TITLE_WALKTHROUGH.md).

#### `title`

```text
usage: recap.py title [-h] --source SOURCE --conversation CONVERSATION [--set SET] [--expected-revision EXPECTED_REVISION]
```

Read current, original and suggested titles with history; `--set` with the
preview's `--expected-revision` writes one checked change. Guide:
[workflows](WORKFLOWS.md#export-and-title-workflow).

### Branch and replay views without a database

#### `web-branch`

```text
usage: recap.py web-branch [-h] --conversation CONVERSATION [--node NODE] input
```

Read one path of a web export from root to `current_node` or an explicit node.
Guide: [workflows](WORKFLOWS.md#read-one-web-conversation-branch-without-importing-it).

#### `replay-local`

```text
usage: recap.py replay-local [-h] input
```

Fail-closed completed-turn text projection of a narrow local grammar. Guide:
[workflows](WORKFLOWS.md#opt-in-completed-turn-text-projection).

### Manual title transfer

#### `export-title-plan`

```text
usage: recap.py export-title-plan [-h] --format {web,local,local-codex} --source SOURCE --conversation CONVERSATION input
```

Export a versioned manual title-change plan after at least one local revision;
always `NOT_EXECUTED`. Guide: [workflows](WORKFLOWS.md#export-a-manual-title-change-plan-for-web-or-local-sessions).

#### `check-title-plan`

```text
usage: recap.py check-title-plan [-h] input plan
```

Recreate the plan from the current archive snapshot and require an exact match.
Guide: [workflows](WORKFLOWS.md#export-a-manual-title-change-plan-for-web-or-local-sessions).

#### `title-adapter-dry-run`

```text
usage: recap.py title-adapter-dry-run [-h] input plan target
```

Validate a mock-only transfer request against a checked plan without executing.
Guide: [title transfer](TITLE_TRANSFER.md).

#### `title-adapter-simulate`

```text
usage: recap.py title-adapter-simulate [-h] input request approval target
```

Simulate an explicitly approved transfer in memory only; nothing is persisted or
sent. Guide: [title transfer](TITLE_TRANSFER.md).

### Recovery

#### `declare-recovery`

```text
usage: recap.py declare-recovery [-h] --output OUTPUT [--declared-at DECLARED_AT] [--text]
```

Write a `recap.recovery-manifest.v1` manifest describing the live archive
read-only. Guide: [recovery rehearsal](RECOVERY_REHEARSAL.md).

#### `rehearse-recovery`

```text
usage: recap.py rehearse-recovery [-h] --restored-db RESTORED_DB --output OUTPUT [--objects OBJECTS] [--text] input
```

Verify a restored copy against a manifest, optionally hash fetched objects, and
write a `recap.recovery-receipt.v1` receipt; exit status 1 means
`RECOVERY_REHEARSAL_FAILED`. Guide: [recovery rehearsal](RECOVERY_REHEARSAL.md).

## Standalone scripts

Each script is the standalone equivalent of the `recap.py` command named beside it
and behaves the same way. The root file is a compatibility entry point; the
implementation is the module of the same name in `recaplib/`.

### `session_workflow.py` (`import`, `inspect`, `title`)

```text
usage: session_workflow.py [-h] [--db DB] {import,inspect,title} ...
usage: session_workflow.py import [-h] --format {web,local,local-codex} --source SOURCE [--conversation CONVERSATION] [--expected-export-sha256 EXPECTED_EXPORT_SHA256] path
usage: session_workflow.py inspect [-h] --format {web,local,local-codex,normalized} [--conversation CONVERSATION] [--expected-export-sha256 EXPECTED_EXPORT_SHA256] path
usage: session_workflow.py title [-h] --source SOURCE --conversation CONVERSATION [--set SET] [--expected-revision EXPECTED_REVISION]
```

Explicit export adapters and reversible local title organization. Guide:
[workflows](WORKFLOWS.md#export-and-title-workflow).

### `export_inventory.py` (`list-export`)

```text
usage: export_inventory.py [-h] --format {web,local,local-codex} [--limit LIMIT] [--offset OFFSET] [--expected-export-sha256 EXPECTED_EXPORT_SHA256] [--contains CONTAINS | --text-contains TEXT_CONTAINS] [--text-role {user,assistant,system,tool}] [--canonical-unicode] input
```

Guide: [export inventory](EXPORT_INVENTORY.md).

### `import_check.py` (`check-import`)

```text
usage: import_check.py [-h] --db DB --source SOURCE --format {web,local,local-codex,normalized} [--conversation CONVERSATION] [--expected-export-sha256 EXPECTED_EXPORT_SHA256] [--limit LIMIT] input
```

Guide: [import conflicts](IMPORT_CONFLICTS.md).

### `conversation_search.py` (`find`)

```text
usage: conversation_search.py [-h] --db DB [--source SOURCE] [--limit LIMIT] [--include-title-history] [--export-sha256 EXPORT_SHA256] [--text-role {user,assistant,system,tool}] [--cursor CURSOR] [--canonical-unicode] [--from FROM_DATE] [--until UNTIL_DATE] query
```

Guides: [search excerpts](SEARCH_EXCERPTS.md), [search pagination](SEARCH_PAGINATION.md).

### `conversation_view.py` (`list`, `show`)

```text
usage: conversation_view.py [-h] --db DB {list,show} ...
usage: conversation_view.py list [-h] [--source SOURCE] [--limit LIMIT] [--offset OFFSET] [--order {recent,oldest}] [--from FROM_DATE] [--until UNTIL_DATE]
usage: conversation_view.py --db DB show [-h] --source SOURCE --conversation CONVERSATION [--limit LIMIT] [--offset OFFSET] [--message MESSAGE] [--around-message AROUND_MESSAGE] [--before BEFORE] [--after AFTER]
```

Guide: [message selection](MESSAGE_SELECTION.md).

### `title_history.py` (`title-history`)

```text
usage: title_history.py [-h] --db DB --source SOURCE --conversation CONVERSATION [--limit LIMIT] [--offset OFFSET] [--expected-revision EXPECTED_REVISION]
```

Guide: [title history view](TITLE_HISTORY_VIEW.md).

### `title_suggestion.py` (`suggest-title`)

```text
usage: title_suggestion.py [-h] --db DB --source SOURCE --conversation CONVERSATION [--message MESSAGE] [--output NEW_JSON]
```

Guide: [workflows](WORKFLOWS.md#generate-a-local-title-excerpt-for-review).

### `title_proposal.py` (`preview-title`, `apply-title`)

```text
usage: title_proposal.py [-h] --db DB {snapshot,preview,apply} ...
usage: title_proposal.py --db DB snapshot [-h] --source SOURCE --conversation CONVERSATION
usage: title_proposal.py --db DB preview [-h] [--output NEW_JSON] [--title TITLE] [--with-evidence] input
usage: title_proposal.py --db DB apply [-h] input
```

Operator or external-adapter proposal contract: `snapshot` returns the content
fingerprint a proposal must cite; no model is called. Guide:
[workflows](WORKFLOWS.md#external-title-proposal-contract).

### `web_branch.py` (`web-branch`)

```text
usage: web_branch.py [-h] --conversation CONVERSATION [--node NODE] input
```

Guide: [workflows](WORKFLOWS.md#read-one-web-conversation-branch-without-importing-it).

### `branch_title.py` (`suggest-branch-title`)

```text
usage: branch_title.py [-h] --db DB --source SOURCE --conversation CONVERSATION [--node NODE] [--message MESSAGE] [--output NEW_JSON] input
```

Guide: [workflows](WORKFLOWS.md#suggest-a-title-from-a-verified-archived-branch).

### `replay_local.py` (`replay-local`)

```text
usage: replay_local.py [-h] input
```

Guide: [workflows](WORKFLOWS.md#opt-in-completed-turn-text-projection).

### `replay_title.py` (`suggest-replay-title`)

```text
usage: replay_title.py [-h] --db DB --source SOURCE --conversation CONVERSATION [--message MESSAGE] [--output NEW_JSON] input
```

Guide: [workflows](WORKFLOWS.md#propose-a-title-from-verified-retained-local-turns).

### `attributed_title.py` (`suggest-attributed-title`)

```text
usage: attributed_title.py [-h] --db DB --source SOURCE --conversation CONVERSATION [--message MESSAGE] [--origin-locator ORIGIN_LOCATOR] [--output NEW_JSON] input
```

Guide: [source-attributed titles](SOURCE_ATTRIBUTED_TITLES.md).

### `title_plan.py` (`export-title-plan`, `check-title-plan`)

```text
usage: title_plan.py [-h] --db DB {export,check} ...
usage: title_plan.py --db DB export [-h] --format {web,local,local-codex} --source SOURCE --conversation CONVERSATION input
usage: title_plan.py --db DB check [-h] input plan
```

Guide: [workflows](WORKFLOWS.md#export-a-manual-title-change-plan-for-web-or-local-sessions).

### `title_adapter.py` (no `recap.py` equivalent)

```text
usage: title_adapter.py [-h] --db DB --source SOURCE --conversation CONVERSATION [--kind {local,mock,external}] [--provider-id PROVIDER_ID] [--model MODEL] [--endpoint ENDPOINT] [--allow-external] [--timeout TIMEOUT] [--evidence-scope {raw,web-branch,local-replay,local-attributed}] [--input INPUT] [--node NODE] [--message MESSAGE] [--origin-locator ORIGIN_LOCATOR] {prepare,generate,complete-response} ...
usage: title_adapter.py --db DB --source SOURCE --conversation CONVERSATION prepare [-h] [--output NEW_JSON]
usage: title_adapter.py --db DB --source SOURCE --conversation CONVERSATION generate [-h] [--response RESPONSE] [--consent CONSENT]
usage: title_adapter.py --db DB --source SOURCE --conversation CONVERSATION complete-response [-h] [--output NEW_JSON] prepared response
```

Provider-neutral title generation contract: `prepare` freezes a bounded request,
`generate` runs only the local excerpt or a deterministic mock (the external kind
returns `EXTERNAL_NOT_CONFIGURED` without sending anything), and
`complete-response` validates a separately obtained response against the unchanged
preparation. Guides: [title adapter](TITLE_ADAPTER.md), [saved title response](SAVED_TITLE_RESPONSE.md),
[adapter message selection](ADAPTER_MESSAGE_SELECTION.md).

### `recovery.py` (`declare-recovery`, `rehearse-recovery`)

```text
usage: recovery.py [-h] {declare,rehearse} ...
usage: recovery.py declare [-h] --db DB --output OUTPUT [--declared-at DECLARED_AT] [--text]
usage: recovery.py rehearse [-h] --restored-db RESTORED_DB --output OUTPUT [--objects OBJECTS] [--text] manifest
```

Guide: [recovery rehearsal](RECOVERY_REHEARSAL.md).

## Checks, tests and examples

### `runtime_check.py`

```text
usage: runtime_check.py [-h]
```

Check the Python version and an in-memory SQLite FTS5 probe; exit 0 for `READY`.
Guide: [install](INSTALL.md).

### `verify_manifest.py` and `audit_publication.py`

```text
python verify_manifest.py
python audit_publication.py
```

Both take no arguments. The first verifies every published file's bytes against
`PUBLICATION_MANIFEST.json` and rejects unlisted files; the second runs the
limited prohibited-type and secret-pattern scan. Neither is proof of anonymity or
legal clearance. Guides: [publication boundary](../PUBLICATION.md), [security](../SECURITY.md).

### `python -m unittest discover -v`

Runs the synthetic standard-library test suite, the `tests/` package, from the
repository root; one module runs as `python -m unittest tests.test_recap`. Set
`TMP`/`TEMP` to a writable scratch directory on restricted Windows hosts. Record:
[validation](../VALIDATION.md).

### `examples/make_review_demo.py`

```text
usage: make_review_demo.py [-h] destination
```

Create the invented two-part web ZIP and local JSONL used by [Start here](START_HERE.md)
in a new directory whose parent exists; it reads no conversation files.

## Library modules without a command line

All of these live in the `recaplib/` package. `recaplib/archive.py` (schema, normalized
JSONL ingest, read-only connections and FTS search behind `recap.py`),
`recaplib/local_parser.py` (generic normalized session parser and manifest utilities),
`recaplib/prepare_web_export.py` and `recaplib/inspect_web_zip.py` (ZIP preparation and
inventory behind the `recap.py` commands), `recaplib/title_batch.py` (review pages),
`recaplib/title_transfer.py` (mock transfer contract), `recaplib/title_document_output.py`
(exclusive `--output` saving), `recaplib/title_evidence.py`, `recaplib/title_excerpt.py`,
`recaplib/title_review.py`, `recaplib/title_review_state.py`, `recaplib/title_rules.py`,
`recaplib/source_identity.py`, `recaplib/source_text.py`, `recaplib/strict_json.py`,
`recaplib/text_summary.py` and `recaplib/unicode_search.py` are imported by the commands
above and have no entry point of their own; the implementation of every standalone
script is likewise the module of the same name in `recaplib/`. Design notes:
[architecture](ARCHITECTURE.md).

### `render`

```text
usage: recap.py render [-h] --source SOURCE --conversation CONVERSATION [--limit LIMIT] [--offset OFFSET] [--message MESSAGE] [--around-message AROUND_MESSAGE] [--before BEFORE] [--after AFTER] --format {html,markdown} --output NEW_FILE
```

Save a readable Unicode HTML or Markdown view from the same read snapshot and
selectors as `show`. Choose `--format html` or `--format markdown`;
`--output NEW_FILE` is required. No standalone twin exists. stdout is only an ASCII
`recap.saved-view.v1` receipt with the selected document kind. Existing paths are
refused and encoded output is capped at 16 MiB before staging. All Markdown data
is fenced with a fixed `text` info string and fences longer than any contained
backtick run; not every viewer is guaranteed safe. See [HTML views](RENDER_VIEWS.md)
and [Markdown views](RENDER_MARKDOWN.md).

### Saved queue HTML view

#### `render-queue`

```text
usage: recap.py render-queue [-h] --output NEW_FILE QUEUE.json
```

Read one saved title-review queue without a database and publish inert HTML to a
new file. Original file SHA-256, queue order, advisories, collisions and unavailable
reasons remain visible. No approval or freshness claim. No standalone equivalent.
See [saved queue views](RENDER_QUEUE.md).

`--format normalized` is supported only by inspect and check-import, without
`--conversation`. Conflicting repeats are reported, not inspection failures; use
ingest for admission. See [the normalized contract](NORMALIZED_JSONL.md).

## Invented adapter illustration

```text
usage: adapter_illustration.py [-h] --output OUTPUT input
```

`python examples/adapter_illustration.py INPUT --output NEW_JSONL` converts only
the invented shape in `examples/foreign-sample.json`, with exclusive UTF-8/LF
output and a text-free byte-linkage receipt. No database or network access.
See [the executable walkthrough and rights boundary](ADAPTER_GUIDE.md).

List's opt-in `--order recent|oldest` and strict whole-UTC-day `--from`/`--until`
use a versioned query-time rule without changing stored timestamps or the default
list output. See [time interpretation and pagination](BROWSE_BY_TIME.md).

`find` and standalone `conversation_search.py` accept `--from YYYY-MM-DD` and
`--until YYYY-MM-DD`: only bodies inside the inclusive UTC calendar-day window
are searched. Titles remain conversation-wide. See [time browsing](BROWSE_BY_TIME.md).

`stats --by-source` adds stored-row/conversation counts and declared timestamp
coverage per source in one read-only snapshot. Default `stats` is unchanged.
See [time browsing](BROWSE_BY_TIME.md).

`check-import` and `import_check.py` accept `--delta-output NEW_JSON` for an
exclusive private conversation delta sample file. Counts are always included.
See [re-import delta](REIMPORT_DELTA.md).

`review-titles --conversation ID` may repeat to explicitly select a bounded
identity subset before pagination. Other filters intersect; source-wide existing
title collision checks remain. See [selected title review](SELECTED_TITLE_REVIEW.md).

`show` and standalone `conversation_view.py show` accept `--output NEW_JSON`.
They save the unchanged selected view object as UTF-8 and print only a hash/byte
receipt. See [saved conversation JSON](SAVED_CONVERSATION_JSON.md).

For an actual fresh normalized-object replay rather than a live-DB self-check,
follow the [rebuild rehearsal](REBUILD_REHEARSAL.md).
Use separate absent DB paths; ingest is a write, and this guide does not make
existing-path ingestion exclusive or recreate title/review history.

For Python callers replaying retained export bytes, see [explicit byte replay](EXPORT_BYTE_REPLAY.md). This API supplies original parsing labels and
LF/CRLF serialization explicitly; the existing path-based CLI remains unchanged.
It is an import write API, not an exclusive new-DB or verified recovery command.

Use [automated declared-object rebuild](AUTOMATED_REBUILD.md)
with `python recap.py rebuild-archive MANIFEST --plan PLAN --objects DIR
--new-db NEW.sqlite --output NEW.json [--text]`. It never opens the original DB;
it exclusively publishes a checked new DB from explicit replay steps. Declared
title history is not rebuilt, and review state remains undeclared/unrestored.

### Private review view checkpoint

```text
usage: recap.py declare-review-checkpoint [-h] --source SOURCE --output OUTPUT [--declared-at DECLARED_AT] [--text]
```

Read one source snapshot and write a new private unsigned view cutoff, not a
review decision. `review-titles --since-checkpoint FILE` compares the entire
source before intersecting other filters; no archive mutation or automatic
advancement. See [checkpoint semantics and workflow](REVIEW_CHECKPOINT.md).

## Accepted-artifact cutoff

```text
usage: recap.py declare-checkpoint [-h] --source SOURCE --output OUTPUT [--declared-at DECLARED_AT] [--text]
```

```text
usage: recap.py changed-since [-h] --source SOURCE --checkpoint CHECKPOINT [--text]
```

Both commands require global `--db`; changed-since exits 1 with no delta when
the declared subset is not verified. See [IMPORT_CHECKPOINT](IMPORT_CHECKPOINT.md).

## build_manifest.py

```text
usage: build_manifest.py [-h] [--root ROOT] [--release RELEASE] [--date DATE] [--write NEW_PATH] [--expected-plan-sha256 HEX]
```

Read-only plan by default; a reviewed plan hash permits only a new outside-tree
manifest candidate. See [Build manifest](BUILD_MANIFEST.md).

Handled low-level execution failures use [fixed stderr diagnostics](ERROR_DIAGNOSTICS.md).
CLI usage and result-document failure statuses are unchanged.

## Message provenance cards

```text
usage: recap.py export-provenance [-h] --source SOURCE --conversation CONVERSATION --message MESSAGE --output OUTPUT [--declared-at DECLARED_AT] [--text]
```

```text
usage: recap.py check-provenance [-h] [--text] input
```

Both require global `--db`; check-provenance returns exit 1 for STALE.
See [message provenance](MESSAGE_PROVENANCE.md).

## Synthetic scaling checks and examples

```text
usage: make_scale_fixture.py OUTPUT_DIR --conversations N --messages M --seed INT
usage: benchmark.py FIXTURE_DIR --work-dir NEW_DIR --output NEW_JSON [--repetitions N]
```

The generator is `examples/make_scale_fixture.py`. The runner accepts only its
exact regenerated synthetic bytes, creates new scratch archives and exclusively
saves a private measurement receipt. See [SCALING](SCALING.md).

## Command catalogue

```text
usage: recap.py describe [-h] [{apply-title,changed-since,check-import,check-provenance,check-title-plan,declare-checkpoint,declare-recovery,declare-review-checkpoint,describe,describe-schema,export-normalized,export-provenance,export-title-plan,find,import,ingest,inspect,inspect-web-zip,list,list-export,prepare-web-export,preview-title,rebuild-archive,rehearse-recovery,render,render-queue,replay-local,review-state,review-titles,search,show,stats,suggest-attributed-title,suggest-branch-title,suggest-replay-title,suggest-title,title,title-adapter-dry-run,title-adapter-simulate,title-history,web-branch}]
```

No archive/input access; optional release metadata is not verification. See
[command catalogue](COMMAND_CATALOG.md).

## rebuild-archive usage

```text
usage: recap.py rebuild-archive [-h] --plan PLAN --objects OBJECTS --new-db NEW_DB --output OUTPUT [--text] input
```

See [command catalogue](COMMAND_CATALOG.md) and the matching workflow guide.

Global `--json-errors` precedes the subcommand and structures only caught execution
errors on stderr (exit 1). Default text, result-level JSON and usage errors are
unchanged. See [JSON_ERRORS](JSON_ERRORS.md).

## Read-only MCP stdio entry point

`python recap_mcp.py --db DB` starts an explicitly selected local foreground stdio
child. Its six DB-read tools exclude writes and file inputs. This is not a unified
recap.py subcommand, installation or client connection. Read [MCP_SERVER.md](MCP_SERVER.md)
for the tested JSON client configuration, pinned protocol and privacy/resource
boundaries. EOF exits; clients own timeouts.
