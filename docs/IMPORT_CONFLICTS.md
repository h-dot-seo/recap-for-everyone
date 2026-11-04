# Diagnose a reimport without changing the archive

`inspect` validates the source file, and `list-export` helps choose an identity.
Neither opens your database. `check-import` adds an optional read-only comparison
against an **existing** Recap archive before you decide to import again.

For a synthetic walkthrough, choose a new private scratch directory outside this
repository. If the path exists, choose another instead of overwriting it:

```sh
mkdir ../recap-conflict-demo
python recap.py --db ../recap-conflict-demo/archive.sqlite import examples/web-export.json --format web --source demo
python recap.py --db ../recap-conflict-demo/archive.sqlite check-import examples/web-export.json --format web --source demo
```

The check reports two unique identities identical to the archive and
`status:"NO_CONFLICTS"`. It imports nothing. If an otherwise identical later web
export has a different source conversation title, the check instead reports
`title_only` conflicts. The importer still rejects them: original titles are
preserved evidence, not the mutable local display-title override.

The standalone equivalent is:

```sh
python import_check.py --db ../recap-conflict-demo/archive.sqlite examples/web-export.json --format web --source demo
```

Both commands support `local` and `local-codex`, optional `--conversation`, and
`--expected-export-sha256` from an earlier inventory or inspection. Selection and
hash validation happen before database access. A missing database is not created;
use ordinary source inspection when preparing a new archive.

## Counts and conflict samples

The comparison follows the importer's exact identity and value rules:

- Identity is the source, conversation ID and message ID. Separate sources remain
  separate. Each first incoming occurrence is compared against that archive source.
- `archive_comparison` counts unique first occurrences as `new`, `identical` or
  `conflicting`. These are comparisons, not promised inserts or committed changes.
- `repeated_input` counts later occurrences as identical to or conflicting with
  the **first incoming occurrence** of the same identity. These are separate from
  archive comparisons. An identity can have both an archive conflict and an
  input repetition conflict; both count toward `total_conflicts`.
- Compared fields are role, timestamp, original title and text. Local display
  overrides are ignored. Export provenance is not repaired or rewritten.
- `title_only` means only the original title differs. `text_changed` means text
  differs, possibly alongside other fields. `metadata_changed` covers remaining
  role/timestamp/title differences. `changed_fields` makes mixtures explicit.

Samples include only the comparison type, classification, changed-field names
and a one-based `record` number. For repeated input they also include
`first_record`. These are **normalized message occurrence numbers after optional
selection**, not physical source lines or mapping-node IDs. A web title change
can therefore produce a separate conflict for every extracted message.

`--limit` bounds samples from 1 to 1000, default 20. Total counts cover all
comparisons, with `omitted_conflicts` indicating samples left out. The entire file
is parsed and all selected identities are compared; the sample limit does not
bound parsing memory, source size or database work. Whole-file extraction warnings
remain in `coverage`, even when a conversation is selected.

The JSON report goes to stdout. Exit status is zero for no identity conflicts,
one for detected conflicts, and one with an error on stderr for an invalid input
or inaccessible archive. A conflict report is not a parser error or failed write.
Argument/usage errors use the parser's exit status two. Inspect the exit status
and JSON before continuing any scripted workflow.

## Advisory, not approval or repair

All comparisons share one read-only SQLite snapshot. No artifact, provenance,
message, FTS, schema, title history or review state is added or changed. The source
is read once, and existing expected-hash checks refer to those exact bytes.

`NO_CONFLICTS` is not a guarantee that a later import succeeds. The source or
archive can change, and database permissions, constraints, triggers, disk space
or other conditions can fail. No messages is also not a successful extraction.
Normal import still checks identities under its write lock and rolls back a
conflicting batch. This report is not a lease, authorization or automatic retry.

The importer additionally rejects conflicting repeats within its selected normalized
input **before opening SQLite**, so that known input contradiction cannot leave a
new empty archive behind. Identical repeats keep their existing counts/provenance.
This does not change this read-only report's comparisons or the locked archive
checks. See [failure boundaries](INPUT_SCOPE.md#clean-failure-for-decoder-nesting-and-conflicting-incoming-records)
for selected-scope, line-number and other-failure limitations.

Keep the source and archive unchanged when investigating. A title-only conflict
is still a conflict, not permission to replace original titles. There is no
automatic merge, repair, conflict override, source renaming or deletion step.

Samples omit message IDs, title values and message bodies. `coverage.selection`
can echo an explicitly selected conversation ID, and counts/hashes are metadata.
Treat reports as private rather than assuming body-free output is anonymized or
safe to publish. No external service or model is contacted.
