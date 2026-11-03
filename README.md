# recap-for-everyone

대화·에이전트 세션을 출처와 함께 보존하고 검색하는 로컬 도구와 설계입니다.
Portable, local-first conversation archives with provenance and read-only search.

## 공개 범위 / Scope

이 첫 공개본은 개인용 Recap의 **개념과 독립 실행 가능한 공통 핵심**을 분리한 출발점입니다.
개인용 시스템 전체의 배포본이나 모든 수집기의 이식판은 아닙니다.

| Included | Excluded |
|---|---|
| Normalized JSONL import, SQLite FTS search, source hash/line ledger | Real conversations, archives, databases, logs, user/device configuration |
| Existing generic local session parser and synthetic tests | Authentication bundles, browser profiles, cookies, credentials |
| Collection/index/publication separation and recovery design | Private service endpoints, account automation, SSH and scheduler setup |

## Quick start

Python 3.10+ with SQLite FTS5. No external Python dependencies, account or API key.
Run from the repository root:

```sh
python3 recap.py --db /tmp/recap-demo.sqlite ingest examples/conversations.jsonl --source demo
python3 recap.py --db /tmp/recap-demo.sqlite search orchard
python3 recap.py --db /tmp/recap-demo.sqlite stats
python3 -m unittest discover -v
```

Use a writable database path outside this public repository for your own data.
Input is UTF-8 JSONL: one message per line with `conversation_id`, `message_id`,
`role`, `timestamp`, `text` and optional `title`. Timestamps are retained as supplied;
the importer does not normalize, validate or filter dates. Search uses literal
AND-connected FTS5 terms rather than raw SQL or a user-supplied FTS expression.

`recap.py` imports only a file explicitly supplied by the operator. It does not crawl
home directories, access online accounts, collect credentials or push data anywhere.
The JSONL file is hashed from its original bytes; message rows retain the hash and
line locator. Repeated identical messages are idempotent; conflicting message
identities roll back the import batch instead of overwriting evidence.

`local_parser.py` retains the generic normalized agent-session parser and manifest
utilities. It is a library module, not an automatic collector. Its original local
snapshot schema is separate from the simplified `recap.py` schema; an adapter is
required to connect them. These are not interchangeable database formats.

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
`title_proposal.py preview/apply` for reviewed proposal application. The standalone
scripts remain supported with equivalent behavior. Only `inspect` can omit `--db`.

## Design

See [architecture](docs/ARCHITECTURE.md), [agent workflow](SKILL.md),
[publication boundary](PUBLICATION.md), and [security](SECURITY.md).
Only synthetic examples are distributed. Do not commit your resulting database.

## Rights

No third-party code, book text, article corpus or private database was deliberately
bundled in this extraction. No license has been selected by the owner yet;
public visibility is not an open-source license. See [rights](RIGHTS.md).

## Export and title workflow

`session_workflow.py` connects explicit local session JSONL and ChatGPT-style web
JSON exports (`id`, `mapping` nodes) to the existing index. Text nodes from all
branches are imported; original byte hashes, node/line locators and web parent IDs
are retained in `export_provenance`. Nontext content is not extracted. Keep original
exports for recovery. This is not online collection or a universal export parser.

```sh
python session_workflow.py --db ../demo.sqlite import examples/web-export.json --format web --source demo
python session_workflow.py --db ../demo.sqlite import examples/local-session.jsonl --format local --source local-demo
python session_workflow.py --db ../demo.sqlite title --source demo --conversation synthetic-chat
python session_workflow.py --db ../demo.sqlite title --source demo --conversation synthetic-chat --set "Orchard experiment plan" --expected-revision 0
```

Title preview is read-only. Suggestions are the first user request, whitespace
normalized and truncated to 80 characters; they are not semantic summaries.
Local display overrides retain previous titles without changing source messages.
Restore a prior title with `--set` to append an auditable reversal. The original
`recap.py search` still returns original message titles. Online rename, attachment
extraction, bulk rename and semantic title generation remain future work.

### Transactional imports and title preview leases

