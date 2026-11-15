# Open conversations identified after an import cutoff

`changed-since` still prints counts only by default. With explicit
`--delta-output NEW_JSON`, a successful cutoff comparison also saves private
conversation IDs for subsequent manual inspection. This compares multiple imports
against a stored accepted-artifact cutoff; it does not replace `check-import`,
which compares an incoming file before import.

The file is `recap.import-changes-delta.v1`. Each mutually exclusive category
(`new_conversations`, `has_new_identities`, `no_new_identities`) has a sorted ID
sample and an omitted count. `--limit` defaults to 20 and accepts integers 1..1000,
per category, like the existing import delta limit. Zero and booleans are not
valid API limits. The full counts in `delta` are not limited; neither is the
verification scan. The file is at most 8 MiB of ASCII JSON bytes followed by LF;
large IDs may require a lower sample limit. These are output bounds, not total
memory or query-time guarantees. Without delta output, limit does not alter the
existing counts-only response.

IDs come from the same read-only snapshot that verifies the cutoff. Only after
all checks pass and the connection closes is the new file published exclusively.
`CUTOFF_NOT_VERIFIED` produces no delta file. Existing paths and late competing
files are never overwritten. The original stdout result gains only a
`delta_document` hash/size/publication receipt, not IDs or message bodies. Source
labels and conversation IDs in the file may be private; store it outside public
or shared locations. A sample is not a complete selection when omitted is nonzero.

The saved file can exist even if later stdout delivery fails. Inspect the chosen
path before retrying; publication is not rolled back because a pipe closed.
Reported staging-cleanup problems retain the shared exclusive-writer contract.
No automatic review, title decision, checkpoint advance, remote action, or archive
mutation is performed. Identity changes do not prove real-world conversation
changes, completeness, or review need. The unsigned cutoff is not authentication.

## Synthetic manual follow-up

This fixture adds new conversations after one existing conversation. Unit tests
also cover additional identities in a shared conversation and repeated imports.
After inspecting the delta file, the operator explicitly chooses `epoch` below;
there is no automatic selection or approval from the file.

```sh
python recap.py --db OUTPUT/archive.sqlite ingest examples/conversations.jsonl --source synthetic-delta
python recap.py --db OUTPUT/archive.sqlite declare-checkpoint --source synthetic-delta --output OUTPUT/cutoff.json
python recap.py --db OUTPUT/archive.sqlite ingest examples/time-sample.jsonl --source synthetic-delta
python recap.py --db OUTPUT/archive.sqlite changed-since --source synthetic-delta --checkpoint OUTPUT/cutoff.json --delta-output OUTPUT/delta.json --limit 20
python recap.py --db OUTPUT/archive.sqlite show --source synthetic-delta --conversation epoch
python recap.py --db OUTPUT/archive.sqlite review-titles --source synthetic-delta --conversation epoch
```
