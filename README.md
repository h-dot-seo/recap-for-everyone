# recap-for-everyone

[한국어 안내](docs/README.ko.md)

대화·에이전트 세션을 출처와 함께 보존·검색하고, 검토를 거친 로컬 표시 제목으로 정리하는 로컬 도구와 설계입니다.
Portable, local-first conversation archives with provenance, read-only search and
reviewed local display-title changes.

## 공개 범위 / Scope

이 첫 공개본은 개인용 Recap의 **개념과 독립 실행 가능한 공통 핵심**을 분리한 출발점입니다.
개인용 시스템 전체의 배포본이나 모든 수집기의 이식판은 아닙니다.

| Included | Excluded |
|---|---|
| Normalized JSONL import, SQLite FTS search, source hash/line ledger | Real conversations, archives, databases, logs, user/device configuration |
| Existing generic local session parser and synthetic tests | Authentication bundles, browser profiles, cookies, credentials |
| Reviewed local display-title suggestions, preview/apply and title history | Remote or bulk renaming, model calls and semantic summarization inside this repository |
| Collection/index/publication separation and recovery design; `declare-recovery` manifest plus `rehearse-recovery` of a restored copy with a retained receipt | Private service endpoints, account automation, SSH and scheduler setup, remote backup fetch and decryption |

## Start with your export

First use [installation and runtime checks](docs/INSTALL.md) to obtain the code,
choose your Python launcher and verify in-memory SQLite FTS5. The workflow
described here is on the default `main` branch since 2026-11-08.

New to this tool? Follow [Start here: ZIP/local file to a findable title](docs/START_HERE.md).
It chooses the right input path and walks through 24 invented conversations, explicit
review, defer/revisit, one local title change and search. The commands are tested
end-to-end. No model, account or remote rename is involved.

## Quick start for already-normalized JSONL

Python 3.10+ compatibility with SQLite FTS5; choose a currently supported runtime.
No external Python dependencies, account or API key. Run from the repository root,
substituting your chosen launcher for `python`. Use a new scratch directory:

```sh
mkdir ../recap-normalized-demo
python recap.py --db ../recap-normalized-demo/archive.sqlite ingest examples/conversations.jsonl --source demo
python recap.py --db ../recap-normalized-demo/archive.sqlite search orchard
python recap.py --db ../recap-normalized-demo/archive.sqlite stats
python -m unittest discover -v
```

Use a writable database path outside this public repository for your own data.
Input is UTF-8 JSONL: one message per line with `conversation_id`, `message_id`,
`role`, `timestamp`, `text` and optional `title`. For opt-in time ordering and UTC windows, see [browse by time](docs/BROWSE_BY_TIME.md).
Timestamps are retained as supplied;
the importer does not normalize, validate or filter dates. Search uses literal
AND-connected FTS5 terms rather than raw SQL or a user-supplied FTS expression.

`recap.py` imports only a file explicitly supplied by the operator. It does not crawl
home directories, access online accounts, collect credentials or push data anywhere.
The JSONL file is hashed from its original bytes; message rows retain the hash and
line locator. Repeated identical messages are idempotent; conflicting message
identities roll back the import batch instead of overwriting evidence.

## One CLI for the common workflow

```sh
python recap.py inspect examples/web-export.json --format web
python recap.py --db ../demo.sqlite import examples/web-export.json --format web --source demo
python recap.py --db ../demo.sqlite list --source demo
python recap.py --db ../demo.sqlite find orchard --source demo
python recap.py --db ../demo.sqlite show --source demo --conversation synthetic-chat
python recap.py --db ../demo.sqlite suggest-title --source demo --conversation synthetic-chat
python recap.py --db ../demo.sqlite title --source demo --conversation synthetic-chat
```

