# Validation record

Current release: `0.100.14-checkpoint-delta`, dated 2026-11-15.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Private cutoff delta files (0.100.14-checkpoint-delta):

Roadmap #7 adjustment3/6 follow-up: opt-in changed-since delta-output lists bounded
private conversation IDs from the same verified snapshot. Limit20 default/1..1000
per category, full counts and omitted counts distinct, max8MiB ASCII JSON plus LF.
Default stdout unchanged, unverified cutoff never publishes, connection closes
before exclusive creation. No automatic review, checkpoint advance or archive
mutation. File may remain when subsequent stdout delivery fails; inspect before
retrying. Existing import delta and checkpoint formats remain unchanged.

Core43, new11 delta tests, and combined usage/effects/release26 tests pass.
Independent core23 tests and actual prior/current default JSON/text CLI parity
for verified/unverified cutoffs pass. A post-close database mutation probe
confirms the published IDs remain from the verified snapshot.
Initial focused checks found one stale usage ordering and one missing conditional
write test case; both test/document contracts were corrected, then all26 passed.
First full run: 1656 tests, one failure (missing changed-since conditional-write
row in SKILL.md), two skips. Added the precise opt-in write row; product unchanged.
Full rerun: 1656 tests in 72.215 seconds, PASS (two environment-dependent
skips). Python 3.10 AST compatibility and all 145 prior sh blocks preserved.
Manifest and audit are checked on the final tree; hosted six-row CI is pending.
