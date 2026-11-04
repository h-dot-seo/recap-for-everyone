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
not the default importer. See the README for its narrower grammar. Title proposals
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
private. Do not import the whole file merely to learn an ID if that exceeds your
intended scope. Local formats use the session ID:

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
