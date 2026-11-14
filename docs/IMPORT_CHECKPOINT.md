# Accepted-artifact import cutoff

`declare-checkpoint` records one explicitly selected source's normalized artifact
rows and accepted messages in a new private `recap.import-checkpoint.v1` file.
`changed-since` verifies that declared subset before reporting counts. Neither
command imports, modifies SQLite, approves an import or records review completion.
The separate [review view cutoff](REVIEW_CHECKPOINT.md) compares content and local
title revisions; this cutoff instead checks the original accepted artifact lineage.

## Verification and interpretation

The declaration contains `source`, operator-supplied `declared_at`, artifact hashes,
byte/record counts, message count and a logical messages digest. It contains no
conversation IDs or message text, but source and artifact hashes are private.
Store it outside public/shared locations. The receipt and comparison output contain
no source/conversation IDs or excerpts. Dates are supplied, never read from a clock.
An empty source can be declared; this does not establish that the source exists.

Each comparison uses one read-only snapshot. Every declared artifact row must still
match. Only messages whose first-accepted `source_sha256` belongs to the declared
artifact set contribute to the checked count and digest. Later artifacts are allowed.
The digest uses compact ASCII JSON arrays followed by LF, ordered by source,
conversation and message IDs under SQLite BINARY collation, with the same nine
fields as recovery: source ID, conversation ID, message ID, role, timestamp,
original title, text, source hash and source line. It is not a file-byte digest.

Only after those checks succeed does `delta` report mutually exclusive conversation
counts: `new_conversations` has no accepted cutoff messages;
`has_new_identities` has both cutoff and later-accepted messages;
`no_new_identities` has only cutoff messages. `accepted_after_cutoff_messages`
counts accepted messages outside the declared artifact set. Empty or repeated
artifacts may add no accepted messages. This is not a count of changed exports,
semantic growth, new real-world conversations, deleted remote conversations or
items needing review. Local basename/line-derived identities can change with labels.

A mismatch returns `CUTOFF_NOT_VERIFIED`, `delta: null` and exit status 1, never a
partial delta. Malformed, oversized or wrong-source documents are rejected before
archive opening. Successful comparisons exit 0. Local title/review-state ledgers
are not included; the stored original message title is included. No archive UUID
or signature exists: a matching rebuilt subset can pass, and a consistently edited
unsigned declaration is not authenticated. The operator alone chooses a new cutoff.

Both document reading and writing are bounded at 64 MiB; source messages are scanned
in sorted order. This is not a total memory or runtime budget. Output creation is
exclusive, with no overwrite fallback. Existing `check-import`, ingest receipts and
recovery manifests are unchanged. In particular, an older recovery manifest may
fail full `artifact_rows` matching after a later import even when this restricted
cutoff still verifies. A cutoff is neither a backup nor a full recovery rehearsal.

## Executable synthetic example

The existing fictional demo supplies two disjoint sets of six web conversations.
The second import yields six new conversations, no shared-conversation additions,
and six unchanged conversations. Unit tests separately exercise shared additions,
repeated artifacts and verification failures. No real archive is used.

```sh
python examples/make_review_demo.py OUTPUT/cutoff-demo
python recap.py prepare-web-export OUTPUT/cutoff-demo/web.zip --member conversations-001.json --output OUTPUT/first.json
python recap.py prepare-web-export OUTPUT/cutoff-demo/web.zip --member conversations-002.json --output OUTPUT/second.json
python recap.py --db "OUTPUT/archive.sqlite" import OUTPUT/first.json --source synthetic-cutoff --format web
python recap.py --db "OUTPUT/archive.sqlite" declare-checkpoint --source synthetic-cutoff --output "OUTPUT/cutoff.json" --declared-at 2026-11-14
python recap.py --db "OUTPUT/archive.sqlite" import OUTPUT/second.json --source synthetic-cutoff --format web
python recap.py --db "OUTPUT/archive.sqlite" changed-since --source synthetic-cutoff --checkpoint "OUTPUT/cutoff.json"
```
