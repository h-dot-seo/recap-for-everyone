# Replay declared v2 content into a new archive

`rebuild-archive` accepts an explicitly supplied recovery manifest v2 and the
existing `recap.rebuild-plan.v1` plan. It replays authorized retained objects into
a private staging database, verifies the declared replayable rows and publishes a
new database only if those checks pass. It never opens or rewrites the original
archive. This is **not full archive restoration**.

## Synthetic walkthrough

Use a fresh OUTPUT directory outside the repository. The reference archive and
plan below are synthetic; no private data or remote service is involved.

```sh
python recap.py --db OUTPUT/reference.sqlite ingest examples/conversations.jsonl --source demo
python recap.py --db OUTPUT/reference.sqlite declare-recovery --manifest-version 2 --declared-at 2026-11-14 --output OUTPUT/manifest-v2.json
python recap.py rebuild-archive OUTPUT/manifest-v2.json --plan examples/rebuild-plan.json --objects examples --new-db OUTPUT/rebuilt-v2.sqlite --output OUTPUT/rebuild-v2.json
```

Expected: `recap.rebuild-receipt.v2`, `REBUILD_REHEARSAL_PASSED` and
`full_archive_restored: false`. The receipt's `manifest.schema` records v2.
`new_database_created_exclusively: true` means this operation published that new
file, not that the directory was clean, all data was recovered or backups exist.

## Decisions are not source objects

Title and review decisions cannot be replayed from the original exported message
objects. Their two checks are listed in `excluded_checks`, not inserted as PASS
or as successful skipped checks. `not_rebuildable_from_objects` identifies whichever
of `title_history` and `title_review_history` were declared (including empty tables).
They are excluded from expected tables and from integrity-failure NOT_RUN lists
as well. No history is invented, copied from another database or silently reset.

If those histories were declared, a later full `rehearse-recovery` of the rebuilt
DB against that v2 manifest still fails their missing-ledger checks. Use a retained
restored database copy for that purpose. A successful rebuild receipt is not a
substitute for a successful restored-copy rehearsal.

## Everything else stays checked

The object inventory, hash-bound reads, explicit plan source/format/label/selection/
newline/order, message/artifact/source checks, FTS checks and all declared
provenance/topology digests still apply. Unexpected, missing or changed replayable
ledgers fail verification; no table is created or dropped just to force a match.
Absent and empty tables remain different. V2 therefore detects count-preserving
occurrence changes and topology ordering/text-membership changes.

The original-export object authorization still uses the existing occurrence-based
inventory. Legacy-only archives and exports with no extracted messages may lack
the required original hash, even if topology retains it. The tool does not guess
or widen permission from that topology. An export with another declared text
conversation can still reproduce its textless conversation nodes. These are
explicit limitations, not reasons to skip failing checks.

The plan order is executed, but the logical message digest does not include
`message_pk`; it does not establish complete original archive insertion order.
Neither a matching hash nor a supplied plan establishes authenticity, consent,
rights, completeness, remote retention or future recoverability.

## Existing publication and v1 behavior

All [existing failure and publication boundaries](AUTOMATED_REBUILD.md#publication-failure-and-privacy)
remain: exclusive new files, closed staging connections, no replacement fallback,
failed verification leaves no published DB, cleanup status is explicit, and a DB
already published is preserved if receipt publication then fails. Inspect the
actual outcome before retrying at the same paths. The two outputs are not atomic.

V1 receipt fields, check order, outcome semantics and side effects are unchanged.
The recorded implementation hashes must change when their actual files change;
the receipt's hash consequently changes too. Tests compare v1 behavior with only
those evidence-bound fields excepted, never freeze stale hashes to claim identical
bytes. Default v1 declaration and restored-copy rehearsal documents remain
byte-compatible. No migration, stamp, fingerprint, automatic re-sealing or policy
change is introduced.
