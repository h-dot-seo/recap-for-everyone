# Opt-in structured execution errors

The unified CLI accepts global `--json-errors` before the subcommand. It changes
only caught execution errors that already exit 1: stderr becomes one ASCII JSON
object with `schema: recap.error.v1`, `code`, `message` and `exit_status: 1`.
Without the flag, existing stderr text is unchanged. The standalone product
entry points listed below accept the same opt-in flag; their default diagnostics
remain plain, including the adapter's existing bare error codes.

## Synthetic failure example

Create an empty directory named OUTPUT outside this checkout and replace the
placeholder. Do not create `missing.sqlite`. The first command succeeds; the
second intentionally exits 1 with an ARCHIVE_ERROR object on stderr and no stdout.
Neither command creates that database:

```sh
python recap.py --json-errors describe stats
python recap.py --json-errors --db OUTPUT/missing.sqlite stats
```

ARCHIVE_ERROR does not mean DB_MISSING. Permissions, invalid database bytes and
other SQLite failures can have the same exception family. Correct the actual
problem; never create or overwrite a database just because a code was returned.

## Codes are explicit, not guessed from message text

| Code | Source of classification |
|---|---|
| SOURCE_CHANGED | Explicit checked source hash mismatch at supported normalized/export/ZIP paths |
| STALE | Explicit supported revision/content, plan/request or cursor-state mismatch |
| UNKNOWN_IDENTITY | Explicit supported conversation/message lookup failure |
| PATH_UNAVAILABLE | Recorded web topology is missing, ambiguous, inconsistent or excludes the selected node/hash |
| CURRENT_NODE_UNAVAILABLE | The chosen recorded export supplies no usable current-node pointer; explicit node selection is required |
| CONFLICTING_IDENTITY | Incoming or stored normalized message identity conflict |
| OUTPUT_EXISTS | FileExistsError |
| FILE_ERROR | Other caught OSError |
| ARCHIVE_ERROR | Caught sqlite3.Error |
| UNCLASSIFIED | Other already-caught execution errors without an explicit code |

The first four are ValueError subclasses raised at selected existing checks. Their
messages and validation order are retained. Classification is intentionally
incomplete; an unclassified error is not evidence that no conflict or stale state
exists. Codes do not establish blame, permission, retry safety or recoverability.
There is no message-substring classifier and no automatic repair or retry.

The message uses the same safe diagnostic formatter as the normal CLI. Low-level
filesystem/SQLite/decoder details stay fixed and content-free. Existing authored
validation messages remain unchanged and can contain supplied labels. This is not
a blanket private-data sanitizer; do not publish diagnostics without review.

## Paths that do not become error envelopes

- argparse usage/policy errors remain exit 2 and plain stderr, including missing
  or rejected global DB arguments. The option follows normal argparse placement.
- Documented negative results remain their original stdout JSON with exit 1 and
  empty stderr: conflicts, unsupported replay, stale provenance, unverified
  cutoff, failed rehearsal or failed rebuild checks.
- Successful stdout and saved documents keep their existing shapes.
- Unexpected exceptions remain defects; this flag does not widen the catch set
  or turn every traceback into a supported error.

No JSON output means no universal rollback promise. In particular, a rebuild can
publish its verified new DB and fail while publishing the receipt. The existing
fixed 'database was preserved' advisory remains in the structured message; inspect
the new DB before retrying. Do not overwrite published outputs or alter a supplied
hash/revision to make an error disappear.

The envelope describes a failure, not source authenticity, completeness, authorship,
consent, retention or recovery readiness. No model or network is called by error
formatting. See [command discovery](COMMAND_CATALOG.md) for command effects and
[diagnostic boundaries](ERROR_DIAGNOSTICS.md) for the existing privacy scope.

## Standalone product entry points

The same opt-in flag is available on `attributed_title.py`, `branch_title.py`,
`conversation_search.py`, `conversation_view.py`, `export_inventory.py`,
`import_check.py`, `recovery.py`, `replay_local.py`, `replay_title.py`,
`session_workflow.py`, `title_adapter.py`, `title_history.py`, `title_plan.py`,
`title_proposal.py`, `title_suggestion.py` and `web_branch.py`. Put it before the
subcommand when that parser has subcommands. Runtime checks, publication tools,
benchmarking and the MCP protocol are separate interfaces and are not changed.

Fourteen parsers wrap only their existing caught exception boundary using the
same typed classification as the unified CLI. The title adapter instead records
its existing closed error code, with that same code as the message; its existing
unexpected-error fallback remains PROVIDER_FAILED. No new exception diagnosis,
provider call, consent or permission is introduced. Replay-local has no caught
execution-error boundary: accepting the option does not transform unsupported
replay documents or their exit status.

Successful output, ordinary default stderr, usage exit 2, conflict/rehearsal/replay
negative stdout results and already-published output on a later failure keep their
existing contracts. An envelope does not prove that nothing was written, identify
a safe retry, or authorize changing a source, revision or output destination.
