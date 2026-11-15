# Validation record

Current release: `0.100.11-normalized-inventory`, dated 2026-11-15.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Normalized conversation inventory (0.100.11-normalized-inventory):

Roadmap #12 adjustment 7/#27: normalized list-export now reuses whole-file
validate_normalized for DB-free conversation IDs, ordered distinct effective
titles, occurrence counts, filters and pagination. Repeated identity conflicts
stay in coverage, not silently merged or rejected. Selection is always false /
NOT_SUPPORTED; normalized selected ingest, import and title plans stay closed.
Existing three-format output bytes and shared read/expected-hash seams remain.
No origin admission, ledger mutation, body output or new byte budget is added.

New 9 tests and existing core83 passed. Independent 29 tests and actual prior/
current 12 CLI comparisons across web/local/local-codex passed byte-identically.
The first full run (1,627 tests /74.648s) found two old normalized-inspection
oracles that still required list-export to reject normalized input. Only those
inventory exclusions were removed; shared normalize/import/title-plan and
selected-inspection rejection assertions remain. New inventory tests assert the
separate supported read-only behavior and the NOT_SUPPORTED selection boundary.
Final full suite: 1,627 tests /74.339s PASS (two local environment skips:
decoder-gap probe and AF_UNIX creation prohibited). Focused31, Python3.10
grammar/compile, old143 sh blocks, manifest343/audit344 pass.
