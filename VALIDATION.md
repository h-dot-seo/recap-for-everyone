# Validation record

Current release: `0.100.17-rebuild-plan-shape`, dated 2026-11-15.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Rebuild plan documentation shape (0.100.17-rebuild-plan-shape):

Roadmap #25 narrowed to the already-labelled, operator-authored rebuild-plan.v1.
One documentation JSON Schema describes existing required fields, types, enums,
nullable text, hash spelling and max10000 steps; empty steps remain allowed.
Runtime/CLI/default outputs and consumer validation are unchanged. No generic
schema validator, external reference retrieval, approval label or CI dependency
was added. The existing consumer remains authoritative: source identity, Unicode,
file bytes, local/normalized cross-fields, declared objects and replay are stronger.

New8 plus existing rebuild tests:60 PASS. Local already-installed standard
jsonschema4.26.0 Draft202012Validator checked the metaschema, six valid plans,
19 structural negatives and five intentionally schema-admitted but consumer-refused
cases with socket creation blocked. The standalone cross-check script and result
are retained outside the public checkout; this is not a new CI support claim.
An initial focused command named a nonexistent test_rebuild module; corrected to
the actual modules before the passing60 run. No product defect was implicated.
Full1679 tests in71.864 seconds PASS (two environment-dependent skips).
Independent core8 tests and78 standard-validator checks pass with socket creation
blocked. Product57 module bytes are unchanged except release-version metadata.
All146 prior sh blocks preserved and Python3.10 AST passes. Final manifest/audit
and independent tree are checked before ready/merge; hosted six-row CI pending.
