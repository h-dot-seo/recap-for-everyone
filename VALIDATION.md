# Validation record

Current release: `0.100.12-document-admission`, dated 2026-11-15.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Saved document admission (0.100.12-document-admission):

Roadmap #23 remaining saved-document slice: regular-file and 8MiB inclusive
preflight for title documents, plan checks and unified manual transfer inputs.
One read_bytes snapshot and a post-read length check preserve the shared seam.
Title BOM acceptance and plan/transfer BOM rejection plus read_text universal
newline/error positions remain. Existing smaller budgets, approval gates and
source paths are unchanged. Growth after stat can allocate beyond the ceiling;
this is not a total memory or hostile namespace guarantee.

Ten new focused tests pass, including real boundary bytes, UTF8, growth, kinds,
symlinks, encoding and actual FIFO CLI timeouts. An initial new FIFO test used
nonexistent --plan/--target flags and failed at argparse; corrected to documented
positional arguments, without changing product code. Core focused78 pass.
Full suite: 1,637 tests /74.278s PASS (two local environment skips: decoder-gap
probe and AF_UNIX creation prohibited). Independent core38 tests pass plus real
prior/current plan CLI 3 valid and 6 negative cases with identical bytes/exit and
unchanged DB bytes. Independent size/kind/growth/BOM/newline checks pass.
Python3.10 AST/compile/diff, prior144 sh blocks, manifest344/audit345 pass.
