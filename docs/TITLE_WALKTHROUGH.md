# Review a title in one CLI

These two examples use only invented conversations bundled in `examples/`.
Python 3.10+ and SQLite FTS5 are required; there are no Python dependencies,
accounts, credentials or network requests. Run commands from the repository root.
First follow [installation and runtime checks](INSTALL.md) to obtain the workflow
branch and choose a working launcher. Substitute that launcher for each leading
`python`; a system with only `python3` need not provide a `python` command.
Use a **new, private scratch directory outside the repository** for the database
and JSON outputs. Below, `../recap-demo` stands for that directory: create it first,
and substitute your chosen path. Do not reuse a directory containing important
files. Use new filenames in an operator-controlled private directory with an
existing parent. The native `--output NEW_JSON` commands below write UTF-8 JSON
without a BOM and keep Unicode readable. No shell `>` or special shell encoding
is needed. Existing files, directories and symlinks are refused, not replaced.
Publication uses a same-directory staging file and an atomic hard link; a
filesystem without hard-link support fails rather than falling back to overwrite.
See [saved title documents](TITLE_DOCUMENT_FILES.md) for details.

Inspect the exit status after **each** command and stop if it is nonzero. With
`--output`, stdout is a metadata-only `recap.saved-title-json.v1` receipt with
`status: SAVED`, `document_kind` (`proposal`, `preview` or `queue`), byte count and
SHA-256. It is not the document to preview or apply. Check
`staging_cleanup_complete`; if false, the output already exists, so inspect the
`remaining_staging_file` in its directory rather than blindly retrying. Open the
actual saved document for review. Saving does not approve a title.
Without `--output`, these commands still print the original JSON document.
Legacy redirected examples elsewhere still require UTF-8 shell redirection, not
Windows PowerShell 5's default UTF-16; `>` may overwrite before validation.

## Web export: select, propose, review, apply

```sh
python recap.py inspect examples/web-export.json --format web
python recap.py --db ../recap-demo/archive.sqlite import examples/web-export.json --format web --source web-demo
python recap.py web-branch examples/web-export.json --conversation synthetic-chat --node m2
python recap.py --db ../recap-demo/archive.sqlite suggest-branch-title examples/web-export.json --source web-demo --conversation synthetic-chat --node m2 --output ../recap-demo/web-proposal.json
python recap.py --db ../recap-demo/archive.sqlite preview-title ../recap-demo/web-proposal.json --output ../recap-demo/web-reviewed.json
```

Open both JSON files in your editor before continuing. The proposal title should
be `Design a synthetic orchard experiment`; the reviewed file should show
`previous_title: "New chat"` and `expected_revision: 0` on a new archive.
The shipped web fixture has no `current_node`, so this walkthrough explicitly
selects `m2`. For another export use its valid current node or choose a node from
its mapping; never guess a branch from array order. Import keeps all branches.
If a later user request names the useful topic, [select an exact message within
the verified branch or retained turns](TITLE_REVIEW_HINTS.md#choose-a-later-message-inside-a-verified-branch-or-retained-history)
instead of giving up those scope checks to use raw evidence.

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
python recap.py --db ../recap-demo/archive.sqlite suggest-replay-title examples/rollback-session.jsonl --source local-demo --conversation synthetic-rollout --output ../recap-demo/local-proposal.json
python recap.py --db ../recap-demo/archive.sqlite preview-title ../recap-demo/local-proposal.json --output ../recap-demo/local-reviewed.json
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

- **Existing output or unsupported filesystem:** choose a new private filename and
  check that its parent exists. Never delete valuable output just to retry. If
  hard links are unavailable, use a suitable operator-controlled filesystem;
  native saving does not promise universal filesystem support. A receipt with
  incomplete staging cleanup means the saved document already exists.
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
  `reason_code`, and no partial transcript; it exits 1. Read the
  [narrow supported grammar](WORKFLOWS.md#opt-in-completed-turn-text-projection). Raw `local-codex` inspection/import may still be useful, but
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
