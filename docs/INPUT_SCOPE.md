# Select the input and indexing scope

The import parsers process an explicitly named **local UTF-8 text file**.
One optional initial UTF-8 signature is accepted. Local/normalized JSONL consistently
recognizes LF, CRLF and CR physical lines while preserving original hashes and
Unicode message text. See [source text compatibility](SOURCE_TEXT_COMPATIBILITY.md)
for exact acceptance and failure boundaries. UTF-16/32 are not auto-detected.
The separate [bounded ZIP preparation command](PREPARE_WEB_EXPORT.md) can create
a new web JSON input from one explicitly selected archive member. It is not a web
account collector or installed Codex session discovery tool. Use only exports you
are authorized to read. Current formats are deliberately limited:

| Format flag | Input and extraction | Important exclusions |
| --- | --- | --- |
| `web` | JSON array of conversation objects with `id`/`conversation_id` and `mapping` parent graph; string parts plus explicit code/execution-output text | No direct ZIP parsing at import, HTML, browser database, attachment downloads, universal/stable vendor schema or active-branch selection on import |
| `local` | Legacy local session JSONL metadata and supported user/assistant response records | Not a replay engine; legacy text normalization differs from typed Codex mode |
| `local-codex` | Local JSONL, explicitly typed input/output text items from supported response messages | No tools/media, inherited-history resolution or complete model-context recovery; context markers are warnings |

