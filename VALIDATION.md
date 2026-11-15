# Validation record

Current release: `0.100.18-selected-normalized`, dated 2026-11-15.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Selected normalized ingest and explicit replay (0.100.18-selected-normalized):

Roadmap #12 adjustment6/#27 selection-path completion (supplied-origin ledger
remains deferred): opt-in conversation selection
retains whole-file artifact SHA/bytes/record_count and physical source lines while
inserting only selected identities. All syntax is validated before DB access;
identity conflicts are checked after selection. Same-handle two-pass verification,
source budget, transaction rollback and possible new empty schema file remain.
Selected plus non-None Python provenance (including []) is refused. Inline origin
claims stay ignored. No new original_exports format or recovery manifest version.

Explicit plan.v2 permits normalized conversation selection; v1 retains null-only
selection and its prior behavior. v2 receipts identify plan schema and normalized
step selection. Old releases reject v2: forward incompatibility, not universal
compatibility. No default ingest fields change. Intentional metadata exceptions:
normalized inventory blocker/support/selectable counts and support warning reflect
the new capability; command catalog ingest/rebuild notes describe it. Existing
three export formats remain unchanged. V1 rebuild receipt differences are exactly
the actual archive.py/session_workflow.py/rebuild.py implementation hashes and the
resulting receipt digest. Hashes are never frozen artificially.

New15 tests including executed guide PASS; related54/66 and separate24 file/bytes
cases PASS. Independent core102 tests PASS, actual63/64 default4 CLI raw outputs,
manifest1/2/3 declare/rehearse and DB/FTS match; v1 receipt exceptions above verified.
Initial failures were stale unsupported-selection/v2 oracles and one new test's
coverage key (records, not extracted_messages), corrected without broadening
adapter import/title-plan support. Two probe commands named nonexistent test
modules; corrected to real modules before the passing runs. These were not product
failures. An existing documentation row incorrectly called rebuild-archive
'rebuild-recovery'; the exact real CLI name is corrected here. The old normalized
guide's stale list-export exclusion is also corrected; existing sh blocks stay.
First full1694 run had two failures: an older normalized-delta rejection oracle
and the immutable SKILL baseline sentence still claimed selection unsupported.
The delta case now checks actual selected counts; the baseline is retained with
one exact authorized capability-sentence replacement. An appended stale SKILL
selection/byte-admission note is corrected without weakening its privacy boundary.
Full rerun1694 tests in73.141 seconds PASS (two environment-dependent skips).
All146 prior sh blocks remain unchanged; Python3.10 AST passes. Final independent
metadata/tree review and hosted six-row CI are required before merge.
