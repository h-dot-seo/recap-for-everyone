# Explicit ledger-preserving recovery declarations (v2)

Use `declare-recovery --manifest-version 2` when a restored-copy rehearsal must
compare title/review ordering, legacy provenance and recorded web topology in
addition to the existing message, artifact, occurrence and FTS checks. Default
`declare-recovery` still writes v1. Existing v1 manifests and their exact check
order remain supported unchanged; they do not gain checks they never declared.

## Synthetic self-check

Use a fresh output directory outside the repository. This example deliberately
checks the same synthetic archive, so it is a self-check, **not a restore test or
backup**. A real rehearsal should receive a separately restored copy chosen by
the operator, not a live working archive.

```sh
python recap.py --db OUTPUT/v2.sqlite import examples/web-export.json --source demo --format web
python recap.py --db OUTPUT/v2.sqlite declare-recovery --manifest-version 2 --declared-at 2026-11-14 --output OUTPUT/v2-manifest.json
python recap.py rehearse-recovery OUTPUT/v2-manifest.json --restored-db OUTPUT/v2.sqlite --output OUTPUT/v2-receipt.json
```

Standalone `recovery.py declare` accepts the same version option. Rehearsal
selects its validation contract from the input manifest's schema, not a guessed
file name or a flag. The v2 declaration, manifest and receipt have explicit `.v2`
labels; the receipt records the actual input manifest schema and byte hash.

## What v2 binds

The existing logical-row checks remain. Additionally:

- `title_history`: source, conversation, **id**, previous title, title and changed_at,
  ordered by source, conversation and id. Swapping revision IDs cannot preserve
  the digest while changing which title wins.
- `title_review_history`: source, conversation, **id**, state, content_sha256,
  title_revision and decided_at in the same identity/revision order.
- `export_provenance`: every legacy provenance field, not merely its row count.
- `export_occurrences_sha256`: all six occurrence columns (source, conversation,
  message, original_hash, locator, parent). This supplements the existing count,
  which alone cannot detect a changed repeated locator or parent. Each physical
  logical row contributes once, including duplicate rows; duplicates are not
  silently collapsed. Full-column BINARY sorting makes insertion order irrelevant.
- `export_nodes`: source, conversation, original hash, node, parent, ordinal and
  extracted-text membership. Both path ordering and textless-node distinctions
  are bound.
- `export_conversations`: source, conversation, original hash, current_node,
  current_node_state and mapping_nodes.

Each new optional ledger is `null` when absent or `{count, sha256}` when present.
The existing occurrence count retains its shape; the separate v2 occurrence digest
is null exactly when that table is absent, including an empty digest for an empty
present table.
An empty table is not an absent table. Canonical ASCII JSON row arrays plus LF
and explicit SQLite BINARY ordering make logical rows comparable across an
ordinary file copy and `VACUUM`. Physical rowids (except semantic history IDs),
indexes, page layout and file bytes are not part of these ledger digests.

A missing, newly present or changed declared ledger fails its corresponding
check. Checks remain PASS/FAIL; missing v1 declarations do not become misleading
new PASS results. V1 deliberately retains its historical title digest without
revision IDs and omits review/legacy/topology comparisons. Use a new explicitly
chosen v2 declaration when those checks are needed, never relabel an old v1 file.

## Limits and compatibility

Declaration reads one archive snapshot and exclusively publishes a new manifest.
Rehearsal reads the supplied copy and exclusively publishes a receipt, including
failed checks. Neither repairs or rewrites the archive, replaces an old manifest,
changes a schema stamp, chooses a license nor automatically re-seals prior work.
Existing output files and dangling links are refused. Existing cleanup and
partial-publication diagnostics still apply.

This increment is for restored-copy rehearsal only. `rebuild-archive` explicitly
rejects v2 before creating a database or receipt. Replaying source objects cannot
restore title/review decisions and must not claim to satisfy their v2 digests.
The existing v1 rebuild workflow remains unchanged. Sidecar observations and
legacy-only object-inventory improvements are not added here; existing file-copy,
WAL and source-retention cautions still apply.

A matching digest is a comparison with supplied declarations, not proof of source
authenticity, consent, rights, completeness, remote retention, safe keys or future
recoverability. V2 detects more declared ledger changes; it is not a blanket
losslessness guarantee. Store manifests and receipts privately because source
labels, hashes and supplied paths can be identifying even without message text.
