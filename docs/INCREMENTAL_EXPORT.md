# Transfer messages accepted since a checkpoint

Use `export-normalized --since-checkpoint FILE` to move additions into an archive
that already has your earlier export. It writes one private JSONL record per
newly accepted identity, including new messages in older conversations. The
optional `--conversation ID` narrows the transfer to that exact conversation.
To freeze the transfer at a known stopping point, also supply
`--through-checkpoint FILE`. Used alone, this flag exports the baseline held by
that checkpoint. Used together, the flags export exactly the identities added
between the two checkpoints, even if more imports have arrived since.

## Try it with a synthetic archive

Start with an empty private output directory and substitute its path for
`OUTPUT`. This example first transfers the fictional `epoch` conversation, then
transfers two messages selected later from the same retained input file. A third
import arrives after the second checkpoint. It waits for a later transfer.

```sh
python recap.py --db OUTPUT/source.sqlite ingest examples/time-sample.jsonl --source synthetic --conversation epoch
python recap.py --db OUTPUT/source.sqlite declare-checkpoint --source synthetic --checkpoint-version 2 --output OUTPUT/cutoff.json
python recap.py --db OUTPUT/source.sqlite export-normalized --source synthetic --through-checkpoint OUTPUT/cutoff.json --output OUTPUT/base.jsonl
python recap.py --db OUTPUT/moved.sqlite ingest OUTPUT/base.jsonl --source moved
python recap.py --db OUTPUT/source.sqlite ingest examples/time-sample.jsonl --source synthetic --conversation later
python recap.py --db OUTPUT/source.sqlite declare-checkpoint --source synthetic --checkpoint-version 2 --output OUTPUT/next.json
python recap.py --db OUTPUT/source.sqlite ingest examples/time-sample.jsonl --source synthetic --conversation offset
python recap.py --db OUTPUT/source.sqlite export-normalized --source synthetic --since-checkpoint OUTPUT/cutoff.json --through-checkpoint OUTPUT/next.json --output OUTPUT/additions.jsonl
python recap.py --db OUTPUT/moved.sqlite ingest OUTPUT/additions.jsonl --source moved
```

The destination now has three messages. Re-ingesting the additions there inserts
zero more. After confirming the destination accepted the transfer, use
`--since-checkpoint OUTPUT/next.json` to pick up the still-pending `offset`
conversation. Retain the two checkpoints if you need to repeat the same interval.

## Verification and output

The CLI validates each supplied checkpoint for the explicit source, then opens
one read-only archive snapshot. It checks the entire saved cutoff even when
exporting one conversation. A changed or missing saved message or artifact
fails the export before staging any text. A v1 artifact cutoff also fails if a
later selection adds identities from a previously declared artifact. Choose a
v2 membership checkpoint before making such selections.

When both cutoffs are supplied, the ending cutoff must contain every artifact
and accepted identity in the starting cutoff. The command verifies containment
across the entire source, independent of date labels and the conversation filter.
Equal checkpoints select zero messages. Either flag accepts either checkpoint
version. Both verification and export see the same archive snapshot.

Either flag selects receipt schema `recap.normalized-export-receipt.v2`.
The receipt identifies each supplied checkpoint version in
`since_checkpoint_schema` or `through_checkpoint_schema`. For each supplied
cutoff, `since_checkpoint_sha256` or `through_checkpoint_sha256` matches the
`checkpoint_sha256` in its declaration receipt. These digests identify the
complete validated document serialized in declaration field order, with ASCII
JSON, two-space indentation and a final LF. An equivalent API dictionary or a
file with different whitespace, encoding markers or object key order has the
same digest. To verify the original bytes of a reformatted file, hash that file
separately. Both export statuses carry these digests. They can link receipts for
the same cutoff without disclosing its message identities.
Check its status before using the output path.

- `EXPORTED` reports `published: true`, the record and conversation counts,
  byte count and SHA-256. The file uses the regular normalized JSONL fields and
  archive insertion order. Omitted provenance occurrences count only exported
  identities.
- `NO_NEW_MESSAGES` is a successful comparison with zero selected additions.
  It reports `published: false` and creates no file. With an explicit conversation
  the ID must exist in the source. A verified empty source is valid without a
  conversation filter.
- A stale or malformed cutoff, non-nested interval, source mismatch, unknown conversation, or
  occupied output path fails the command. Choose a fresh path for each call.
  An already published file survives a later failure delivering stdout.

Comparison and export run locally and do not advance a checkpoint. With only
the starting cutoff, each retry includes all additions visible when that call
begins reading. Keep an ending cutoff for a repeatable set of identities. The
file uses insertion order in the current archive, so rebuilding the archive in a
different order can change the derived bytes.

If you specify a conversation, the transfer covers that conversation only.
Reusing its ending cutoff as a source-wide starting point can skip additions in
other conversations. Transfer the whole interval before advancing a source-wide
baseline.

The receipt omits source labels, conversation and message IDs, titles and text.
The private output includes all six normalized fields and can contain sensitive
content. Re-ingest gives the derived file its own artifact hash and physical
line numbers. Original provenance, display titles, and review history stay in the
source archive. The checkpoint does not establish possession of the baseline
at the destination or authenticate its contents.

Verification scans the source. V2 uses memory proportional to the saved identity
membership, and output encoding buffers a message at a time. See
[checkpoint membership](MEMBERSHIP_CHECKPOINT.md) and
[normalized output bytes and privacy](EXPORT_NORMALIZED.md).
