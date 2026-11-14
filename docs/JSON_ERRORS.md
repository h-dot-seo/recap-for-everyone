# Opt-in structured execution errors

The unified CLI accepts global `--json-errors` before the subcommand. It changes
only caught execution errors that already exit 1: stderr becomes one ASCII JSON
object with `schema: recap.error.v1`, `code`, `message` and `exit_status: 1`.
Without the flag, existing stderr text is unchanged. Standalone entry points keep
their current plain diagnostics even when they share the underlying library.

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
