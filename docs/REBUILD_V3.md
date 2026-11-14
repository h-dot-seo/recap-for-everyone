# Explicit v3 replay including original-export metadata

A supplied v3 manifest and explicit `recap.rebuild-plan.v1` can replay retained
objects into a new staging DB and compare all seven `original_exports` fields.
The DB is published exclusively only after all applicable checks pass. This is
not full archive restoration, a migration, or permission to handle private data.

## Synthetic zero-message walkthrough

Use a fresh OUTPUT directory. The empty JSON export and supplied plan are fictional.
Unlike occurrence-only declarations, v3 explicitly retains its original hash and
metadata despite extracting no messages. No private database is used here.

```sh
python recap.py --db OUTPUT/empty-reference.sqlite import examples/synthetic-empty-web-export.json --source synthetic-empty --format web
python recap.py --db OUTPUT/empty-reference.sqlite declare-recovery --manifest-version 3 --declared-at 2026-11-14 --output OUTPUT/empty-manifest-v3.json
python recap.py rebuild-archive OUTPUT/empty-manifest-v3.json --plan examples/rebuild-v3-empty-plan.json --objects examples --new-db OUTPUT/empty-rebuilt.sqlite --output OUTPUT/empty-rebuild-v3.json
```

The receipt is `recap.rebuild-receipt.v3`, records the actual manifest schema,
and reports `full_archive_restored:false` even when its status is
`REBUILD_REHEARSAL_PASSED`. Zero extracted messages is not a missing original.

## Supplied parameters, never inferred history

For v3 adapter steps, source, original hash, format and selection must match an
explicit declared origin row. Normalized steps still require a declared artifact.
The separate v3 hash set is not a license to use that hash with any source,
parser, or selection. No legacy occurrence union is inferred.

The seven-column ledger does **not** record local parsing labels, newline choice,
or original import order. The operator supplies these in the existing ordered
plan. Neither plan generation nor parsing-label reconstruction is automatic.
Wrong labels, order, newline, parser-version differences or mismatched metadata
cause ordinary failures; the tool does not infer a cause or silently reconcile
rows. Passing compares declared logical rows, not original physical insertion order.

Every declared original-export field, count and digest is checked against actual
replay. Recording byte count in a declaration does not independently authenticate
an object; the replayed import supplies the count being compared. A missing,
empty or legacy origin table is not fabricated or dropped to force success.
If replay cannot reproduce its declared state, the new DB is not published.

## Histories and failure boundaries

Title history and review decisions remain explicitly excluded from checks and
expected tables. They are never reported as PASS or as successful NOT_RUN checks.
`not_rebuildable_from_objects` names whichever of those histories were declared.
Use a retained restored DB copy with `rehearse-recovery` to verify those histories;
a full rehearsal of a rebuilt copy can still fail because they were not restored.

All other replayable ledgers, message/artifact/source digests, FTS and object hashes
remain checked. No unexpected table is removed. The live archive is never opened
by the rebuild. Existing destinations and sidecars are refused. A replay or DB
publication failure leaves no published partial DB and reports its failure receipt.
If DB publication succeeds but receipt publication fails, the DB is preserved and
the error says to inspect it before retrying. Two outputs are not atomic.

V1/v2 replay results remain compatible except actual implementation hashes and
the derived receipt hash, which correctly change with code bytes. Existing v1/v2/v3
declaration and restored-copy rehearsal bytes/checks are unchanged. Both existing and newly generated v3 manifests retain the historical
restored-copy-only scope wording for byte compatibility. That unchanged description
does not describe the current rebuild support: the actual v3 rebuild receipt and
this guide define its limited replay checks. Saved manifests are not rewritten.
No automatic resealing, stamp, fingerprint, licensing or policy wording is changed.
