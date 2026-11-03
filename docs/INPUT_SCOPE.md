# Select the input and indexing scope

Recap processes an explicitly named **local UTF-8 text file**. It is not a web
account collector or installed Codex session discovery tool. Use only exports you
are authorized to read. Current formats are deliberately limited:

| Format flag | Input and extraction | Important exclusions |
| --- | --- | --- |
| `web` | JSON array of conversation objects with `id`/`conversation_id` and `mapping` parent graph; string parts plus explicit code/execution-output text | No ZIP, HTML, browser database, attachment downloads, universal/stable vendor schema or active-branch selection on import |
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
fuzzy ID selection. Obtain it from your own export in an editor or from an archive
you already intentionally imported. Do not import the whole file merely to learn
an ID if that exceeds your intended scope. Local formats use the session ID:

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
