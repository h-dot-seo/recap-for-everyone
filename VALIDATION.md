# Validation record

Current release: `0.100.19-membership-checkpoint`, dated 2026-11-15.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Explicit accepted-identity checkpoints (0.100.19-membership-checkpoint):

Roadmap #7 cutoff plus #12/#27 selected-ingest end-to-end completion. Actual
installed64 CLI A selection -> artifact checkpoint -> same-object B selection
returned CUTOFF_NOT_VERIFIED as designed. This is a v1 scope limitation, not a
violation of its fail-closed contract. Opt-in --checkpoint-version2 saves exact
identity-hash membership with the existing nine-field message digest. Default v1
and existing v1 failures remain unchanged; no checkpoint is rewritten/upgraded.

V2 checkpoint, declaration, comparison and delta have explicit v2 schema labels.
Saved identity hashes are private, not anonymization/authentication. Optional
provenance/topology/title/review ledgers remain outside message verification.
64MiB bounds serialized bytes, not Python heap. No rowid/path dependence, new DB
schema, ingestion change, network runtime, license/tag or release-index action.

Focused membership/checkpoint/delta38 PASS; membership/usage/catalog22 PASS after
adding exact budget, duplicate JSON, late stdout and artifact-metadata checks.
Two attempted usage-module names were nonexistent; corrected to the actual
listed tests.test_command_usage before the passing run (not product failures).
Independent core34 PASS, actual64/65 v1 declaration/comparison/doc/delta bytes
identical, separate identity hash/Unicode/new identity and snapshot challenge PASS.
Existing sh blocks preserved; the new guide uses tokenization before path insertion
and a real space-containing output directory. SQLite connections explicitly close.

Isolated wheel0.100.19 built offline with preinstalled flit_core3.12.0 using
--no-index/--no-deps/--no-build-isolation, installed --no-index/--no-deps outside
checkout. Actual console CLI with PYTHONPATH absent completes same-artifact A/B
v2 cutoff, source move/repeat/missing selection preservation and plan.v2 rebuild
with all DB/FTS tables identical. Local Linux installation observation is not
all-platform installation CI. No actual personal files were used.

Full1709 tests in72.730 seconds PASS (two environment-dependent skips).
Independent actual installed CLI journey also PASS in a fresh Korean/space/apostrophe
path, including explicit missing-selection exit1/no stdout/unchanged DB assertions.
Prior147 sh blocks byte-preserved, AST3.10 PASS; manifest361 valid/audit362 PASS.
Final independent metadata and hosted six-row exact-head CI are required before merge.
