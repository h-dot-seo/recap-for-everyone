# Validation record

Current release: `0.100.15-source-byte-admission`, dated 2026-11-15.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Source byte admission (0.100.15-source-byte-admission):

Roadmap #23 reader adjustments 1/5: the eight explicit source entry points now
reject inputs larger than 2 GiB = 2147483648 bytes (inclusive at the limit).
This narrows previously unbounded regular-file acceptance; there is no override.
Existing ZIP/document budgets and byte-only APIs are unchanged. Stat preflight
and snapshot actual-length checks preserve read seams. Normalized file ingest
checks cumulative bytes in both passes on the same descriptor. Pass-two failure
rolls back the transaction but a new empty schema file can remain. Growth after
stat may still allocate beyond the limit in read_bytes; no memory/TOCTOU guarantee.

Core99 PASS (one environment skip); new source-size9 tests PASS. Tests use fake
large stat and tiny patched budgets, not a 2 GiB allocation or memory benchmark.
An initial test used the provisional MAX_SOURCE_BYTES name before implementation
was frozen and produced five AttributeErrors; corrected to final MAX_EXPORT_BYTES,
then all tests passed. Product behavior was not implicated.
Full: 1665 tests in 76.442 seconds, PASS (two environment-dependent skips).
Independent core: 45 tests PASS (one existing AF_UNIX environment skip); actual
previous/current ingest receipt/tables/FTS and normalized inspect/list-export CLI
bytes match. Python 3.10 AST passes; all 146 prior sh blocks are unchanged.
Final manifest/audit and independent tree checks follow; hosted CI is pending.
