# Explicit accepted-identity checkpoint

The default artifact cutoff remains `recap.import-checkpoint.v1`. It deliberately
fails verification when later selections accept new identities from an already
saved artifact. This is not corruption detection proof: the old cutoff cannot
separate those newly accepted identities. Existing v1 files are never upgraded,
reinterpreted or overwritten automatically.

Choose `declare-checkpoint --checkpoint-version 2` for that incremental selection
workflow. The new `recap.import-checkpoint.v2` saves sorted unique SHA-256 identity
tokens plus the existing logical message digest. Tokens hash compact ASCII JSON
`[source_id,conversation_id,message_id]` followed by LF, without Unicode folding,
normalization or trimming. The declaration receipt, comparison and optional delta
file use their respective `.v2` schema labels. `changed-since` selects the contract
from the explicitly supplied checkpoint; there is no inferred migration or separate
comparison mode. Older readers reject v2. This is forward incompatibility, not
universal compatibility. Default declarations and all v1 behavior remain unchanged.

## What verification means

Every saved identity must occur exactly once, with matching logical content under
the existing nine-field digest: source, conversation, message, role, timestamp,
original title, text, source artifact hash and physical source line. Saved artifact
metadata must remain present. New accepted identities may share an old artifact.
Existing identity changes or deletion produce `CUTOFF_NOT_VERIFIED`, no claimed
delta and no delta file. Local rowids, paths and insertion order alone are not
identity; changed accepted source hashes/lines are real logical differences.

Optional provenance, topology, supplied origin claims, title histories and review
histories are outside this message digest. This does not authenticate sources,
prove completeness, establish rights, restore an archive or authorize review.
Identity hashes can be guessed from candidate IDs and linked across checkpoints;
they are private data, not anonymization. Duplicate identity tokens are rejected;
SHA-256 collision or second-preimage impossibility is not guaranteed. The unsigned
checkpoint itself is an operator declaration, not tamper-proof authentication.

The existing 64 MiB total document limit remains, without an override. Membership
has one fixed-size hash per saved identity, approximately 72 serialized bytes each
before other fields. The actual total is checked; there is no guaranteed maximum
message count. Parsing and identity sets require additional Python memory. This
file-byte limit is not a heap or total query-memory bound. Comparison still scans
all accepted rows. Selected ingest's own two-pass input/transaction behavior is
unchanged; the checkpoint does not add staging copies of private message bodies.

Outputs remain exclusive new files. Verification and connection close precede
delta publication; failures do not advance the checkpoint. A published delta file
may remain after a later stdout failure. Inspect existing outputs before retrying.
Limit and omitted counts retain their v1 meanings. Default stdout contains counts,
not conversation IDs or message bodies; explicit delta files contain private IDs.

## Synthetic same-artifact selection

Use a fresh OUTPUT directory outside the checkout. Both selections refer to the
same retained fictional input. After verification the user may inspect the delta
manually; no checkpoint, title or review state advances automatically.

```sh
python recap.py --db OUTPUT/archive.sqlite ingest examples/time-sample.jsonl --source synthetic-membership --conversation epoch
python recap.py --db OUTPUT/archive.sqlite declare-checkpoint --source synthetic-membership --checkpoint-version 2 --output OUTPUT/cutoff.json --declared-at 2026-11-15
python recap.py --db OUTPUT/archive.sqlite ingest examples/time-sample.jsonl --source synthetic-membership --conversation later
python recap.py --db OUTPUT/archive.sqlite changed-since --source synthetic-membership --checkpoint OUTPUT/cutoff.json --delta-output OUTPUT/delta.json
```

See [artifact cutoffs](IMPORT_CHECKPOINT.md) for the unchanged default and
[delta files](CHECKPOINT_DELTA.md) for output privacy and partial-success limits.
Use [incremental export](INCREMENTAL_EXPORT.md) to transfer the newly accepted
messages from a verified cutoff.
