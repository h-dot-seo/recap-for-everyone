# Explicit normalized selection and replay

`ingest --conversation ID` is opt-in. Inspect/check-import can apply the same
selection after validating every physical record. No format is auto-detected;
normalized data still uses ingest, not the export adapter/title-plan paths.

## Complete artifact, selected messages

The artifact SHA-256, byte count and `records` count cover the entire original
file, including excluded conversations and identical repeated rows. `inserted`
counts newly inserted selected identities. A selection block reports conversation,
selected/excluded row counts and selected role counts. Stored `source_line` keeps
the original physical line number. No derived selected file is invented or required
as a recovery object. Retain the complete original file.

All rows must have valid syntax and fields, including excluded rows. Identity
conflicts are checked after selection: a conflicting excluded conversation does
not block this selection, while malformed excluded JSON still does. Missing or
invalid IDs fail before SQLite opens. Repeating a selection is idempotent;
selecting another conversation or later ingesting the whole file adds only new
identities. Artifact counts remain whole-file counts rather than silently keeping
the first selected count. First accepted message metadata stays authoritative;
reordering objects may change source hashes/lines and fail a later digest check.

File ingest retains the same two passes on one descriptor, full-input hashes and
2 GiB admission limit. The second pass must finish and match before commit. Failures
roll back the transaction; initialization can still leave a new empty schema file.
No immutable-snapshot, hostile change-and-restore, total-memory or filesystem-race
protection is promised.

The Python APIs accept the same conversation keyword. Combining it with a non-None
`provenance` argument, including an empty list, is explicitly unsupported and fails
before database access. Existing calls without selection retain their behavior.
Inline origin fields remain ignored extra input members, not verified provenance.
No original_exports, supplied-origin or selection-history ledger is created.

Inventory now reports normalized selection support and corresponding counts.
That is capability metadata, not conflict-free admission, human approval or proof
of completeness. IDs and titles may be private. Existing web/local/local-codex
inventory behavior is unchanged.

## Replay is explicit, not inferred

Use `recap.rebuild-plan.v2` only when selecting normalized conversations. It has
the same exact step fields as v1. For normalized steps, label remains null;
conversation may be null (whole file) or a nonempty explicit ID. Local/web step
rules are unchanged. New v2 replay receipts identify the plan schema and normalized
step conversation/selection so the result cannot be mistaken for whole-file replay.

Plan v1 remains supported with its existing normalized-null rule. Older releases
reject v2 rather than silently ignoring selection: this is forward incompatibility,
not universal compatibility. Recovery manifest v1/v2/v3 formats are unchanged.
Their existing artifact metadata and actual message digests can describe selected
archives. Whole-file v1 replay of a partial declaration fails the count/digest
checks instead of publishing an overfilled DB.

Supply steps in the intended replay order. There is no automatic derivation of
selection or original insertion order. Title/review history, all version-specific
exclusions and the false full-archive-restored claim boundary stay unchanged.
Publication of the new DB and receipt is not atomic as a pair; a verified DB may
remain if receipt publication fails. Inspect partial results before retrying.
The implementation hashes in old-style rebuild receipts change when their actual
source changes; no hash is fixed artificially to imitate old source bytes.

## Synthetic end-to-end example

Start with an empty OUTPUT directory outside the checkout. These commands inspect
and select the existing fictional `epoch` conversation, retain the original file
under examples, and explicitly write a v2 plan without guessing its selection:

```sh
python recap.py inspect examples/time-sample.jsonl --format normalized --conversation epoch
python recap.py --db OUTPUT/archive.sqlite ingest examples/time-sample.jsonl --source synthetic --conversation epoch
python recap.py --db OUTPUT/archive.sqlite check-import examples/time-sample.jsonl --format normalized --source synthetic --conversation epoch
python recap.py --db OUTPUT/archive.sqlite declare-recovery --manifest-version 3 --declared-at 2026-11-15 --output OUTPUT/manifest.json
python -c "import hashlib,json; from pathlib import Path; raw=Path('examples/time-sample.jsonl').read_bytes(); plan=dict(schema='recap.rebuild-plan.v2',steps=[dict(source='synthetic',kind='normalized',object_sha256=hashlib.sha256(raw).hexdigest(),label=None,conversation='epoch',newline='lf')]); f=Path('OUTPUT/plan.json').open('x',encoding='utf-8'); json.dump(plan,f); f.close()"
python recap.py rebuild-archive OUTPUT/manifest.json --plan OUTPUT/plan.json --objects examples --new-db OUTPUT/rebuilt.sqlite --output OUTPUT/rebuild.json
```

The plan is supplied data, not an approval token. This example never accesses a
personal export, contacts a service or modifies the retained source. For the v1
documentation shape and its limits, see [DOCUMENT_SCHEMAS.md](DOCUMENT_SCHEMAS.md).
