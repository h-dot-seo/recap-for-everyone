# Validation record

Current release: `0.100.10-provenance-admission`, dated 2026-11-15.
This file is the current snapshot. Prior entries remain in
[docs/VALIDATION_HISTORY.md](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Explicit provenance admission (0.100.10-provenance-admission):

Roadmap #12 reader adjustment 11: validate the existing explicit Python
provenance argument before opening SQLite, preventing malformed origin hashes
from entering ledgers and breaking later recovery declaration. Required identity
membership, lowercase SHA-256, nonempty locator, optional text/null parent and
UTF-8 storage checks; iterable order/duplicates/extra-key ignoring, partial
coverage and None versus empty-ledger behavior remain. No automatic origin-field
admission, authentication claim, new schema, or recovery meaning.

Eleven focused synthetic tests pass, including invalid-input no-connect/new-DB
absence/existing-DB bytes unchanged and the file snapshot fallback. Core focused
109 pass. Independent core: 70 tests pass, including actual 55/56 web/local/
local-codex CLI and normalized bytes/file-provenance snapshot receipts and all
DB/FTS tables equal. A reusable mutable-mapping generator preserves each yielded
value snapshot. Full suite: 1,618 tests in 74.630s, PASS (2 local environment skips: decoder-gap
probe and AF_UNIX creation prohibited). Python 3.10 AST/compile/diff, all 143
prior sh blocks, manifest341/audit342 passed. Final independent tree check follows.

Baseline reproduction on release 55: a single synthetic message committed with
original_hash=not-a-hash; declare_recovery then raised ValueError because the
occurrence hash was not lowercase SHA-256. No real archive was used.

Initial full run: 1,618 tests in 73.945s, one release-identity failure because
the numeric constant remained 0.100.9 while the manifest was 0.100.10. Corrected
the constant and two version documentation lines; no product logic change.

The next focused check also caught the stale current-release header and history
heading format; both metadata declarations were aligned before final validation.
