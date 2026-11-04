# Review a title in one CLI

These two examples use only invented conversations bundled in `examples/`.
Python 3.10+ and SQLite FTS5 are required; there are no Python dependencies,
accounts, credentials or network requests. Run commands from the repository root.
Use a **new, private scratch directory outside the repository** for the database
and JSON outputs. Below, `../recap-demo` stands for that directory: create it first,
and substitute your chosen path. Do not reuse a directory containing important
files. Shell `>` overwrites its target even when the command subsequently fails.

The examples use a shell that writes UTF-8 redirection, such as a POSIX shell or
PowerShell 7. Windows PowerShell 5's default UTF-16 redirection is not compatible;
use a UTF-8-capable shell. Inspect the exit status after **each** command. Stop if
it is nonzero; an empty output file is not a valid proposal or preview.

## Web export: select, propose, review, apply

```sh
python recap.py inspect examples/web-export.json --format web
python recap.py --db ../recap-demo/archive.sqlite import examples/web-export.json --format web --source web-demo
python recap.py web-branch examples/web-export.json --conversation synthetic-chat --node m2
python recap.py --db ../recap-demo/archive.sqlite suggest-branch-title examples/web-export.json --source web-demo --conversation synthetic-chat --node m2 > ../recap-demo/web-proposal.json
python recap.py --db ../recap-demo/archive.sqlite preview-title ../recap-demo/web-proposal.json > ../recap-demo/web-reviewed.json
```

Open both JSON files in your editor before continuing. The proposal title should
be `Design a synthetic orchard experiment`; the reviewed file should show
`previous_title: "New chat"` and `expected_revision: 0` on a new archive.
The shipped web fixture has no `current_node`, so this walkthrough explicitly
selects `m2`. For another export use its valid current node or choose a node from
its mapping; never guess a branch from array order. Import keeps all branches.

**Only after reviewing the title, source and conversation**, run:

```sh
python recap.py --db ../recap-demo/archive.sqlite apply-title ../recap-demo/web-reviewed.json
python recap.py --db ../recap-demo/archive.sqlite list --source web-demo
python recap.py --db ../recap-demo/archive.sqlite find orchard --source web-demo
```

`apply-title` accepts the **reviewed preview**, not the original proposal. It
changes one local display title and increments its revision. It does not rename
anything in ChatGPT, rewrite the source file, or remove messages.

To reuse the same verified path for bounded provider-neutral preparation, rather
than return to raw archive text, inspect this read-only request:

```sh
python title_adapter.py --db ../recap-demo/archive.sqlite --source web-demo --conversation synthetic-chat --evidence-scope web-branch --input examples/web-export.json --node m2 prepare
```

It contains selected user text for local review, not a transmitted model request.
The adapter's `generate` command still executes only local excerpts or synthetic
mocks. [Adapter scope details](TITLE_ADAPTER.md) also cover retained local turns
and source-attributed parts. Those separate scopes do not combine replay and
attribution filtering. Any resulting proposal still needs fresh preview and review.

## Codex local export: retain raw evidence, title retained turns

```sh
python recap.py inspect examples/rollback-session.jsonl --format local-codex
python recap.py replay-local examples/rollback-session.jsonl
python recap.py --db ../recap-demo/archive.sqlite import examples/rollback-session.jsonl --format local-codex --source local-demo
python recap.py --db ../recap-demo/archive.sqlite suggest-replay-title examples/rollback-session.jsonl --source local-demo --conversation synthetic-rollout > ../recap-demo/local-proposal.json
python recap.py --db ../recap-demo/archive.sqlite preview-title ../recap-demo/local-proposal.json > ../recap-demo/local-reviewed.json
```

The projection should be `supported: true` with one retained turn and one rolled
back turn. The raw import still stores four messages. The proposal should be
`Synthetic question retained`, not the discarded question. The excerpt algorithm
is local and deterministic, **not a semantic model or validated summary**.
Review both files before applying:

```sh
python recap.py --db ../recap-demo/archive.sqlite apply-title ../recap-demo/local-reviewed.json
python recap.py --db ../recap-demo/archive.sqlite list --source local-demo
python recap.py --db ../recap-demo/archive.sqlite find discarded --source local-demo
```

The new title is visible in `list`; `find discarded` still matches the raw
conversation. This is intentional preservation, not a replay failure. Missing
source message IDs are not invented: projection IDs and archived filename-based
IDs remain separate, joined by verified source hash and line provenance.

## Errors and recovery

All title commands return exit code 1 on validation failure and explain the
failure on stderr. Do not apply an empty output or hand-edit fingerprints/revisions
to bypass a failure. JSON must be UTF-8 and duplicate keys are rejected.

- **Wrong document:** `preview-title` needs a proposal object; `apply-title` needs
  the reviewed object containing `proposal` and integer `expected_revision`.
  Generate the correct stage again rather than renaming the wrong file.
- **Unknown conversation or missing database:** check the explicit database path,
  `list --source ...`, source ID and conversation ID. Review/apply never create a
  missing database. Import only a file you intend to index.
- **Different snapshot or stale revision:** another import/title edit may have
  happened. Generate a fresh proposal and preview, then review again. Reapplying
  the same reviewed file after success is rejected, not silently repeated.
- **Export provenance mismatch or ambiguous occurrence:** keep the original bytes
  used for import. A modified export needs an intentional import and fresh
  proposal; conflicts may require a separate source namespace. Do not delete raw
  evidence to force a match. Importing a renamed ID-less file twice under the same
  source can create ambiguity and is deliberately rejected by the title bridge.
- **Unsupported replay:** `replay-local` prints `supported: false`, a fixed
  `reason_code`, and no partial transcript; it exits 1. Read the README's narrow
  supported grammar. Raw `local-codex` inspection/import may still be useful, but
  `suggest-title` on the raw archive is not a retained-history substitute. Never
  describe tools, media, compaction or inherited histories as reconstructed.

## Safety boundary

Preview is read-only. Apply rechecks the entire raw conversation fingerprint and
uses a transactional expected-revision check. An explicit apply command is your
instruction to make this local change; the program cannot certify that a human
reviewed it. JSON documents are unsigned. Descriptive projection/branch metadata
is not an authorization token. Apply checks the archive, **not the current source
file or any live platform**. Preserve the original bytes and regenerate a proposal
if you want a new file snapshot checked.

Source messages and original title evidence remain unchanged. No remote title
mutation, model call, upload, credential creation or account discovery occurs.
The general-purpose output can contain private text/titles/IDs when used on your
own exports; keep it out of public repositories. Optional `export-title-plan`
produces a manual checklist only, with `NOT_EXECUTED` status.