Adapter provenance now commits in the same SQLite transaction as messages and FTS.
A failed provenance insertion rolls back the whole import. Title previews return a
`revision`; CLI `--set` requires `--expected-revision REVISION`. A write lock covers
revision comparison and history insertion, so a stale preview cannot overwrite a
newer title. The Python API retains optional revision checking for compatibility;
callers should always supply it. Reversal is another checked title change.

## External title proposal contract

`title_proposal.py` supplies a local contract for an operator or future semantic
model adapter. **No semantic model is connected or called.**

```sh
python title_proposal.py --db ../demo.sqlite snapshot --source demo --conversation synthetic-chat
python title_proposal.py --db ../demo.sqlite preview proposal.json
python title_proposal.py --db ../demo.sqlite apply reviewed-preview.json
```

Save the preview JSON to `reviewed-preview.json` outside the repository. A proposal
requires `source`, `conversation`, `content_sha256` from snapshot, a single-line
`title`, `evidence_message_ids` referencing user messages, and `provider` equal to
`operator`, `external-adapter`, `synthetic-mock`, or `local-extractive`. Preview is read-only and returns
the expected title revision. Apply checks content under the same write lock as the
revision and title history insertion. The snapshot contains private messages; this
tool performs no external transmission. References and hashes do not establish
semantic title accuracy. Synthetic tests use a mock proposal, not model output.

## End-to-end and CI verification

`test_cli_e2e.py` runs the synthetic workflow through actual CLI subprocesses and
checks failed inputs and reproducible output. GitHub Actions runs standard-library
tests, publication scanning and manifest byte verification on Linux and Windows
with Python 3.10 and 3.12. Actions are commit-pinned; token permissions are read-only,
checkout does not persist credentials, no secrets or deployment steps are used.
The manifest describes LF-normalized published files, enforced by .gitattributes.
External model/search behavior and scientific meaning are not evaluated by CI.

## Find conversations by their current title

```sh
python conversation_search.py --db ../demo.sqlite "orchard plan" --source demo
```

This read-only search uses case-insensitive literal substring terms, AND-connected
across the current display title and all messages of each conversation. Renaming
immediately changes title matches; reverting removes matches for the former title.
Results include source/conversation identity, original and current title, revision,
message count, up to three message snippets with provenance, total matches and
truncation. Title matches rank first; remaining ordering is deterministic. Source
filters keep identically named conversations distinct. The implementation scans the selected archive row by row, retaining only bounded
result candidates and per-conversation term flags; it is not a semantic index.
`recap.py search` retains its original message-level FTS behavior.

## Read-only conversation views

Use the structured view to browse imported conversations and see reviewed local
names without replacing source evidence:

```sh
python conversation_view.py --db ../demo.sqlite list --source demo --limit 50 --offset 0
python conversation_view.py --db ../demo.sqlite show --source demo --conversation synthetic-chat
```

The inventory returns the original title, current display title, title revision and
message count. Sources remain separate even when conversation IDs match. Listing
uses binary source/conversation ordering and explicit offset pagination, with a
maximum page size of 1000. Each command reads one consistent database snapshot;
separate pages can change if imports occur between requests.

Details retain original message titles, normalized artifact hashes/line numbers,
and every recorded original-export hash, locator and parent node. Plain normalized
imports have an empty export-provenance list. Messages appear in archive insertion
order, not timestamp or active web-branch order. All imported text branches remain
visible; skipped nontext nodes are not reconstructed. These commands neither change
titles nor create a missing database, and perform no network access. JSON output can
contain private message text: keep it outside the public repository.

## Bounded search and SQL pagination

Conversation search keeps at most two result buckets of `limit` conversations,
three snippets per result, and the current message while scanning. AND terms may
match across different messages, and current-title hits still rank first. Search
still reads every selected message; runtime scales with archive size and SQLite title-history aggregation.
Latest-title and message cursors are merged in source/conversation order, avoiding
a separate full title-history scan for every searched conversation. SQLite native caches and the largest individual message are not
covered by the Python buffering bound.

