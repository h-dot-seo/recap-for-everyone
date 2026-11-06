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

## Start with your export

First use [installation and runtime checks](docs/INSTALL.md) to get the workflow
branch, choose your Python launcher and verify in-memory SQLite FTS5. The default
`main` extraction does not contain all commands described here.

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
`recap.py --db ... preview-title proposal.json` then
`recap.py --db ... apply-title reviewed.json` for reviewed proposal application.
Use `--output NEW_JSON` on title suggestions, review queues and previews to create
UTF-8 files without overwriting existing paths or relying on shell redirection.
Stdout then contains a receipt; open the saved document before applying.
Editor-saved title proposals, queues and previews can contain one initial UTF-8
BOM; reading preserves file bytes and all evidence/revision checks. UTF-16 and
malformed JSON remain unsupported.

[Native title JSON files](docs/TITLE_DOCUMENT_FILES.md) lists supported commands
and filesystem limits. The default stdout mode remains available.
Add `preview-title --with-evidence` for an explicitly requested private view of
up to five cited user-message excerpts and bounded original provenance.
[Evidence review](docs/TITLE_REVIEW_EVIDENCE.md) explains truncation and why raw
excerpts are not automatically the exact passages used by scoped generation.
If `find` omits matching messages, its conversation cursor does not page those
body samples. [Browse the remaining raw messages](docs/OMITTED_SEARCH_MESSAGES.md)
with scoped `show` pages before choosing a later user request for a title.
For a useful request later in a verified web branch or retained local turns, add
`--message ARCHIVED_ID` to `suggest-branch-title` or `suggest-replay-title`.
Selection stays inside the verified scope and never falls back to another message;
the full conversation fingerprint and separate preview/apply checks remain.
See [scoped message selection](docs/TITLE_REVIEW_HINTS.md#choose-a-later-message-inside-a-verified-branch-or-retained-history).
The standalone scripts remain supported with equivalent behavior. `inspect`,
`list-export`, `web-branch`, `replay-local`, `prepare-web-export` and `inspect-web-zip` can omit `--db`.

To choose a conversation before importing, run `recap.py list-export INPUT --format web`
(or use `local`/`local-codex`). It lists exact IDs, existing web titles and selection
blockers without a database or message-body output. Titles and IDs may still be
private. Add `--contains "remembered text"` to find a literal part of an existing
web title or session ID before paging; `--canonical-unicode` optionally matches
canonical Unicode equivalents. This does not search bodies or skip full-file
validation. See [export inventory](docs/EXPORT_INVENTORY.md).
Carry its `original_sha256` into `--expected-export-sha256` on later inventory,
inspection or import commands when you want to reject changed source bytes.
This optional consistency check does not replace format validation or authorization.
For a reimport into an existing archive, `check-import INPUT --format FORMAT --source SOURCE`
with `--db DB` reports title-only, text and metadata identity conflicts without
changing the archive. [Conflict diagnostics](docs/IMPORT_CONFLICTS.md) explain
bounded samples, duplicate occurrences and why a clear check is only advisory.
Use repeatable `review-titles --proposal FILE` options to review existing web-branch,
local-attributed, operator or model proposal files together. Missing or stale
candidates remain unavailable rather than reverting to raw excerpts. The
[web/local walkthrough](docs/SUPPLIED_TITLE_REVIEW.md) connects these proposals
to current titles, collision checks, one-at-a-time preview/apply and search.
Add `--supplied-only` to filter to those candidate identities before pagination
when the archive contains many other conversations. Whole-source title collision
checks remain active.

Start with the [two-format title walkthrough](docs/TITLE_WALKTHROUGH.md) for
copyable synthetic web and Codex local examples, expected results and recovery
steps. No account, API key or network connection is needed.

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

Title preview is read-only against the archive; `--output` explicitly creates a
new local JSON file. The informational `title` command and `suggest-title`
share the same first-non-greeting user excerpt, with whitespace/control cleanup
and an 80-code-point limit; they are not semantic summaries. Greeting-only inputs
retain a greeting fallback. With no usable user text, `title` shows an informational
`Untitled conversation` placeholder while proposal generation still rejects.
If that first request is too generic, inspect a later user message and pass its
exact ID with `suggest-title --message ID` to choose the excerpt evidence yourself.
This uses one raw archived user message, keeps the entire conversation fingerprint
and the same 80-code-point cap, and still requires preview/apply. It does not infer
relevance or establish branch/replay/attribution scope. See the [tested example and
selection limits](docs/TITLE_REVIEW_HINTS.md#choose-a-more-informative-user-message).
Title reads return current/original titles, suggestions and revision history from
one database snapshot. Separate commands can observe later changes.
Local normalization parses its existing byte snapshot directly, avoiding a temporary
source-file copy during inspection and source-backed title reads. Record errors now
point to the selected basename and physical line. Hashes, fallback IDs and parsing
rules are unchanged. Export import also passes normalized bytes directly to the
archive writer instead of staging a second JSONL file. See
[local snapshot parsing](docs/INPUT_SCOPE.md#local-snapshot-parsing-and-error-locations).

Local parsing now rejects malformed known response envelopes before archive work;
valid unsupported records remain counted skips. See [input boundaries](docs/INPUT_SCOPE.md).
Typed `local-codex` content also rejects malformed present type tags instead of
silently losing a user request; missing tags and valid unknown variants retain
their documented compatibility skips. Errors identify the physical record line.
Web/local identity aliases must agree exactly when both are supplied, and malformed
local message IDs cannot silently become filename/line IDs. Missing/null/empty
fallback remains explicit compatibility. The same checks apply to inventory,
selection and source-backed title workflows before archive access. See
[source identity rules](docs/INPUT_SCOPE.md#source-identities-must-resolve-without-guessing).
Python title preview/apply also detach caller-owned JSON and require text identities
to prevent mutable-input substitutions and SQLite type coercion.
[Review input snapshots](docs/TITLE_REVIEW_HINTS.md) explain the unsigned-document limits.
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

Conflicting repeated identities within an incoming normalized batch now fail before
SQLite connection/schema creation, while identical repeats and locked comparisons
against existing records retain their behavior. JSON decoder recursion errors also
become clean validation failures rather than tracebacks. See the [precise failure
boundaries](docs/INPUT_SCOPE.md#clean-failure-for-decoder-nesting-and-conflicting-incoming-records);
these checks are not a general memory limit or a guarantee about every I/O failure.

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

If copied Korean or accented text looks identical but does not match, opt in with
`find --canonical-unicode`. [Canonical Unicode search](docs/CANONICAL_UNICODE_SEARCH.md)
matches composed/decomposed equivalents while preserving original evidence and
covering snippet offsets. The default remains unchanged; cursor pages must keep
the same mode and runtime Unicode version.

Use `find --text-role user` (or `assistant`, `system`, `tool`) to search only
message bodies of that role. Titles remain conversation-wide metadata; a
conversation must contain a message satisfying the role and any export filter.
Message counts and samples describe that filtered set. Cursor pages must retain
the same role filter.

Large result sets support [cursor pagination](docs/SEARCH_PAGINATION.md). Copy
`next_cursor` into `find --cursor TOKEN` with the same query and filters to continue
past the first page, including more than 1,000 matches. Title-first ranking and
bounded evidence samples remain unchanged; changed result membership/order requires
a fresh search. Each page reads fresh evidence, not a saved content snapshot.

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

After finding a message, `show --around-message ID --before 2 --after 2` opens
[bounded raw neighbors](docs/MESSAGE_SELECTION.md) without locating its page offset.
This explicit broader view stays within the chosen source/conversation, preserves
provenance, and does not reconstruct branches, turns or an export-specific snapshot.
Exact `--message` behavior remains unchanged.

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

Source readers also support [one initial UTF-8 signature and consistent physical
line handling](docs/SOURCE_TEXT_COMPATIBILITY.md). Original bytes, byte counts,
hashes and line provenance remain intact. This covers source import/inventory and
verified title selections without guessing encodings or relaxing JSON/replay checks.

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
Python API retains its documented optional revision argument for compatibility:
`None` still omits that lower-level write guard. Supplied revisions must now be
exact nonnegative Python integers, not booleans or floats that compare equal.
Its source/conversation identities must be valid Unicode strings, never coerced
numbers or booleans. Invalid values fail before database access; accepted text
identities are not trimmed, normalized or case-folded. These checks deliberately
narrow malformed direct API calls, without retroactively repairing old title writes.
External adapters should use the checked proposal workflow. Missing/unreadable
SQLite databases produce clean CLI errors and are not created by preview/snapshot.

## Generate a local title excerpt for review

```sh
python title_suggestion.py --db ../demo.sqlite --source demo --conversation synthetic-chat --output ../proposal.json
python title_proposal.py --db ../demo.sqlite preview ../proposal.json --output ../reviewed-preview.json
# Inspect the suggested title and evidence before applying:
python title_proposal.py --db ../demo.sqlite apply ../reviewed-preview.json
```

The local generator selects the first usable user message that does not match a
small built-in English/Korean greeting list after NFC normalization, case folding
and the existing punctuation trimming. NFC applies only to this comparison, so
decomposed Korean greetings do not hide the next meaningful request. It normalizes
whitespace and replaces control/format characters in the proposed label with spaces,
except U+200C ZWNJ and U+200D ZWJ, which are preserved for text shaping and joined
emoji. It takes up to 80 Unicode code points, not complete grapheme clusters.
The returned prefix must itself contain an alphanumeric code point; otherwise that
message is skipped rather than producing an invisible or punctuation-only title.
If all usable user messages are greetings, the output explicitly marks
that fallback. No usable user text produces an error rather than an assistant-based
title. Source messages are never modified.

The selected label retains its original normalization and join controls; it is
not sanitized or guaranteed to render identically everywhere. Review hints still
flag format characters. Truncation can split an emoji or combining sequence, and
other format characters, including emoji tags, retain the existing space-replacement
behavior. See [Unicode excerpt boundaries](docs/TITLE_REVIEW_HINTS.md#unicode-excerpt-boundaries).

Output is a `local-extractive` proposal with one user evidence ID and the conversation
content fingerprint. Generating and previewing are read-only against the archive; applying still requires
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
metadata. All decoded string keys and values also reject unpaired Unicode
surrogates, including unused metadata. Valid escaped surrogate pairs (for example,
emoji), Korean text and ordinary Unicode values remain unchanged. Inspection and
import use this same check before database creation; invalid strings are not
replaced, dropped or silently repaired. Diagnostics do not echo the bad string.
This decoder is duplicate-safe and Unicode-safe, not a full RFC-strict or
resource-limited JSON parser; ordinary Python JSON depth/size behavior still applies.

Import source labels, which arrive separately from JSON, are also checked for
valid Unicode before reading the export or opening SQLite. Invalid surrogate
labels fail without creating an empty archive; accepted labels keep their exact
spelling. See [source-label and byte-ingestion boundaries](docs/INPUT_SCOPE.md#normalized-bytes-and-compatibility).

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
python title_proposal.py --db ../demo.sqlite preview ../proposal.json --output ../reviewed-preview.json
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

The adapter can also prepare from verified source scopes with
`--evidence-scope web-branch`, `local-replay` or `local-attributed` and an explicit
`--input` export. These reuse the branch/retained-turn/producer-attribution checks
before applying request limits, so excluded raw history does not reenter a model-ready
request. Default raw mode is unchanged. This still provides local/mock execution
only; see the adapter guide for scope selection, provenance and review boundaries.

Already have a title response from a separately authorized tool? The
[saved-response workflow](docs/SAVED_TITLE_RESPONSE.md) validates its JSON against
the unchanged prepared request and current source evidence, then produces a normal
reviewable proposal. It requires no network call and does not claim which model ran.
Its offline `prepare` and `complete-response` commands now support native
`--output NEW_JSON` with UTF-8 and no-overwrite publication, avoiding shell
redirection. Saved request/proposal receipts are not transmission permission or
title approval; external `generate` remains disabled/unconfigured. Named adapter
input files also tolerate [one initial UTF-8 signature](docs/TITLE_ADAPTER.md#editor-saved-utf-8-input-files)
from an editor, while counting its original bytes against the same limits. This
does not relax source provenance, request freshness or explicit title review.

If the useful request you found is older than the adapter's recent-user window,
[select that exact message](docs/ADAPTER_MESSAGE_SELECTION.md) for preparation and
completion. Selection stays inside the verified raw/branch/replay/attributed scope,
freezes the explicit choice locally and preserves full-content freshness checks.
Repeated attributed occurrences require their exact original locator. This adds
no model connection or automatic title change.

## Explicit web text shapes and branch coverage

The web adapter extracts string entries from `content.parts` and now also supports
`content_type: code` and `content_type: execution_output` with a string `text`
field. These two text-field shapes must not also contain `parts`, so ambiguous
representations fail before import. Nonblank text and its whitespace are preserved verbatim; whitespace-only messages
are omitted. Attachment objects are never stringified. Other `text` fields are not guessed.
This is a tested offline format contract, not a claim to cover every export version.

Inspection and import receipts count text-field messages, skipped nontext parts,
unsupported text fields and forked conversations, without exposing message text or
IDs. Normalization and first import retain all mapping branches in original mapping order.
`current_node` does not select a path. Fork warnings make clear that title proposals
can mix alternate conversation paths; review the evidence before applying a title.
Archive branch filtering, binary attachments and remote title changes are not implemented.
The separate read-only export branch viewer below supports branch selection.

Reimporting an original export can add code/output messages skipped by older
versions. Recovered messages are appended after existing archive messages, so their
archive order can differ from the original mapping order; existing message positions
are not rewritten. Existing message identities retain conflict protection. Newly recovered
messages invalidate earlier content-bound title proposals, which must be generated
and reviewed again. A mixed text/parts shape previously accepted may now be rejected;
keep the original export and use a separately normalized explicit representation
rather than editing archived evidence. Checked titles affect only the local display.


## Read one web conversation branch without importing it

```sh
python recap.py web-branch ../conversations.json --conversation synthetic
python recap.py web-branch ../conversations.json --conversation synthetic --node alternate-tip
# Equivalent standalone entry point:
python web_branch.py ../conversations.json --conversation synthetic
```

The default endpoint is the selected conversation's `current_node`. An explicit
`--node` selects an alternate or interior endpoint. Output follows `parent` links
from root to endpoint, not timestamps or mapping insertion order. Null/nontext nodes
remain in the node path and omission count; supported text messages retain their
original hash and mapping locator. Leaf IDs, immediate continuations and forks along
the path help select another endpoint. These are node IDs, which need not equal the
embedded message IDs.

The entire export is validated from one byte snapshot before selection. Missing or
invalid current pointers are rejected without guessing a replacement. A named node
can still be selected explicitly. Duplicate matching conversation records are
rejected as ambiguous. Malformed graphs even outside the selected path are rejected.
Parent links are authoritative; redundant `children` arrays are not used to select
the path. Multiple roots remain permitted by the existing normalization contract.

This command never opens a database, changes an export or contacts a service. Its
JSON contains **private text and node IDs**; do not publish or transmit it. All
supported roles on the path are included, including system/tool text when present;
this is not reconstruction of the website's visibility rules. The full export is
loaded in memory and parsed twice, so this is not a bounded-memory large-file viewer.

The all-branch archive import and title-generation behavior are unchanged. Branch
output is a review view, not a title proposal or replacement export, and cannot be
applied as one. Branch-specific archive indexing remains future work; the verified branch title
proposal command below connects this view to the existing archive. Original exports are needed because the archive does not retain `current_node`.

The structural contract is informed by the public converter's
[data models](https://difegam.github.io/chatgpt-to-markdown/reference/data-models/),
which describes mapping nodes, parent pointers and current_node. It is an independent
implementation's observed format, not a stable official OpenAI schema. Only synthetic
fixtures are shipped; no public or private conversation corpus was imported.


## Suggest a title from a verified archived branch

```sh
python recap.py --db ../demo.sqlite suggest-branch-title ../conversations.json --source demo --conversation synthetic --output ../proposal.json
# Optionally add --node alternate-tip to use another path.
python title_proposal.py --db ../demo.sqlite preview ../proposal.json --output ../reviewed.json
# Review title, evidence and branch context before applying:
python title_proposal.py --db ../demo.sqlite apply ../reviewed.json
```

`branch_title.py` is the standalone equivalent. Import the original web export into
the intended source first. Generation checks every extracted message on the selected
path against one archive read snapshot: node/message ID, role, text, timestamp and
exact original-file hash, mapping locator and parent provenance must match. It reads
both the current and legacy provenance ledgers, without migrating the database.
A text-only archive without matching export provenance is rejected. Reformatting an
export changes its byte hash; explicitly import those bytes before using them here.

The local excerpt algorithm selects user text only from the verified path. The
proposal fingerprint covers the **whole archived conversation**, so an addition on
an alternate path also invalidates it. Existing preview/apply checks still reject
changed contents or stale title revisions. Generation does not change messages,
provenance or title history. All branches remain indexed and searchable.

This selects the evidence for one **conversation-wide local display title**, not a
separate persistent title per branch. It is still an extractive suggestion, not a
semantic model. Branch metadata in the saved proposal is descriptive and unauthenticated,
like the other operator-editable proposal fields; review it rather than treating it
as proof. Apply validates user evidence membership, the whole content fingerprint and
reviewed revision, not the original export file or a live website selection. Later
changes to that file or its `current_node` alone do not invalidate a pinned proposal.
Generate and review again if you want the newly selected branch. No external API,
automatic import, credential handling or remote title update is involved.


## Export a manual title-change plan for web or local sessions

```sh
# First review and set a local display title using the checked title workflow.
python recap.py --db ../demo.sqlite export-title-plan ../conversations.json --format web --source demo --conversation synthetic > ../title-plan.json
python recap.py --db ../demo.sqlite check-title-plan ../conversations.json ../title-plan.json
# For local session exports use --format local with the explicit JSONL path.
```

Standalone equivalents are `title_plan.py --db ... export` and `... check`.
This read-only interface exports versioned JSON after at least one explicit local
title revision. It contains the source/conversation identity, archive original and
proposed titles, revision and content/original-file hashes. It does not include message
records or local file paths. **Titles may themselves quote private message text**, and
IDs/hashes can be sensitive, so the plan is not safe to publish or send automatically.

All text from the selected export conversation must match archived content and exact
provenance. Web duplicates are rejected as ambiguous; repeated local occurrences are
verified individually. Other archived branches or later imports remain intact. The
check recreates the plan from one current archive snapshot and requires an exact
field/type match, rejecting changed export bytes, conversation contents, title
revisions, extra fields and altered values. JSON field order does not matter. Checks
are point-in-time, not a lock against subsequent changes. The plan is not signed or
authenticated and cannot authorize execution.

`manual_rename` and `no_change` compare against the **archive's original title**, not
a live platform title. Archive identifiers are not verified service targets, even if
they resemble service IDs. Both export and check always report `NOT_EXECUTED` and
`remote_mutation: false`. There is no apply-to-platform command, login, transport,
credential storage or paid API. To use the title elsewhere, identify the intended
conversation in its own application, compare its actual current title and make the
change yourself. A successful check does not establish that a remote change is needed
or permitted. The original export and local database are never modified by these commands.

## Opt-in typed Codex local text profile

```sh
python recap.py inspect ../explicit-session.jsonl --format local-codex
python recap.py --db ../typed.sqlite import ../explicit-session.jsonl --format local-codex --source typed-demo
# The same format is supported by manual title-plan export and recheck.
```

`local-codex` keeps the existing session_meta / response_item message envelope but
extracts only content items explicitly typed `input_text` or `output_text`. This
selection follows the public OpenAI Codex
[ContentItem model](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/models.rs)
observed on 2026-11-03. It is a versioned parser behavior in this project, not a claim
that all Codex rollout versions, event types or storage formats are supported.

Known text items require string text. Content must be an array of objects. Malformed
supported shapes fail before database writes. Nontext, unknown and untyped parts are
skipped and counted, even if they contain a field named text. Nonblank extracted text
retains leading/trailing whitespace; multiple text items are joined with one newline.
Whitespace-only messages are omitted. This preserves indentation that the legacy
profile trims, but is not byte-for-byte reconstruction of the original JSONL record.
Original file hashes and line locators remain available independently.

The existing `local` format is unchanged: it accepts generic text fields and trims
outer whitespace for compatibility. **Do not switch an existing source blindly.**
If the profile changes the text for an existing message ID, reimport rejects the
conflict rather than rewriting evidence. Use a distinct source ID or a separate
archive after inspecting coverage, and review new title proposals. A new source ID
creates a separate archive identity; it does not migrate old title history or remove
old data. Profiles that produce identical rows can deduplicate normally.

Both profiles currently extract only user/assistant response_item messages. Tool
calls, system/developer text, event-only messages, media and encrypted content are not
reconstructed. Fallback IDs still use the source basename and line number when an
explicit message ID is absent, so renaming or rearranging an export can change those
IDs. No private directory scan or account access is performed.

## Local rollout context and incomplete-history warnings

Local inspection/import now reports fixed-category record counts and detected
compaction, rollback, fork, parent-thread, paginated-history and inherited-history
markers. These counts disclose no marker values, paths, arbitrary event names or
message text. Unknown record kinds are grouped under `other_records`. Fallback
message IDs also trigger a basename/line-number stability warning.

These are **presence diagnostics, not schema validation or effective-history replay**.
Metadata values are not followed or fetched. Referenced parent files are never opened.
Compaction summaries/replacement_history are not extracted as original messages, and
rollback markers do not delete earlier archived messages. Extraction keeps supported
response_item text in source line order. Both legacy and typed profiles report
`effective_history_reconstructed: false`; absence of markers does not prove completeness.
All warnings describe the supplied export file, not only a selected conversation.

This boundary is informed by the official Codex
[rollout reconstruction](https://github.com/openai/codex/blob/main/codex-rs/core/src/session/rollout_reconstruction.rs)
and [thread history fields](https://github.com/openai/codex/blob/main/codex-rs/thread-store/src/types.rs)
observed on 2026-11-03. Actual reconstruction is more complex than removing N messages
or replacing text with a summary, and is intentionally not approximated here.

Manual title plans now use `recap.manual-title-plan.v2` and carry export-wide extraction
warnings plus the explicit effective-history flag. Version 1 plans must be regenerated
and reviewed; recheck rejects them as unsupported. Database contents and title history
need no migration. Ordinary archive title suggestions still use stored raw text and
cannot diagnose an unavailable original export. Inspect the retained export and review
its warnings before transferring a title, especially for forks, compaction or rollback.
No warning authorizes automatic title changes or external transmission.

## Opt-in completed-turn text projection

```sh
python recap.py replay-local ../explicit-rollout.jsonl
# Equivalent: python replay_local.py ../explicit-rollout.jsonl
```

This is a separate, read-only, **narrow text projection**, not full Codex replay.
It accepts exactly one initial session_meta without history/fork/parent references,
with absent/cli/vscode/exec source and matching session/thread identity when supplied,
then nonoverlapping completed turns with unique explicit turn IDs. Supplied message
IDs must be unique; v4 also handles absent/null message IDs as described below. Start and
completion events must match (`task_started`/`task_complete`, or their `turn_` aliases).
Session metadata and user_message fields use explicit allowlists; unknown fields
are rejected rather than assumed harmless. Nonempty image/audio/file metadata is
rejected even if the event also has text. Each turn must contain one matching user_message event and exactly one first user
response, followed only by assistant text responses. All content parts must be typed
input_text/output_text. Optional message turn IDs must match the active turn.

Only rollback events **between completed turns** are replayed. An integer num_turns
must fit the number of retained turns and the public u32 range. The projection removes
that many complete turns from its in-memory result; it never deletes archived data.
Zero rollback and later new turns are supported. Surviving messages retain original
line locators, and the output includes the original whole-file hash. Rolled-back text
is not emitted. Every input record is still validated, including later-removed turns.

Compaction (even with replacement_history), inherited/paginated history, subagents,
turn attribution, unsupported turn_context forms, tools/media, failed/aborted/open/nested turns,
unknown events and ambiguous user boundaries are **unsupported**. There is no fallback
or guessed recovery. On rejection, JSON contains a fixed reason code and line number,
no partial text/turns, and the CLI exits 1. A line number of 0 denotes a whole-file or
input boundary. Source read failures use SOURCE_ERROR. Many normal Codex rollouts will
therefore be rejected; use ordinary inspect/import for raw archival diagnostics.

The grammar is based on the official
[event definitions](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs)
and [reconstruction implementation](https://github.com/openai/codex/blob/main/codex-rs/core/src/session/rollout_reconstruction.rs),
observed on 2026-11-03. The event model describes rollback in units of user turns and
the task/turn wire aliases. No Rust code is executed here and parity beyond this
restricted grammar is not established. Success still reports
`full_model_history_reconstructed: false`: instructions, tool state, hidden context,
truncation, UI visibility and full model inputs are not reconstructed.

Output includes private text and IDs. The whole explicit input is loaded into memory.
The command does not open a database, follow references, alter import/title workflows,
produce an applicable title proposal, or contact a service. Keep the original export;
the projection is not a replacement export or an authenticated record.


## Representative projection coverage and scoped turn context

A deterministic matrix in `test_replay_coverage.py` exercises 13 chosen schema
scenarios. Contract v1 supported 2 and rejected 11; contract v2
supported 3 and rejected 10. **This is a hand-selected synthetic matrix, not a sample of
user sessions or a measured real-world success rate.** Cases are individual variants,
so a session combining supported and unsupported features still fails closed.

The v2 supported cases were plain completed text, completed text with one matching
turn_context, and completed-turn rollback. The v2 rejected cases were: token accounting events, absent explicit
message IDs, tool invocation, file/image references, compaction, inherited history,
modern turn attribution, missing user event, ongoing turn and mismatched turn context.
Thus even common present-day sessions can still be unsupported. Raw import remains a
separate archival option and does not gain effective replay semantics from this feature.

Contract `completed-turn-text-projection.v2` allows at most one turn_context record
inside an active turn with the same explicit turn_id and matching root ID if supplied.
It accepts only turn_id/root_turn_id plus cwd, model, approval_policy, sandbox_policy,
effort, summary and comp_hash metadata. Unknown context fields, invalid basic value
shapes, repeated/unscoped context and mismatched IDs are rejected. This is a deliberate
subset of the public TurnContextItem, not full validation of policy/model values.

The metadata is ignored for this **text-only** projection, never applied as settings,
executed or included in the output. Counts show accepted context records, including
those in later-rolled-back turns; each retained turn also carries its own count.
The official reconstruction code treats turn context as baseline/settings state and
requires a real user boundary to count a user turn. This implementation still requires
the matching user event and first user message; context alone cannot create a turn.
Full context restoration, policy enforcement, model replay and any external operation
remain out of scope. Existing raw archives and title workflows are unchanged.


## Scoped token-accounting events in text projection

Contract `completed-turn-text-projection.v3` additionally accepts `token_count` events
inside an active turn. The public TokenCountEvent contains optional usage and rate-limit
metadata; official text reconstruction does not turn it into conversation content.
The event cannot start or complete a turn. Its data is never summed, interpreted as a
price/balance, applied to settings or emitted. Counts include accepted events in later
rolled-back turns, and retained turns also show their own event counts.

Only type/info/rate_limits event keys are allowed. When usage info is present, both
usage objects and the public integer counter fields are checked, with signed 64-bit
bounds and no bool/float coercion. Optional context-window and reasoning flags are
shape-checked. Rate-limit outer keys and basic string/object/bool shapes are checked;
nested window/credit objects and enum values are deliberately not fully validated
because they are ignored. A passed projection does not validate accounting accuracy,
available credits, pricing or policy. Unknown outer fields, malformed checked fields
and unscoped accounting events fail closed. Other unsupported records remain unsupported.

Using the same 13 scenario categories (with a public-schema-valid nullable accounting
payload), the prior v2 code supports 3/rejects 10, while v3 supports 4/rejects 9. The only
newly accepted category is token accounting. This remains a chosen synthetic matrix,
not evidence of real usage prevalence or a general Codex success rate. Tools, media,
compaction, inherited history, attribution and unfinished/ambiguous turns remain outside
the supported text grammar. Source and database preservation boundaries are unchanged.


## Source message IDs and projection identities

The public [ResponseItem::Message model](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/models.rs)
permits absent/null message IDs. Contract `completed-turn-text-projection.v4` now
accepts that case without inventing a source or remote ID. `message_id` remains null.
Every output message, including those with explicit IDs, gets a separate projection_id
formed from the original whole-file SHA256 and its physical source line number.
`identity_basis` distinguishes a supplied source ID from a hash/line-only identity.

Projection identities refer only to one exact byte snapshot. Renaming an unchanged
file preserves them; reformatting, appending or otherwise changing its bytes changes
them. They are not stable cross-export message identifiers, signatures or service IDs.
Equal message text is never merged. Supplied nonempty string IDs remain unchanged,
and invalid/empty/reused supplied IDs still fail closed, even across rolled-back turns.
Explicit turn IDs and matching user boundaries remain mandatory.

The same schema check exposed additional boundaries: encrypted message content and
noncompleted status now fail closed. A supplied phase must be a recognized text phase.
The supported nested message metadata is limited to turn_id (which must match) and
finite numeric create_time. Other message/passthrough fields are rejected rather than
assumed harmless. Status, phase and nested metadata are not emitted as new content;
this is still a text projection, not full item or model replay.

On the same 13 synthetic categories, prior v3 supports 4/rejects 9 and v4 supports
5/rejects 8. The only newly supported category is missing message IDs. Boundary
hardening additionally rejects previously unchecked encrypted/incomplete/mismatched
or unknown message metadata. These counts do not estimate actual usage frequency.
No archive migration, source rewrite, remote operation or title application is added.

## Propose a title from verified retained local turns

```sh
# Preserve the complete raw export in the archive first:
python recap.py --db ../demo.sqlite import ../rollout.jsonl --format local-codex --source local-demo
python recap.py --db ../demo.sqlite suggest-replay-title ../rollout.jsonl --source local-demo --conversation synthetic --output ../proposal.json
python title_proposal.py --db ../demo.sqlite preview ../proposal.json --output ../reviewed.json
# Review the retained-turn excerpt and evidence mapping before applying:
python title_proposal.py --db ../demo.sqlite apply ../reviewed.json
```

`replay_title.py` is the standalone equivalent. This connects parsing, archival data
and a human-readable local title without replacing raw history with a projection.
The source is read once. The same immutable bytes feed the restricted projection and
typed normalization. Unsupported replay inputs fail before a proposal is produced;
a fully rolled-back history with no usable user text yields no invented title.

Every normalized raw message, including later-rolled-back text, must match exactly one
archive message occurrence by original file hash and line locator, then role, text and
timestamp and supplied explicit source IDs, including discarded-turn IDs. Both
provenance ledgers are supported. Retained projected messages are
matched to those verified occurrences; an explicit source ID must also match the
archive ID. The proposal uses the **actual archive evidence ID**, not projection_id.
A missing source ID remains null in the descriptive evidence mapping.

Identical bytes under a renamed filename can therefore match an existing archive via
provenance even when fallback archive IDs contain the old basename. If both filenames
were imported into the same source and produced multiple archive identities for one
occurrence, generation rejects that ambiguity rather than merging or choosing one.
Inspect the source/identities or rebuild a separate archive from explicit originals;
this command never deletes, deduplicates or repairs the archive automatically.

The excerpt uses retained user text only. Its fingerprint still covers the **whole raw
archived conversation**, so changes even to removed-turn content invalidate it. Existing
preview/apply revision checks remain in force. The result changes one conversation-wide
local display title, not source files, remote titles or branch-specific title records.
Raw discarded messages remain searchable and auditable. Manual title-plan export/check
continues to carry the raw export warnings and NOT_EXECUTED status.

Projection context in a saved proposal is descriptive, unsigned and pinned to those
source bytes. Apply rechecks the archive fingerprint/user evidence and reviewed title
revision; it does not reread the export or verify live platform state. Regenerate and
review after changing the source you intend to use. All existing restricted-projection
limitations remain, including no general compaction/model-history reconstruction.

## Mock-only title transfer boundary

`title-adapter-dry-run` and `title-adapter-simulate` rehearse a separately supplied
provider/account/target/revision contract after checking a manual title plan.
An explicit approval document binds the whole request; an in-memory mock checks
its target snapshot atomically. **No real provider is configured and no remote
rename or transmission occurs.** The CLI does not persist simulated state.
See [the mock contract and synthetic example](docs/TITLE_TRANSFER.md), including
unsigned approval and cross-system transaction limits. This is separate from the
local title-text generation adapter and does not enable an external model API.

## Import only an explicit conversation

`inspect` and `import` accept `--conversation ID` for `web`, `local` and
`local-codex`. Only selected extracted messages enter the database; the original
whole-file hash, node/line locators and all selected branches/raw history remain
intact. The file is still fully read and validated. Existing coverage is file-wide;
`selection` separately reports selected/excluded message counts. This does not
remove anything already indexed. See [input scope and failure boundaries](docs/INPUT_SCOPE.md).

## Review multiple local title suggestions

`review-titles --source SOURCE --limit 20 --offset 0` creates a read-only proposal
page with current titles, unavailable-item reasons and advisory duplicate-title
counts. It uses raw archive excerpts, not web active paths or retained Codex
history. Select one item with `preview-title queue.json --conversation ID`, review
the resulting preview, then use the existing single-title apply command. There is
no bulk apply or remote mutation. See [title review queue limits and examples](docs/TITLE_REVIEW_QUEUE.md).

## Review title length and possible private details

Queue items and previews include local `title_advisory` hints for character count,
reported truncation/greeting fallback and a few possible private-detail patterns.
They report categories only and **never certify privacy or semantic quality**.
Use `preview-title ... --title "Your chosen wording"` to create an explicitly
operator-authored replacement while preserving the checked evidence/content
binding, then inspect and apply the individual preview. See [review hints and limitations](docs/TITLE_REVIEW_HINTS.md).

When organizing many sessions, add `review-titles --unrenamed-only` to omit any
conversation with existing local title history before pagination. Counts explain
the eligible/source totals. Refresh at offset 0 after applying a title; this is a
read-only history filter, not a durable review/skip ledger or a title quality test.

## Explicit skip and defer state

`review-state` reads or explicitly records `open`, `skipped` or `deferred` for one
conversation, separately from title changes. A write requires the current state
revision, title revision and raw-content hash. Queue items show the decision;
changed content/title makes old decisions stale rather than silently carrying
them forward. No title change, hiding, reminder or remote action is automatic.
See [review state, concurrency and storage limits](docs/TITLE_REVIEW_STATE.md).


Use `review-titles --state deferred` (or `open` / `skipped`) to revisit one explicit
effective state. Stale decisions return to open; no state changes merely by viewing.
The opt-in filter hashes all eligible source conversations before pagination, so
it can cost more than the default page. It can be combined with `--unrenamed-only`.

After reviewing a saved queue item, `review-state --source SOURCE --conversation ID
--set deferred --from-queue queue.json` reuses that item's existing lease without
manual hash/revision copying. It never silently refreshes a stale queue; the same
atomic checks still apply. The decision and destination remain explicit.

## Find a title you used before

`find "old wording" --include-title-history` optionally searches prior local
labels and the archived original title in addition to current titles/raw text.
Results show the current title plus bounded matching historical records and their
local revisions. This can expose private wording removed from a current label,
so it is opt-in and read-only. See [historical title search semantics and limits](docs/TITLE_HISTORY_SEARCH.md).

## Search one original export's message bodies

`find "query" --export-sha256 ORIGINAL_SHA256` restricts body matches and snippets
to messages linked to that exact original file hash in the export provenance ledger.
Current/optional past titles remain conversation-wide local metadata. Original
node/line evidence is shown separately from normalized artifact provenance.
See [export-scoped search and trust boundaries](docs/EXPORT_SCOPED_SEARCH.md).


## Prepare a downloaded web export

`prepare-web-export ZIP --member conversations.json --output NEW_FILE` validates
one explicitly selected ZIP JSON member and copies its bytes to a new local file
without overwriting anything. It has strict size/compression limits, never imports
or uploads automatically, and separates outer ZIP and prepared JSON hashes.
See [official format references and preparation limits](docs/PREPARE_WEB_EXPORT.md).


Use `inspect-web-zip ZIP` first to list conventionally named conversation JSON parts
without decompression. It shows exact names and metadata-only rejection reasons,
never certifies JSON validity or part completeness, and does not list unrelated
account-file names. Pass the first page's hash to later candidate pages and preparation
with `--expected-archive-sha256` to reject a ZIP changed since inspection. Without
that option each page is independent, so replacement or reordering can repeat or
skip entries. Pagination still reads the bounded whole ZIP and does not establish
part completeness. See [candidate selection](docs/WEB_ZIP_INVENTORY.md).

## Match-centered search evidence

Conversation search now shows the matching part of a long message instead of
always its first 240 characters. Each sample includes unchanged source text,
code-point offsets, truncation flags and the first literal match span. Unicode
case-fold expansion is mapped back to the original text; title-only matches do not
invent message evidence. Ranking, provenance and history/export filters are
unchanged. See [search excerpt fields and limits](docs/SEARCH_EXCERPTS.md).

### Web content tag validation

Web imports now reject a malformed present `content_type` before accepting partial
text or touching the archive. This prevents an invalid tag on a substantive request
from silently leaving only an earlier greeting available for a title. Missing tags
and nonblank unknown strings keep their existing limited compatibility behavior;
no guessed repair or new text shape is added. The same validation covers inspection,
selected imports, branch reads and ZIP preparation. Existing partial archives and
saved titles are not automatically changed. See [web tag boundaries](docs/INPUT_SCOPE.md#malformed-web-content-tags).

### Local metadata validation

Present top-level local record tags must also be nonblank strings. A malformed tag
can hide a session boundary and incorrectly associate later messages with the prior
session, so the whole input now rejects instead of skipping that damaged record.
Absent tags and nonblank unknown strings keep their existing warning/skip policy;
metadata-only utility inputs remain unchanged. See [record-tag scope and compatibility](docs/INPUT_SCOPE.md#malformed-local-record-tags-can-hide-a-session-boundary).

Both `local` and `local-codex` imports reject malformed session boundaries rather
than silently assigning subsequent messages to the preceding session. Local
message timestamps preserve numeric zero and accept missing/null as `unknown`.
Empty strings, booleans, containers and nonfinite numbers are rejected before
archive writes. Timestamp text is retained as supplied, not parsed as a date.
If an older archive already stores a zero timestamp as `unknown`, reimport reports
a conflicting identity and leaves the old evidence unchanged; it does not silently
rewrite the archive. Use a separate archive/source for a deliberately corrected
reimport and retain the original export for comparison.

## Open only the evidence you need

`title-history --source SOURCE --conversation ID --limit 20` reads bounded local
title-change events without selecting message-body columns or generating excerpts.
It shows current and historical revisions separately; use `--expected-revision`
on later pages to reject intervening title changes. Old labels may contain removed
private information. No title is restored automatically. See [history review and
deliberate reuse of earlier wording](docs/TITLE_HISTORY_VIEW.md).

`show --message MESSAGE_ID` reads one exact archived message with its provenance.
`show --limit 50 --offset 0` reads a message page and returns the next offset.
Source/conversation identities remain explicit, title summaries and whole-conversation
counts remain visible, and SQL limits both message and provenance retrieval. Omitting
these options retains the existing full view. See [message selection and paging](docs/MESSAGE_SELECTION.md)
for structured fields, snapshot limits and the path from a search result to evidence.

### Search sample coverage

Search now chooses up to three body samples that improve distinct query-term
coverage, so a later rare term need not be hidden behind redundant early hits.
Results also report exact matching-message counts, omitted-sample flags and which
body-matched terms are missing from the sample. This is deterministic bounded
literal coverage, not semantic ranking or a guarantee every term fits in the
visible excerpt. See [sample selection and coverage fields](docs/SEARCH_EXCERPTS.md#diverse-bounded-body-samples).

## Source-attributed local title proposals

For modern local exports that explicitly label content sources,
`suggest-attributed-title INPUT --source SOURCE --conversation ID` can exclude
harness/injected and unknown parts from a proposed local title while preserving
all raw archived text. It verifies source bytes and archived occurrences, uses
original content positions including media, and never equates a producer label
with authenticated human authorship. See the [synthetic walkthrough and strict
compatibility contract](docs/SOURCE_ATTRIBUTED_TITLES.md). Raw inspection surfaces
metadata presence without filtering by it. Existing raw/branch/replay title paths
remain available; the replay grammar also now accepts explicit legacy history mode.

To choose a later user-labeled request without injected parts, see the
[source-attributed message and occurrence selection walkthrough](docs/ATTRIBUTED_MESSAGE_SELECTION.md).

## Find a session by remembered text before import

`list-export --text-contains "remembered phrase"` can find opaque local session IDs
or generically titled web conversations through one literal extracted-message
substring. It returns IDs, existing titles and matching message/role counts without
body fields. This explicit mode is separate from metadata-only `--contains`;
neither changes source files, opens a database or imports automatically. The query
itself can be private. Full-file validation and raw branch/rollback scope remain.
Use the returned exact ID and original hash for selected import, then independently
review title evidence. See [message-text discovery and reviewed-title example](docs/EXPORT_INVENTORY.md#find-a-conversation-by-remembered-message-text).

### Find remembered requests without assistant echoes

Pre-import text discovery accepts an optional `--text-role user` (or `assistant`,
`system`, `tool`) together with `--text-contains`. For example:

```sh
python recap.py list-export examples/title-focus-local.jsonl --format local-codex --text-contains "orchard watering" --text-role user
```

This restricts matching occurrences before pagination without changing full-export
validation or counts. The default still searches every extracted role. A role label
is not proof of human authorship or retained history. See
[the export inventory guide](docs/EXPORT_INVENTORY.md#restrict-remembered-text-to-one-message-role)
for source-format limits, privacy, and the separate import/title-review boundary.
