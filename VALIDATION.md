# Validation record

Current release: `0.100.20-archive-search-and-checkpoints`, dated 2026-11-19.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-19 Incremental transfer and scoped search (0.100.20-archive-search-and-checkpoints):

Normalized export can copy the baseline at a verified import checkpoint, the
messages accepted since a checkpoint, or the messages between two nested
checkpoints. Verification, selection and provenance counts share one read-only
snapshot. Scoped search can page through matching messages in one conversation.

On Windows, the focused export, import checkpoint, delta, command usage/catalog
and matching-message suites ran 77 tests with one platform-dependent skip and
no failures. Synthetic transfer tests cover both checkpoint versions, a concurrent
writer, fixed transfer intervals, duplicate-only artifacts, stale or non-nested
cutoffs, private receipts and idempotent ingest into a second archive.