Conversation list pagination happens in SQLite before Python result construction
or title lookups. Detail queries filter to the exact source/conversation. Counts
and offset pagination can still scan many rows, and a detail view intentionally
returns the whole selected conversation. These are memory improvements, not a
claim of constant-time queries, a full-text index replacement, or a benchmark on
private archives. No schema migration or database writes are required.

## Web-export validation boundaries

Web import rejects duplicate JSON object keys, invalid parent references and parent
cycles, including cycles through nodes without messages. Iterative validation
supports deep parent chains without Python recursion. Valid forks retain their
original mapping order and parent IDs; this does not select an active branch.
Malformed message authors and timestamps produce clean input errors before any
archive write. Supported roles remain user, assistant, system and tool. Numeric
epoch zero is preserved as `"0"`; timestamps otherwise remain unnormalized source
values. Nontext content is still not extracted, and no online account is accessed.

Upgrade boundary: older versions stored numeric epoch zero as `unknown`. Reimport
of those message identities now raises a conflict rather than rewriting existing
evidence. Keep the old archive; use a separately selected new database for a clean
rebuild from retained exports if epoch-zero correctness is needed. No automatic
migration is performed. Empty-string timestamps are now rejected explicitly.

Reviewed title-proposal application requires an explicit nonnegative integer
`expected_revision`. Missing, null, boolean, string or fractional revisions are
rejected rather than disabling the stale-preview guard. The lower-level `titles`
Python API retains its documented optional revision argument for compatibility;
external adapters should use the checked proposal workflow. Missing/unreadable
SQLite databases produce clean CLI errors and are not created by preview/snapshot.

## Generate a local title excerpt for review

```sh
python title_suggestion.py --db ../demo.sqlite --source demo --conversation synthetic-chat > ../proposal.json
python title_proposal.py --db ../demo.sqlite preview ../proposal.json > ../reviewed-preview.json
# Inspect the suggested title and evidence before applying:
python title_proposal.py --db ../demo.sqlite apply ../reviewed-preview.json
```

The local generator selects the first usable user message that is not an exact
match for a small built-in English/Korean greeting list. It normalizes whitespace,
removes control/format characters from the proposed label only, and takes up to 80
characters. If all usable user messages are greetings, the output explicitly marks
that fallback. No usable user text produces an error rather than an assistant-based
title. Source messages are never modified.

Output is a `local-extractive` proposal with one user evidence ID and the conversation
content fingerprint. Generating and previewing are read-only; applying still requires
the reviewed revision and unchanged content. This is a deterministic excerpt, not a
semantic summary, intent classifier or model adapter. It can miss the main topic or
select low-value text, so review remains necessary. No API key, paid service, model
call, automatic rename or external data transmission is involved. Proposal files may
contain private excerpts and must stay outside the public repository.

## Unambiguous JSON inputs

Web exports, local session JSONL, normalized JSONL and title-proposal JSON files now
share duplicate-object-key rejection. This includes nested objects and equivalent
escaped key spellings, while the same key in separate objects remains valid. An
ambiguous record fails before database access rather than silently selecting the
last value. Local/normalized JSONL errors identify the physical line; duplicate-key
diagnostics do not echo the key or value. Original bytes/hashes and line provenance
remain unchanged for accepted inputs. Previously accepted ambiguous files must be
corrected by their owner or re-exported; they are not automatically repaired.
Duplicate keys are rejected even when their values match or occur in unused
metadata. This decoder is duplicate-safe, not a full RFC-strict or resource-limited
JSON parser; ordinary Python JSON depth/size behavior still applies.

## Inspect an export before importing

```sh
python session_workflow.py inspect examples/web-export.json --format web
python session_workflow.py inspect examples/local-session.jsonl --format local
```

Inspection validates and extracts in memory without opening or creating a database,
even if `--db` is supplied. It reports the original byte hash/size, extracted message
and conversation counts, and role counts without outputting message text, titles or
conversation IDs. Web coverage reports mapping nodes without extracted text; local
coverage reports observed records, session metadata counts, and records that did
not produce a message. These counts include legitimate metadata/nontext records,
not just errors, and do not prove complete capture. Zero extraction produces a
warning so an unsupported/empty source is not mistaken for a populated archive.

