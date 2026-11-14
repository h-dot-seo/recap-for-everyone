# Private review view checkpoints

A checkpoint is a source-wide **view cutoff**, not a review decision, approval,
batch skip, backup, archive identity or completion record. The database is never
changed. Existing `review-state` decisions still work independently. This closes
the narrow gap where a renamed conversation later gains messages and is hidden
by `--unrenamed-only`: omit that option when comparing content changes.

`declare-review-checkpoint` requires a new output file and one explicit source.
It enumerates that source in one read transaction, including more than one page,
and saves a private unsigned `recap.review-checkpoint.v1` document. Optional
`--declared-at YYYY-MM-DD` is supplied text, not a clock or attestation. The stdout
receipt omits source/conversation IDs and bodies; the saved document contains
**every conversation ID and content hash**. Store it privately. Both writing and
reading are capped at 64 MiB. Input is strict JSON with exact fields, sorted unique
IDs, valid hashes/revisions and an entries digest. An initial UTF-8 BOM is accepted.
Recomputing a digest detects accidental inconsistency, not forgery or authenticity.

`review-titles --since-checkpoint FILE` checks the file's exact source before
opening the database, then compares within the queue's single read transaction.
Without the option, existing output and behavior are unchanged. The comparison
counts cover the **entire source before other filters**:

- `new`: identity absent from the checkpoint;
- `changed_content`: existing identity whose message fingerprint differs;
- `changed_title`: existing identity with a different local title revision;
- `unchanged`: neither differs;
- `missing_from_archive`: checkpoint identity absent from this source snapshot.

Content/title changes can overlap; never add those two counts as a distinct total.
The content fingerprint covers message ID, role and text in insertion order, not
timestamps or provenance. A different import order can change the fingerprint.
A no-op local title write still changes its revision. There is no archive UUID;
a missing identity can reflect another/rebuilt/edited DB, not a deletion decision.
Review-state revisions are deliberately absent from the checkpoint.

Filter order is unrenamed, checkpoint changes, explicit `--conversation` IDs,
`--supplied-only`, current state, then pagination. Filters intersect. Checkpoint
exclusions are counted only after unrenamed filtering; comparison counts remain
source-wide. The sum of excluded renamed/checkpoint/unselected/unsupplied/state
counts plus `total_conversations` equals `source_total_conversations` (absent
optional exclusions mean zero). Existing-title collisions still scan the entire
source, including unchanged or otherwise excluded conversations. A saved queue
can be rendered or selected for a fresh preview as before. No title is applied.

## Synthetic first-to-second export walkthrough

Use an existing writable private `OUTPUT` directory outside the checkout. The
new `checkpoint-demo` subdirectory and all output paths must be absent. Inputs
are invented by the unchanged training generator, not account collection.

```sh
python examples/make_review_demo.py OUTPUT/checkpoint-demo
python recap.py prepare-web-export OUTPUT/checkpoint-demo/web.zip --member conversations-001.json --output OUTPUT/first.json
python recap.py prepare-web-export OUTPUT/checkpoint-demo/web.zip --member conversations-002.json --output OUTPUT/second.json
python recap.py --db OUTPUT/checkpoint.sqlite import OUTPUT/first.json --source fictional --format web
python recap.py --db OUTPUT/checkpoint.sqlite declare-review-checkpoint --source fictional --declared-at 2026-01-01 --output OUTPUT/view-cutoff.json
python recap.py --db OUTPUT/checkpoint.sqlite import OUTPUT/second.json --source fictional --format web
python recap.py --db OUTPUT/checkpoint.sqlite review-titles --source fictional --since-checkpoint OUTPUT/view-cutoff.json
```

The final page contains six new identities (`web-06` through `web-11`), not six
approved titles. Advance the baseline only by explicitly creating a **new** file
after the operator's scoped work. Never overwrite or silently advance it. Failed
publication follows the existing staged hard-link contract; inspect any reported
leftover staging file. Page offsets are still not durable completion checkpoints.