`recap.py --help` lists the common commands. `find` searches current conversation
titles and text; the original `search` command still performs message-level FTS.
`title` without `--set` is read-only, and applying `--set` requires the preview's
`--expected-revision`. `suggest-title` produces a proposal only; continue through
`recap.py --db ... preview-title proposal.json` then
`recap.py --db ... apply-title reviewed.json` for reviewed proposal application.
The notes on saved `--output` files, evidence review, pre-import discovery and
supplied proposals continue in [workflows](docs/WORKFLOWS.md#the-common-title-workflow-in-one-cli).

## Commands at a glance

`--db DB` precedes the subcommand; `inspect`, `list-export`, `inspect-web-zip`,
`prepare-web-export`, `replay-local`, `web-branch` and `rehearse-recovery` run
without a database. Nothing below contacts a service, calls a model or renames a
conversation in its original application.

| Task | Commands | Guide |
|---|---|---|
| Check the runtime first | `python runtime_check.py`, `python recap.py --help`, `python verify_manifest.py` | [Install](docs/INSTALL.md) |
| Choose a part of a downloaded ZIP | `recap.py inspect-web-zip ZIP`, `recap.py prepare-web-export ZIP --member NAME --output NEW_FILE` | [ZIP inventory](docs/WEB_ZIP_INVENTORY.md) |
| Find IDs and coverage before importing | `recap.py list-export INPUT --format FORMAT`, `recap.py inspect INPUT --format FORMAT` | [Export inventory](docs/EXPORT_INVENTORY.md) |
| Import an export or normalized JSONL | `recap.py --db DB import INPUT --format FORMAT --source SOURCE`, `ingest`, `check-import` | [Input scope](docs/INPUT_SCOPE.md) |
| Export portable message text | `recap.py --db DB export-normalized --source SOURCE --output NEW_JSONL` (optional `--conversation ID`) | [Normalized export](docs/EXPORT_NORMALIZED.md) |
| Read a saved title queue | `recap.py render-queue QUEUE.json --output NEW_FILE` | [Saved queue HTML](docs/RENDER_QUEUE.md) |
| Save a readable local view | `recap.py --db DB render --source SOURCE --conversation ID --format markdown --output NEW_FILE` (or `--format html`) | [Markdown](docs/RENDER_MARKDOWN.md), [HTML](docs/RENDER_VIEWS.md) |
| Inspect the current archive layout | `recap.py --db DB describe-schema` | [Schema reference](docs/SCHEMA.md) |
| Search and read | `recap.py --db DB find QUERY`, `list`, `show --source SOURCE --conversation ID`, `search`, `stats` | [Search excerpts](docs/SEARCH_EXCERPTS.md) |
| Propose a local title | `recap.py --db DB suggest-title`, `suggest-branch-title`, `suggest-replay-title`, `suggest-attributed-title` | [Title walkthrough](docs/TITLE_WALKTHROUGH.md) |
| Review a page and record decisions | `recap.py --db DB review-titles --source SOURCE`, `review-state` | [Review queue](docs/TITLE_REVIEW_QUEUE.md) |
| Preview, apply and audit one change | `recap.py --db DB preview-title PROPOSAL`, `apply-title REVIEWED`, `title`, `title-history` | [Review hints](docs/TITLE_REVIEW_HINTS.md) |
| Read a web branch or project retained turns | `recap.py web-branch INPUT --conversation ID`, `recap.py replay-local INPUT` | [Workflows](docs/WORKFLOWS.md#titles-from-a-verified-branch-retained-turns-or-source-labels) |
| Prepare a provider-neutral request offline | `python title_adapter.py --db DB --source SOURCE --conversation ID prepare`, `complete-response` | [Title adapter](docs/TITLE_ADAPTER.md) |
| Plan a manual title transfer | `recap.py --db DB export-title-plan`, `check-title-plan`, `title-adapter-dry-run`, `title-adapter-simulate` | [Transfer contract](docs/TITLE_TRANSFER.md) |
| Declare before a backup, rehearse after a restore | `recap.py --db DB declare-recovery --output MANIFEST`, `recap.py rehearse-recovery MANIFEST --restored-db COPY --output RECEIPT` | [Recovery rehearsal](docs/RECOVERY_REHEARSAL.md) |

Every script and subcommand with its exact usage line is in the
[command reference](docs/COMMANDS.md). The standalone scripts (`session_workflow.py`,
`conversation_search.py`, `title_proposal.py` and the others listed there) remain
supported with equivalent behavior. Layout: the repository root holds the entry points
only (`recap.py`, the standalone scripts, `runtime_check.py`, `verify_manifest.py`,
`audit_publication.py`, `build_manifest.py`); the implementation modules live in the `recaplib/` package and
the test suite in the `tests/` package, both reached from the root, where
`python -m unittest discover -v` still runs the whole suite.

See [Markdown views](docs/RENDER_MARKDOWN.md) and [HTML views](docs/RENDER_VIEWS.md)
for selection, provenance and display boundaries.

Read-only metadata inspection describes the current archive layout without creating
lazy tables. See [the schema reference](docs/SCHEMA.md) before direct SQL reads;
counts and schema names can be private, and this is not a stability guarantee.

See [saved queue views](docs/RENDER_QUEUE.md) for original-file binding, private
output precautions and a tested synthetic walkthrough.

See [the normalized input contract](docs/NORMALIZED_JSONL.md) before preparing converted JSONL.
Use `inspect INPUT --format normalized` for a database-free dry run, and
`check-import INPUT --format normalized --source SOURCE` with an existing archive.
Bind later `ingest` with `--expected-sha256 HASH`.
The [invented adapter illustration](docs/ADAPTER_GUIDE.md) demonstrates one
synthetic conversion, not real-vendor compatibility or a reuse license.

See [normalized export](docs/EXPORT_NORMALIZED.md) for private, text-only,
re-ingestible JSONL. This derived copy does not replace original exports or backups.

## Documentation

- [Browse by time](docs/BROWSE_BY_TIME.md): opt-in list ordering/UTC windows with explicit timestamp interpretation.
- [Invented adapter illustration](docs/ADAPTER_GUIDE.md): synthetic conversion, byte receipts, tested walkthrough and maintainer checklist.
- [Normalized input contract](docs/NORMALIZED_JSONL.md): accepted fields, read-only diagnostics, hash-bound ingest and normalized-file provenance.

- [Normalized export](docs/EXPORT_NORMALIZED.md): deterministic text-only source or conversation copies from one read-only snapshot.

- [Saved queue views](docs/RENDER_QUEUE.md): inert HTML without opening a database.

- [Schema reference](docs/SCHEMA.md): read-only metadata inspection and tested SQL for the current layout.
- [Markdown views](docs/RENDER_MARKDOWN.md): readable Unicode with fenced metadata and bodies, selected scope and private no-overwrite receipts.
- [HTML views](docs/RENDER_VIEWS.md): read-only Unicode conversation views with private no-overwrite receipts.

- [Start here](docs/START_HERE.md): tested first run from a ZIP or local file to a findable local title.
- [Install](docs/INSTALL.md): get the code, choose a Python launcher, check SQLite FTS5.
- [Title walkthrough](docs/TITLE_WALKTHROUGH.md): web-branch and Codex retained-turn titles in one CLI.
- [Command reference](docs/COMMANDS.md): every script and subcommand with its exact usage line.
- [Workflows](docs/WORKFLOWS.md): the per-feature narratives, grouped by workflow.
- [한국어 안내](docs/README.ko.md): 목적, 공개 범위, 빠른 시작, 주요 명령, 경계, 문서 색인.
- [Architecture](docs/ARCHITECTURE.md): authority layers, identifiers, import transaction, read-only boundary, recovery criteria.
- [ZIP inventory](docs/WEB_ZIP_INVENTORY.md): choose a conversation JSON part of a downloaded ZIP without decompressing it.
- [Prepare a web export](docs/PREPARE_WEB_EXPORT.md): validate one ZIP member and publish it as a new local file.
- [Export inventory](docs/EXPORT_INVENTORY.md): IDs, titles and coverage before importing; find a session by remembered text.
- [Input scope](docs/INPUT_SCOPE.md): supported formats, selected-conversation import, hash binding, failure boundaries.
- [Import conflicts](docs/IMPORT_CONFLICTS.md): diagnose a reimport against an existing archive without changing it.
- [Source text compatibility](docs/SOURCE_TEXT_COMPATIBILITY.md): UTF-8 signatures and physical line handling.
- [Search excerpts](docs/SEARCH_EXCERPTS.md): match-centered samples, offsets and coverage fields.
- [Search pagination](docs/SEARCH_PAGINATION.md): continue a conversation search with cursors.
- [Canonical Unicode search](docs/CANONICAL_UNICODE_SEARCH.md): opt-in matching of canonically equivalent text.
- [Export-scoped search](docs/EXPORT_SCOPED_SEARCH.md): restrict body matches to one original export hash.
- [Title history search](docs/TITLE_HISTORY_SEARCH.md): find a conversation by an earlier local title.
- [Omitted search messages](docs/OMITTED_SEARCH_MESSAGES.md): browse matching messages the samples left out.
- [Message selection](docs/MESSAGE_SELECTION.md): read one message, a bounded page or neighbors around a hit.
- [Title document files](docs/TITLE_DOCUMENT_FILES.md): save proposals, queues and previews with `--output`, never overwriting.
- [Title review queue](docs/TITLE_REVIEW_QUEUE.md): review a page of local title proposals.
- [Title review hints](docs/TITLE_REVIEW_HINTS.md): advisory hints, explicit wording, scoped message choice, Unicode limits.
- [Title review evidence](docs/TITLE_REVIEW_EVIDENCE.md): opt-in cited evidence at preview time.
- [Title review state](docs/TITLE_REVIEW_STATE.md): explicit open, skipped and deferred decisions.
- [Title history view](docs/TITLE_HISTORY_VIEW.md): earlier local titles without opening message bodies.
- [Supplied title review](docs/SUPPLIED_TITLE_REVIEW.md): review web, local and supplied proposal files together.
- [Source-attributed titles](docs/SOURCE_ATTRIBUTED_TITLES.md): titles from explicitly user-labeled source parts.
- [Attributed message selection](docs/ATTRIBUTED_MESSAGE_SELECTION.md): choose a specific source-labeled request or occurrence.
- [Adapter message selection](docs/ADAPTER_MESSAGE_SELECTION.md): use a chosen request in the saved-response workflow.
- [Title adapter](docs/TITLE_ADAPTER.md): provider-neutral generation contract; local and mock execution only.
- [Saved title response](docs/SAVED_TITLE_RESPONSE.md): turn a separately obtained response into a reviewable proposal.
- [Title transfer](docs/TITLE_TRANSFER.md): mock-only platform title transfer contract.
- [Recovery rehearsal](docs/RECOVERY_REHEARSAL.md): declare a live archive before a backup, rehearse a restored copy.
- [Validation history](docs/VALIDATION_HISTORY.md): every dated validation entry since the first release.

## Design

See [architecture](docs/ARCHITECTURE.md), [agent workflow](SKILL.md),
[publication boundary](PUBLICATION.md), [security](SECURITY.md), [rights](RIGHTS.md)
and the [validation record](VALIDATION.md).
Only synthetic examples are distributed. Do not commit your resulting database.

## Rights

No third-party code, book text, article corpus or private database was deliberately
bundled in this extraction. No license has been selected by the owner yet;
public visibility is not an open-source license. See [rights](RIGHTS.md).

For an actual fresh normalized-object replay rather than a live-DB self-check,
follow the [rebuild rehearsal](docs/REBUILD_REHEARSAL.md).
Use separate absent DB paths; ingest is a write, and this guide does not make
existing-path ingestion exclusive or recreate title/review history.

For Python callers replaying retained export bytes, see [explicit byte replay](docs/EXPORT_BYTE_REPLAY.md). This API supplies original parsing labels and
LF/CRLF serialization explicitly; the existing path-based CLI remains unchanged.
It is an import write API, not an exclusive new-DB or verified recovery command.

Use [automated declared-object rebuild](docs/AUTOMATED_REBUILD.md)
with `python recap.py rebuild-archive MANIFEST --plan PLAN --objects DIR
--new-db NEW.sqlite --output NEW.json [--text]`. It never opens the original DB;
it exclusively publishes a checked new DB from explicit replay steps. Declared
title history is not rebuilt, and review state remains undeclared/unrestored.

## Source-wide review view cutoff

Use `declare-review-checkpoint` and `review-titles --since-checkpoint` for an
explicit unsigned source snapshot, not review completion or batch approval.
Content/title comparisons and private-file limits are described in
[the checkpoint guide](docs/REVIEW_CHECKPOINT.md). Existing per-conversation review-state
decisions remain independent; no checkpoint changes the archive.

## Accepted-artifact import cutoff

`declare-checkpoint` and `changed-since` verify a declared source artifact subset
before returning ID-free import-delta counts. They do not approve imports, record
review completion or mutate the archive. See [the cutoff guide](docs/IMPORT_CHECKPOINT.md).

For contributor byte inventories, `build_manifest.py` reports a read-only plan.
After reviewing it, an exact plan hash can create a separate new candidate outside
the checkout, never overwrite the manifest or approve publication. See
[manifest generation](docs/BUILD_MANIFEST.md).

Handled CLI OS/SQLite/decoder failures use fixed, path-free stderr diagnostics.
Existing validation messages and stdout result failures keep their contracts;
exit 1 alone does not establish that no write occurred. See
[failure diagnostics](docs/ERROR_DIAGNOSTICS.md).

For a private pointer without message text or titles, use `export-provenance`
for one explicit message and `check-provenance` to recheck it. Locator hashes
do not establish authorship, consent, retrieval or publication evidence. See
[message provenance cards](docs/MESSAGE_PROVENANCE.md).

Adapter imports avoid decoding their generated JSONL a second time while preserving
artifact hashes, source lines and admission checks. See
[adapter import cost and boundaries](docs/ADAPTER_IMPORT_COST.md); this is not a
bounded-memory or speed guarantee.

Use the optional [synthetic scaling observations](docs/SCALING.md) to measure
import, query, review and recovery operations on generated fictional input in new
scratch archives. Measurements stay in a private receipt, not a speed guarantee.
