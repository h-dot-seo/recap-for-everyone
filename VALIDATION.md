# Validation record

Current release: `0.100.13-package-entrypoint`, dated 2026-11-15.
Prior entries remain in [validation history](docs/VALIDATION_HISTORY.md).

## 2026-11-15 Optional installed command (0.100.13-package-entrypoint):

Roadmap #6 adjusted install path: recaplib-only wheel metadata, exact build-only
flit_core 3.12.0, numeric dynamic version, recap console script and stable -m
entry point. Root shim, seven archive re-exports, build_parser and monkeypatch
seams remain through local function bindings; no global dispatch replacement.
The earlier deliberately-root-only CLI decision is reversed here, not erased.
No runtime dependencies, license decision, package-index publication, tags or
network-enabled CI changes. Installed catalog release is null without a checkout
manifest; examples/audit/verifier remain checkout-only.

Core80 (one skip) and new7 tests pass. A temporary outside build venv fetched
flit_core==3.12.0 from official PyPI; subsequent wheel build used no-index,
no-build-isolation and no-deps, then a separate empty venv installed the wheel
without network/dependencies. Installed recap and -m version/help, describe,
synthetic ingest/find/show passed; wheel contains only recaplib and dist-info,
with no Requires-Dist. These are local Python3.12 observations, not matrix
installation coverage. Full suite: 1,645 tests /71.722s PASS (two local environment skips: decoder-gap
probe and AF_UNIX creation prohibited). New8 tests, independent15 focused and
actual prior/current6 CLI byte comparisons pass; numeric version is intentionally
updated. Independent installed -I console/module/import metadata and local
extractive adapter subprocess spawn pass, with unchanged synthetic DB bytes.
Before/after outside wheel build and install, all 350 checkout file paths/hashes
were identical (excluding normal .git/__pycache__). AST3.10/compile/diff, old144
sh blocks, manifest349/audit350 pass. Existing test monkeypatch targets were not
changed. No files, commands or package were uploaded to a package index.
