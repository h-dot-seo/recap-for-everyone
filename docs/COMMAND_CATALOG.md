# Discover the local command contract

`describe` lists the unified CLI's current command declarations and structured
parser options without opening an archive or input file. It is not another
archive description: `describe-schema` still inspects an explicitly selected DB.
No existing command output gains a new envelope or schema label.

## Read the catalogue before choosing an action

These commands read only installed command metadata and the release label in the
publication manifest. No scratch input or output is required:

```sh
python recap.py describe
python recap.py describe title
python recap.py describe rebuild-archive
```

The report label is `recap.command-catalog.v1`. The release is the value declared
in the local publication manifest, or null if it cannot be read as a valid label.
It is not a verification result; use `verify_manifest.py` to verify the published
inventory. A catalogue from different code may describe different commands.

DB requirements distinguish required `--db`, accepted-but-ignored `--db`, and
rejected `--db`. Rehearsal/rebuild commands can reject global `--db` while still
opening their explicit restored/new database arguments. Read the opening and
conditional effect declarations rather than inferring behavior from the name.
`title` and `review-state` only write the archive with a supplied change; optional
saved outputs add new-file writes. Rebuild can publish a new DB and then fail to
publish its receipt. Its explicit preservation warning remains authoritative.

Effect declarations are static descriptions tested with synthetic inputs, not a
sandbox or permission grant. They do not authenticate editable review files,
operator consent, supplied text or source ownership. SQLite can use journal or
internal temporary files even when an action has no requested document output.
A read-only connection is not a promise that no SQLite sidecar can ever appear.

## Exit status is not enough

- 0: the command completed normally; inspect its documented result and limits.
- 1 with a JSON result: a documented negative result may still be valid output,
  such as conflicts, unsupported local replay, stale provenance, an unverified
  cutoff, or failed recovery/rebuild checks. Read the result before retrying.
- 1 with empty stdout and diagnostic stderr: handled execution failure. A filesystem or
  publication failure does not necessarily undo already completed work.
- 2: argparse usage error, including DB argument policy errors.
- An unexpected traceback is a defect, not a newly classified error code.

No JSON error envelope or inferred exception-code mapping is introduced.
Conditional flags and result labels describe only their declared paths. Outputs
without an existing top-level schema remain unlabelled; a bare search array is
not silently wrapped. Source text and editable documents remain untrusted.

Follow [SKILL.md](../SKILL.md) for authorization and human-review boundaries.
Import needs approved sources, local title changes need approved wording, and
review-state writes record an operator decision. Discovery itself approves none
of these. Existing protected example commands and default outputs are unchanged.

## Executed effect regressions

The test suite binds its read-case names to all unified commands whose declared
**default** write list is empty. Each case must actually complete with its expected
exit status and valid result before the test compares every file byte and path in
the synthetic scratch tree. Source exports, prepared documents and the archive are
part of that comparison, not just the database's main file.

Conditional saved outputs are exercised separately: a requested new document must
appear and existing inputs/archive bytes must remain unchanged. Explicit approved
synthetic title and review-state changes are checked as writes, not relabelled as
read-only. Documented negative result statuses have separate cases. Fault-injected
mutations and failed invocations must be caught by the assertion helper.

Coverage is for those synthetic invocations on an explicitly closed DELETE-mode
archive. It is not exhaustive option-combination testing, arbitrary schema
validation, an OS access monitor, a hostile namespace sandbox, or a claim that WAL
and journal sidecars can never be created. It grants no permission to run commands
against a person's data. Static declarations still need review when code changes.
