# Validation record

Current release: `0.100.16-find-excerpt-budget`, dated 2026-11-15.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Off-page search excerpts (0.100.16-find-excerpt-budget):

Roadmap #24 measured-cost follow-up: skip only excerpt construction for a
conversation that cannot enter the current rank/cursor page. Full term matching,
counts, order digest, sample masks and every SQL/provenance query remain unchanged.
The early prototype skipped more sampling and queries; it was narrowed before
publication to retain errors from hidden corrupted provenance queries.

Implementation review compared 4745 results exactly across 12 synthetic seeds,
rank/cursor/AND/Unicode/role/limit combinations, with no mismatch. Existing search76
and new targeted6 tests pass. An initial new test supplied provenance fixture keys
using storage column names; corrected to the public origin_* API fields and
reran successfully. The first performance probe used an empty required timestamp;
corrected its synthetic fixture before measuring. Neither was a product failure.
Independent core82 tests PASS; actual prior/current API364 results and two CLI
raw outputs match exactly. Actual narrowed code remeasurement (three untraced
runs plus separate traced memory) is in SCALING.md: 1000 ->20 excerpt calls;
ASCII ratio1.17, non-ASCII9.63, canonical25.93, heap almost unchanged. These are
synthetic late-hit observations, not general speed or memory guarantees.
Full:1671 tests in75.980 seconds PASS (two environment-dependent skips).
All146 prior sh blocks preserved; Python3.10 AST compatibility passes.
Final manifest/audit and independent tree are verified before ready/merge;
hosted six-row CI is pending.
