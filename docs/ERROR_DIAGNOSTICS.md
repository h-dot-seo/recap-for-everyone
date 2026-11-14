# Private-data-conscious CLI failure diagnostics

The unified `recap.py` and compatible standalone command entry points use fixed
stderr messages for caught OS, SQLite, JSON-decoder and Unicode-decoder exceptions.
Those messages do not echo exception values, input bytes, absolute paths or staging
names. They identify the observed exception category, not a diagnosis of whether
a file is missing, permissions are wrong or an archive is corrupt. Check the
explicit input/output arguments and retained source files locally.

Existing deliberate validation messages remain unchanged, including documented
physical line numbers, basename-derived identities and numeric limits. Adapter
commands keep their existing bare error codes. This is not a guarantee that every
possible validation message contains no operator-supplied data. Argparse usage
errors still follow argparse behavior, and unexpected programming exceptions are
not silently converted into success or hidden by a catch-all handler.

Caught exception categories use these fixed messages: `Filesystem operation failed`,
`SQLite operation failed`, `JSON decoding failed`, and `Text decoding failed`.
They are intentionally coarse and identical across platforms. Exact existing
code-authored publication/protection messages remain exceptions, including occupied
output names, incomplete writes, unavailable read-only protections and the rebuild
partial-publication warning below. Arbitrary exception text is not whitelisted.

## Interpret exit status and output together

- Exit 0: the command completed; read its result and boundaries.
- Exit 1 with nonempty stdout: a result document may report a failed check. Read
  `status`, `reason_code` or `conflicts_found`; do not treat it as a stderr error.
  Examples include import conflicts, unverified cutoffs and failed recovery.
- Exit 1 with empty stdout: a handled execution error is reported on stderr.
- Exit 2: argument usage error. Correct the command before retrying.

An error does not establish that no write occurred. Ingest/schema initialization,
explicit title writes and output receipt failures have their existing documented
transaction/publication boundaries. Check the resulting artifact or archive when
an outcome is uncertain; do not blindly retry a mutation. The default formatter remains plain text. The unified CLI can now opt into
[structured execution errors](JSON_ERRORS.md) with global `--json-errors`; it uses
the same diagnostic message and grants no permission or automatic recovery action.

## Executable synthetic failure example

Create an empty `OUTPUT` directory outside the checkout. Both commands below are
expected to exit 1, print no stdout, and leave the missing archive absent. The
fixed stderr diagnostic intentionally does not distinguish a missing file from
other reasons SQLite could not open an archive.

```sh
python recap.py --db OUTPUT/missing-private.sqlite stats
python conversation_search.py --db OUTPUT/missing-private.sqlite synthetic
```

Saved title-document publication still refuses existing destinations and late
collisions by exclusive publication. Missing parents and
OS-level failures use the same safe diagnostic path. The operator must choose a
new output name, not overwrite or relax these guards.

For rebuild specifically, if the new database was already published but writing
the receipt fails, stderr retains a fixed partial-success warning: the database
was preserved. Inspect the requested new database before retrying. The destination
path itself is not echoed in that error. Existing stdout receipts may intentionally
include paths and have not been changed by this stderr-only work.