Import receipts include the same `coverage` object alongside existing record and
insert counts. Both are calculated from the same frozen source bytes. Inspection
has the same parsing/memory limits as import and does not reserve an input file;
if the original changes afterward, compare the import receipt's original hash.
Import/title commands still require an explicit `--db` path. No new source scanning,
account access or external transmission is performed.
Inspection reports extracted occurrences, not newly inserted unique messages.
`parser_admission_status` describes parsing only, never database persistence. A
successful inspection cannot predict conflicts with an existing archive or later
filesystem/database failures.

## Consistent local title validation

Manual title changes and proposal previews share the same validation: nonempty
single-line text up to 200 Unicode code points, with no control characters (Unicode Cc), Unicode
line/paragraph separators or surrogate code points. Valid Unicode and emoji joiners
are retained, as are intentional leading/trailing spaces. Existing original titles
and history are not rewritten; newly applying a formerly accepted multiline/control
title now fails. Reversal must also use a valid single-line title.

Title writes open an existing database only. A mistyped/missing database path fails
cleanly instead of creating an empty file. Import remains the explicit operation
that may create a new archive.
Unicode format characters (Cf), including emoji joiners and bidi controls, remain
permitted. This validation is not visual-spoofing protection.

## Verify the complete publication inventory

`python verify_manifest.py` now rejects files outside the publication allowlist,
not only changed/missing listed bytes. It also rejects malformed metadata, unsafe
paths, case-insensitive path aliases and symlinks. Only `.git` metadata and generated
`__pycache__/*.pyc` files are ignored. Unexpected text/hidden files and non-bytecode
cache contents fail verification.

Run publication checks on the exact clean code candidate to be published. Local
handoff bundles, private test output and other unlisted working files must remain
outside that candidate. Do not add private files to the manifest just to make a
check pass. This inventory check supplements the limited secret/type scanner and
human content review; it does not establish anonymity or legal clearance.

## Preserve repeated original occurrences

Identical explicit message IDs are still deduplicated into one message, but every
accepted original line/node locator is now retained in the additive
`export_occurrences` ledger. The legacy `export_provenance` table remains unchanged
for compatibility and can hold only one locator per message/original-file hash.
Structured `show` views union and deduplicate both ledgers, so older archives and
legacy-only records remain readable.

On the next export import, the new occurrence table is created and existing legacy
rows are copied into it in the same write transaction as the import. No legacy table,
trigger, index or message is replaced. A failed import rolls back the new ledger and
its rows. Reimporting retained original exports can recover repeated locations that
older versions collapsed; missing locations cannot be reconstructed without those
exports. Direct SQL consumers needing complete occurrences should use the new ledger
plus legacy-only rows, or the structured view, rather than only the old table.

## Provider-neutral title generation contract

```sh
python title_adapter.py --db ../demo.sqlite --source demo --conversation synthetic-chat generate > ../proposal.json
python title_proposal.py --db ../demo.sqlite preview ../proposal.json > ../reviewed-preview.json
# Inspect the proposed title and evidence before applying:
python title_proposal.py --db ../demo.sqlite apply ../reviewed-preview.json
```

The default adapter is local extraction. A deterministic mock can validate response
contracts; **no semantic model or external transport is connected**. Generation is
read-only and separate from preview/apply. The adapter freezes a bounded recent-user
payload and validates that returned evidence IDs were actually included. Unlike the
standalone full-conversation excerpt command, local adapter selection uses only that
bounded payload. Semantic title quality has not been evaluated.

The declared external path requires both an explicit enabled setting and consent
bound to provider, normalized HTTPS endpoint, model and the exact outbound payload
hash. Even with both, this release returns `EXTERNAL_NOT_CONFIGURED` without sending
anything. There is no credential creation/storage, paid API call or automatic retry.
`prepare` prints private user text for local review only; keep request, response and
proposal files outside the public repository.

See [adapter contract and limits](docs/TITLE_ADAPTER.md) for payload limits,
consent semantics, subprocess deadlines, fixed error codes and future transport
requirements. Local/mock tests do not establish actual model quality or external
service reliability.