`replay-local` is a separate opt-in, fail-closed completed-turn text projection,
not the default importer. See [its narrower grammar](WORKFLOWS.md#opt-in-completed-turn-text-projection). Title proposals
are local excerpts, not semantic model summaries. Local display-title changes do
not rename a live ChatGPT/Codex thread. Mock transfer simulation is not a service
connection. Do not describe this tool as a deployment-ready remote renaming app.

## Index one conversation from a larger file

Previously, import necessarily indexed every extracted conversation in the file.
Both unified and standalone `inspect`/`import` now accept an optional explicit
`--conversation` ID:

```sh
python recap.py inspect examples/web-export.json --format web --conversation synthetic-chat
python recap.py --db ../recap-demo/archive.sqlite import examples/web-export.json --format web --source web-demo --conversation synthetic-chat
```

Create a new private directory outside the repository for the database first.
For your own export, use its exact conversation ID, not its title. There is no
fuzzy ID selection. Use [the read-only export inventory](EXPORT_INVENTORY.md),
`recap.py list-export INPUT --format FORMAT`, to find IDs and existing web titles
without creating a database or printing message bodies. IDs/titles may still be
private. The inventory's optional `--contains` filter can find part of an existing
web title or ID before paging, without searching message bodies or relaxing
full-file validation. Use its exact returned ID for selection. Do not import the
whole file merely to learn an ID if that exceeds your intended scope. For an opaque
local ID or generic web title, explicitly use `list-export --text-contains` to locate
a remembered phrase inside supported extracted messages. It returns IDs and counts,
not body fields, but its echoed query can be private. This searches all raw extracted
roles/branches/turns, not only active or human-authored history; later selected import
still keeps the entire chosen conversation. Local formats use the session ID:

```sh
python recap.py inspect examples/rollback-session.jsonl --format local-codex --conversation synthetic-rollout
python recap.py --db ../recap-demo/archive.sqlite import examples/rollback-session.jsonl --format local-codex --source local-demo --conversation synthetic-rollout
```

Continue with the same branch/retained-title proposal, preview and apply commands
in [the walkthrough](TITLE_WALKTHROUGH.md). Their source and conversation must
match this import. Selected web imports still include **all extracted branches
of that conversation**; local imports still keep raw records including rolled-back
turns. Selection is not an effective-history filter. Selecting one session from a
multi-session local file does not relax the separate replay engine's single-session
input contract; a retained-title proposal may therefore still be unsupported.

### Receipt interpretation

Existing coverage fields, including `extracted_messages`, `role_counts`, warnings
and omission counts, still describe the **whole file**, preserving their meaning.
When selection is present the additional `selection` object contains:

- `conversation`: the exact requested identity.
- `selected_messages`: the number of normalized messages passed to the importer.
- `excluded_messages`: extracted messages intentionally excluded by this selection.
- `selected_role_counts`: roles for the selected normalized rows.
- Explicit coverage scope and selection policy descriptions.

The import's existing `inserted` count can be smaller than `selected_messages`
when some rows were already indexed. Inspection reports contain counts and the
selected ID, not message text or conversation titles. IDs may still be private.
No-selection behavior and receipt shapes remain unchanged.

### Preservation and failure boundaries

The **entire file is read, parsed and validated in memory**, even with selection.
This is a database write-scope control, not a way to avoid reading unselected
content, a streaming/memory optimization, or a malformed-record bypass. Invalid
unselected content can prevent import. Nothing is sent externally.

An unknown selection, selection with no extracted text, or multiple web records
with the selected conversation ID fails **before database access/write**. Selection
does not make duplicate web identities safe; unselected duplicate records are
not newly rejected by this option and still follow existing whole-file validation.

Original whole-file SHA-256 and exact mapping-node/physical-line provenance are
preserved, never recalculated from a sliced file. Fallback local message IDs keep
the original basename and line. The source file is read once, so validation and
selection use the same bytes. Web selection parses those immutable bytes again
to check that the selected record is unique; this adds full-file parsing overhead.
Keep the source unchanged for later verified title proposals/manual plans.

A later intentional import of another conversation from the same file is allowed.
Repeating a selected import remains idempotent; conflicting message identities are
still rejected transactionally. Selection **never removes previously imported
conversations**. Use a new private database if you want an archive containing only
the newly chosen scope. Neither inspection nor a rejected selection creates a DB.

### Local snapshot parsing and error locations

Local and local-codex normalization now parse the already-read immutable byte
snapshot directly. `inspect`, `list-export`, `check-import` and source-backed local
title reads no longer create a temporary second copy of the source JSONL just to
parse it. Record-validation diagnostics use the selected file's basename and its
physical line, rather than a temporary `session.jsonl` path that no longer exists.
The basename is a diagnostic label, not a resolved path or authenticated identity;
use the exact input path you supplied to locate the source. Names can be private.

Original hashes, BOM/newline handling, fallback message IDs, content profiles,
omission/context counts, utility metadata rules and full-file validation stay the
same. This is not streaming: the full source bytes and parsed records still occupy
memory. It does not guarantee zero filesystem I/O by Python/SQLite or other commands.
Export `import` also passes derived normalized JSONL bytes directly to the archive
writer, without a temporary normalized file. It still deliberately writes the
selected SQLite database, whose journal and internal temporary-storage needs are
unchanged. A writable private archive directory is still required. No automatic
collection, format detection, content repair or relaxed validation is added.

For Python callers, `local_parser.parse_jsonl_bytes(raw, source_relative_path,
content_profile="legacy")` accepts immutable `bytes` plus a nonempty text label.
The label is not opened or resolved. It is preserved in fallback IDs and byte-parser
diagnostics and retains existing special metadata-only source-label policies.
This API does not read files, stage bytes or open SQLite. The existing
`parse_artifact(path, ...)` file/SQLite entry points stay supported; their file-based
diagnostics continue to use the explicitly provided path. Neither interface verifies
that a caller-supplied label is a genuine source identity.

### Normalized bytes and compatibility

[The normalized input contract](NORMALIZED_JSONL.md) consolidates fields, silent
acceptances, identity conflicts and the normalized-file provenance boundary.

`recap.ingest_bytes(db, source, raw, provenance=None)` shares the file-ingest record
validation, transaction, conflict and provenance rules. It accepts immutable `bytes`
and an explicit non-whitespace, valid Unicode source label. Labels remain exact, not
trimmed, normalized or converted from numbers/bytes. Invalid source labels fail
before file reads in `ingest(...)`, `import_export(...)` and `check_import(...)`,
and before database access in these and the byte-ingestion entry point. The file
entry point remains supported and reads its input once before using the byte path.

Source labels arrive separately from decoded JSON. Surrogate code points
can occur in Python strings or in Unix command arguments decoded from invalid
bytes; SQLite cannot encode those labels as UTF-8. They now fail with a fixed,
content-free error before source parsing or archive creation, rather than creating
an empty schema and then failing on insertion. No replacement character or guessed
source name is substituted. Correct the supplied label explicitly. Korean, emoji,
combining sequences and other valid Unicode labels retain their exact identities.
Previously created empty databases are not automatically removed or repaired.

For export import, in-memory normalization deliberately retains the previous UTF-8
text-writer behavior, including native Windows CRLF line separators. Existing
normalized artifact hashes and source-line locators therefore remain compatible on
the same platform; this is not a new cross-platform canonical JSONL format. The
receipt's `source_sha256` identifies those derived normalized bytes. Use
`coverage.original_sha256` and the original-export provenance ledgers for the exact
chosen export bytes. Existing archived message provenance is never rewritten just
because a later export is imported.

Adapter imports reuse their parsed rows instead of decoding the derived JSONL
again. The derived bytes are still constructed for the same artifact hash and byte
count. This removes one repeated parsing pass, not the whole-file memory cost or
a promised runtime fraction. See [adapter import cost](ADAPTER_IMPORT_COST.md).

All record and incoming-identity checks still run before opening SQLite. Existing
archive conflicts and provenance failures still roll back the data transaction;
schema setup and all possible filesystem failures are not newly made atomic. Full
source, parsed rows and normalized bytes remain in memory. Removing Python's extra
JSONL staging does not promise bounded memory, disk-free database writes, encryption
or absence of every OS/SQLite temporary file. Keep the original export privately.

## Bind inspection to exact source bytes

`list-export` and `inspect` report the whole-file `original_sha256`. Copy that
lowercase digest into `--expected-export-sha256` on a later `list-export`,
`inspect` or `import` command to require the identical source bytes. Unified and
standalone commands support the same option for web, local and local-codex input.

This copyable check uses the unchanged shipped synthetic web example:

```sh
python recap.py inspect examples/web-export.json --format web --conversation synthetic-chat --expected-export-sha256 207e4b25d6088c4cbc729deeb5aa9993077214dbeadc8e19eb099b762175e434
```

For your own input, use **its** digest, never the example's. The flag works with
or without `--conversation`; a selected import still checks the entire original
file, including unselected content. Changed whitespace or newline bytes also
invalidate it. Renaming an otherwise identical file does not change this hash,
but local fallback message IDs can still depend on its basename.

Invalid hash syntax rejects before reading the source. A mismatch rejects before
parsing or database access, even if the new file is malformed. A match does not
skip format, identity, provenance or transaction checks. The importer reads the
source once and parses that checked byte snapshot, not a second file read.

Successful inspection echoes `expected_export_sha256` beside `original_sha256`.
Import and inventory return it inside `coverage`. This field is present only
when the option was supplied, preserving existing no-option report shapes.
Use the same hash for later inventory pages to detect a changed file. The check
does not retain a snapshot across commands or stop another program changing the
file after it was read; the current operation uses the already checked bytes.

This is an operator-selected consistency check, not a signature, identity proof,
permission record or completeness guarantee. Do not automatically replace a
rejected expected hash with the latest one and retry. Inspect the changed source
and decide the intended scope again. No external verification service is used.

For an existing archive, [read-only conflict diagnostics](IMPORT_CONFLICTS.md)
can compare selected incoming identities before import. This is separate from
source-only `inspect`, and it does not relax the importer's locked checks.

## Malformed web content tags

A web message's **present** `content_type` must be a nonempty string containing a
non-whitespace character. Null, booleans, numbers, arrays, objects, empty strings
and whitespace-only strings reject the entire input. For example,
`{"content_type":["code"],"text":"Compare synthetic irrigation designs"}` is
malformed, not an unsupported text variant that can safely be discarded. Previously
a file with an earlier greeting and this request could import only the greeting
and later suggest that greeting as its title. Malformed tags paired with `parts`
could also be accepted without a warning. Neither case is accepted now.

Validation rejects the input before any parsed result is returned or database
access/write occurs, including when the malformed message is outside a selected
conversation or branch. `inspect`,
`list-export`, `check-import`, imports and source-backed branch/title commands all
share the check. Preparing a selected ZIP member also refuses that malformed web
JSON before creating an output file. The diagnostic names only the field, not its
value or message text; the ZIP preparation wrapper keeps its general unsupported
web-export error. Keep and investigate the original export rather than automatically
changing the tag or importing the earlier partial text.

An **absent** tag remains supported for legacy string `parts`. A nonblank unknown
tag also retains existing behavior: string parts can be extracted, nontext parts
are counted as omitted, and an unsupported `text` field is skipped with a warning.
Tags are not trimmed or normalized. For example, `" code "` is not the supported
`code` text-field variant. Valid `code` and `execution_output` still require string
`text` and reject simultaneous `parts`. This is a narrow input contract, not a
claim that every producer or future export format uses these shapes.

Already imported partial archives, saved proposals and applied titles are not
retroactively scanned, repaired or invalidated. Raw archive-only title generation
does not reread the original export. Reinspect the source and deliberately import a
valid export before generating and reviewing a new proposal; normal identity
conflict and provenance rules still apply. This check adds no text inference,
account collection, model call or remote title change.

## Malformed local record tags can hide a session boundary

Both `local` and `local-codex` now reject a rollout record whose **present** top-level
`type` is null, a boolean, number, array, object, empty string or whitespace-only
string. Previously these values were counted as unknown records and skipped. That
could discard a user request or, more seriously, conceal an intended session boundary:
a valid session A, a damaged record containing an apparent session B payload, then
a valid message would import that later message under A.

The damaged payload does not prove a second session exists. Recap therefore fails
the whole operation rather than guessing its type, resetting to a guessed ID or
silently continuing with the previous identity. The fixed diagnostic is
`invalid local record type`, followed by the source label and physical line number.
It does not echo the malformed tag, payload, session IDs or message text. Parsing
rejects before database access/write or partial results, including when the damaged
record occurs after useful messages or outside an explicit conversation selection.

This is a **deliberate narrowing** of previously accepted malformed tags, not just
a new warning. An older generic unknown-record test admitted object-valued tags;
that behavior is replaced by rejection and regression tests for boundary safety.
Well-formed existing messages and source bytes are not repaired or rewritten.

Compatibility still has explicit limits:

- An **absent** type keeps the existing unknown-record skip and warning.
- Nonblank unknown string tags still skip with fixed coverage counts. Strings are
  not trimmed, case folded or guessed: `" session_meta "` is not `session_meta`.
  This does not detect every misspelled/missing boundary or establish completeness.
- The metadata-only utility contracts run first and are unchanged. Exact
  `session_index.jsonl` inputs validate their index fields without interpreting extra
  rollout tags; generic agent-raw utilities and SQLite backups retain their existing
  behavior. See [index inventory limits](EXPORT_INVENTORY.md#session-index-metadata-is-not-a-message-export).
- This is not full schema validation of every unknown record or payload. The
  [pinned public Codex wire definition](https://github.com/openai/codex/blob/f2b94ef8b52196f127d162c6db71e390b9bb265c/codex-rs/history/src/rollout_payload.rs)
  uses a string-tagged record enum. Recap's missing-tag and unknown-string compatibility
  remains deliberately looser; no universal or current-version replay compatibility
  is implied.

Inspection, inventory, conflict checks, imports and source-attributed title readers
share the parser check. The stricter replay/title path can reject earlier under its
own projection grammar. This rejected input cannot produce a new greeting-only
proposal or silently assign messages across its damaged boundary. Existing archives, saved
proposals and applied titles are not retroactively scanned or corrected, and raw
archive-only title generation does not reread the original source.

Keep and investigate the original export or obtain a valid one. Do not delete a
failed type field, coerce it to a string or select a broader profile just to bypass
this check. A corrected export can still conflict with already admitted identities;
use the existing read-only conflict checks and deliberately choose a separate archive
when needed. The tool does not move existing messages between conversations or
promise automatic repair of an earlier misassignment.

## Malformed known local response records

Both `local` and `local-codex` reject a `response_item` unless `payload` is an
object with a nonempty string `type`. A `type: "message"` payload must also have
a nonempty string `role`. Empty or whitespace-only discriminators are invalid;
strings are not trimmed into a different type or role. A missing/null/list payload
is not treated as a harmless omitted tool event. Earlier releases could silently
skip that malformed record while importing other text and reporting no warning.

These checks run during whole-file parsing, before database creation or changes,
also for inspection, inventory, conflict checks and selected imports. Errors report
the physical line without echoing payload contents. A malformed later record does
not authorize partial import or title generation from the preceding text. Obtain
a valid export or investigate the producer; the tool does not repair the source.
Existing archives are not retroactively scanned or changed by this update.

Valid nonmessage type names and nonempty unsupported roles remain explicit skips,
with the existing counts and warnings. This does not add tool/media extraction or
validate every skipped variant's internal fields. The generic metadata-only archive
utility paths are unchanged. The typed profile's structural distinction follows
the tagged response enum and message role field in the
[pinned public Codex definitions](https://github.com/openai/codex/blob/f2b94ef8b52196f127d162c6db71e390b9bb265c/codex-rs/protocol/src/models.rs).
It is not a claim of full current Codex replay compatibility.

### Malformed typed content must not erase a request

In `local-codex`, a content item's **present** `type` must be a nonempty string
containing a non-whitespace character. Null, numbers, booleans, arrays, objects,
empty strings and whitespace-only strings reject the source. For example,
`{"type":["input_text"],"text":"Synthetic irrigation question"}` is malformed,
not an unsupported media item. Earlier behavior could drop this substantive
request, import only an earlier greeting and then suggest that greeting as a title.
The importer now fails instead of silently accepting that incomplete extraction.

An **absent** `type` remains the existing untyped-content compatibility skip, with
the skipped-part count and warning. Valid unknown/nontext nonempty type strings
also remain skips; their text/metadata is not guessed or stringified. Type names
are not trimmed into another variant: `" input_text "` remains unsupported.
Only exact `input_text` and `output_text` variants supply typed text, and their
`text` must still be a string. This is a narrow shape check, not full validation
of nontext variants or arbitrary future producer schemas. The public
[ContentItem definition](https://github.com/openai/codex/blob/f2b94ef8b52196f127d162c6db71e390b9bb265c/codex-rs/protocol/src/models.rs)
uses a string-tagged enum; the importer deliberately retains the missing-tag
compatibility behavior rather than claiming strict producer-schema equivalence.

The rule applies only to supported user/assistant messages in the typed profile.
The legacy `local` text extraction policy, unsupported-role/nonmessage skips and
metadata-only archive utility paths are unchanged. Choosing the legacy profile
solely to bypass a failed typed validation is not a repair. Obtain or investigate
the valid source instead; existing archive messages are never rewritten.

Whole-file typed validation runs before archive access, even when the malformed
part is later in a message or in an unselected session. Inspection, inventory,
conflict checks, import and source-attributed title generation therefore reject
the same malformed source rather than using preceding text. Invalid typed content
errors include the physical record line and fixed diagnostic labels, without
echoing the content or malformed tag. Source files, hashes and valid occurrence
locators are not changed. Existing archives and previously saved proposals are
not retroactively rescanned or invalidated by this parser change.

## Source identities must resolve without guessing

Web conversation records can provide `id` or `conversation_id`; local session
metadata can provide `id` or `session_id`. If both contain nonempty strings they
must match exactly. A conflicting pair fails instead of silently choosing the
first field and potentially directing search/title work to the wrong conversation.
Every supplied value other than null or the empty string must be a string,
including the secondary field when the primary already looks valid. Numbers, booleans and containers are
not coerced or ignored as missing identities.

Missing, null and empty-string fields keep the existing fallback behavior. They
mean no identity was supplied in that field; another valid alias is still required.
If neither alias supplies a nonempty string, parsing fails. Empty-string fallback
is importer compatibility, not a claim that every producer emits valid empty IDs.
Nonempty strings remain literal: no trimming, case folding, Unicode normalization,
UUID/prefix guessing or remote account verification. Padded and whitespace-only
strings retain their existing treatment; visually similar strings can still be
different IDs. Two canonically equivalent but code-point-distinct aliases are a
conflict. JSON escape spelling does not distinguish equal decoded strings.

For supported local user/assistant messages, `payload.id` must likewise be text,
null or absent. Missing, null and empty strings still use the original source
basename and physical line number, with the existing fallback-ID coverage warning.
A supplied number, boolean or container is now an error, even when that message
has no extracted text. It is not silently replaced with a different identity.
Unsupported-role/nonmessage skip behavior and metadata-only utility paths are not
expanded or newly validated by this rule.

The local optional typed message ID follows the public Codex
[response field](https://github.com/openai/codex/blob/f2b94ef8b52196f127d162c6db71e390b9bb265c/codex-rs/protocol/src/models.rs)
and [transparent string representation](https://github.com/openai/codex/blob/f2b94ef8b52196f127d162c6db71e390b9bb265c/codex-rs/protocol/src/response_item_id.rs).
These references do not authenticate IDs, authorize actions or establish universal
web-export compatibility. The separate replay grammar stays stricter: for example,
its existing empty-message-ID rejection and required primary session ID remain.

Whole-file inspection/import, selected imports, export inventory, web branch views
and source-backed title plans now share the alias resolver. A malformed unselected
conversation or later local boundary still rejects the file before archive access;
selection cannot conceal it. Diagnostics do not echo conflicting IDs or message
contents. Local errors retain their physical-line location. Original hashes,
source bytes, mapping IDs and physical locators are not repaired or rewritten.

Existing archives and saved proposals are not automatically migrated or invalidated.
Source-backed workflows can reject a previously admitted ambiguous export. Obtain
or deliberately inspect corrected source and compare it in a separate archive when
needed; changing a source ID may create a different message rather than update the
old one. Never drop an alias, guess an ID or rewrite an expected hash merely to
make a failed title workflow proceed.

## Clean failure for decoder nesting and conflicting incoming records

If Python's JSON decoder raises a recursion-depth error, the shared reader now
reports `JSON nesting is too deep` as an ordinary source-validation error instead
of leaking a traceback. JSONL wrappers retain the physical line number; replay
reports `INVALID_JSON` at that line with no partial projected text. The whole file
still has to parse, including unknown metadata and unselected conversations.
No recursion limit is increased and no source text is echoed in the diagnostic.

Local/local-codex variant hashing also reports `JSON nesting is too deep` with the
source path and physical line if the encoder rejects metadata the decoder accepted.
It does not expose encoder exception notes, metadata keys or a traceback.

This is not a new fixed numeric nesting/byte limit, streaming parser, resource
budget or repair step. Decoder limits can differ by Python runtime, input shape
and call stack. Inputs the decoder accepts still follow the normal validation
rules. Long bracket characters inside a JSON string are not treated as nesting,
and long flat parent graphs retain their existing iterative validation.

Before connecting to SQLite, `ingest` now checks the **incoming normalized batch**
for repeated `(conversation_id, message_id)` identities whose role, timestamp,
original title or text differs. This prevents a contradictory input from creating
an empty database/schema and then failing later. Existing databases are also left
untouched by this early failure. The source label is fixed for the whole import;
identities from different conversations are separate.

Identical repeats are still allowed and remain in record/artifact counts, while
one archived message and one FTS row are inserted per identity. Existing provenance
rules retain distinct source occurrences and deduplicate equal hash/locator entries.
The first admitted occurrence keeps its existing source-line behavior. Different
optional metadata outside the compared fields does not create a new conflict.
The preflight adds memory proportional to unique incoming identities; it is not
a constant-memory or bounded-input import.

This comparison happens **after optional conversation selection**. It does not
newly reject contradictory identities belonging only to an excluded conversation.
Structural/JSON validation still covers the whole file. Source-only `inspect` and
`list-export` still describe parsing rather than promise successful import; use
[`check-import`](IMPORT_CONFLICTS.md) with an existing archive for conflict detail.

The error's `line` is a physical normalized-input line for direct `ingest`. Export
adapters produce an in-memory normalized message stream, so their conflict line is
the one-based selected normalized occurrence, not the original JSONL line or web
node. Keep source provenance for the original location. IDs and differing values
are not echoed.

Comparisons against the existing archive still execute inside `BEGIN IMMEDIATE`.
Preflight does not replace that lock or protect against a later source/archive
change. Other database, provenance, permission or I/O failures retain their existing
behavior; this is not a guarantee that every failed operation leaves no filesystem
artifact. Existing empty databases from older failures are not removed. Nothing
is automatically repaired, merged, retried or renamed.

## Index metadata versus rollout messages

The special local basename `session_index.jsonl` is a metadata-only utility input,
not a source of message evidence or inferred display titles. Inventory respects that
classification, even when index entries contain additional rollout-looking fields.
See [index inventory and zero-record import limits](EXPORT_INVENTORY.md#session-index-metadata-is-not-a-message-export)
before treating a successful receipt as archived sessions. No index-driven file
collection or new metadata persistence is added.

## Testing interpreter-dependent nesting

Synthetic nesting fixtures use a cached, byte-bounded decoder probe rather than
assuming that every interpreter rejects the same bracket depth. The fixture uses
twice a failing probe depth, with space reserved for wrappers and BOMs below the
supplied-title reader's 1 MiB budget. If no safe failing depth is found within that
budget, only the decoder-dependent case is skipped with an explicit reason.
Duplicate-key, surrogate, bracket-string and deterministic exception-sanitization
checks still run. These are test fixture bounds, not a new input-admission policy.

A separate test probes the encoder and exercises an actual decoder/encoder gap
when a depth with a 32-frame safety margin is accepted by the decoder. It skips
when no such gap is available on the running interpreter; injected encoder-failure
tests always exercise the source readers and CLI error boundary, including line
numbers, hidden private diagnostics and no new database. This is not a resource
exhaustion guarantee or proof of behavior on an untested interpreter.

### Normalized inspection and optional hash lease

`inspect` and `check-import` now accept `--format normalized` without conversation
selection. They report repeated-identity conflicts; ingest still rejects them.
`from recap import validate_normalized` exposes `(records, coverage)` for immutable
bytes; records are private `(decoded_row, effective_title, physical_line)` tuples.
Coverage omits content and counts silent acceptances. `ingest`/`ingest_bytes` accept
keyword-only `expected_sha256=None` and CLI ingest accepts `--expected-sha256`.
The optional guard checks the exact byte snapshot before database access; default
behavior is unchanged. Neither shared adapter normalization, list-export nor title
plans accept normalized input. See [contract and diagnostics](NORMALIZED_JSONL.md).
