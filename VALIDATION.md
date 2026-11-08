# Validation record

Current release: `0.88.1-documentation-restructure`, dated 2026-11-08 (Asia/Seoul).
This file is the current snapshot. Every dated entry since the first release is kept
unchanged and in order in [docs/VALIDATION_HISTORY.md](docs/VALIDATION_HISTORY.md).

## Latest change

2026-11-08 Documentation restructure (0.88.1-documentation-restructure): README reduced
to one screen with a command table and documentation index; `docs/COMMANDS.md`,
`docs/WORKFLOWS.md` and `docs/README.ko.md` added; this record split into snapshot and
history; no code, fixture or executed sh block changed. Full entry:
[validation history](docs/VALIDATION_HISTORY.md#2026-11-08-documentation-restructure-0881-documentation-restructure).

## What CI runs

`.github/workflows/tests.yml` runs on every push to `main` and on pull requests, on
`ubuntu-latest` and `windows-latest` with Python 3.10 and 3.12 (four jobs, `fail-fast:
false`, ten-minute timeout each), in this order: `python -m unittest discover -v`,
`python audit_publication.py`, `python verify_manifest.py`. Actions are commit-pinned,
token permissions are read-only, checkout does not persist credentials, and no secrets
or deployment steps are used. Remote results are the public GitHub Actions history;
this file does not restate or certify them.

## How to verify locally

From the repository root, with your chosen launcher in place of `python`
([installation and runtime checks](docs/INSTALL.md)):

1. `python -m unittest discover -v` runs the synthetic standard-library suite. On
   restricted Windows hosts set `TMP` and `TEMP` to a writable scratch directory. The
   tests use temporary synthetic data and never read your conversations. Documented
   sh blocks (for example in `docs/START_HERE.md`, `docs/INSTALL.md` and
   `docs/RECOVERY_REHEARSAL.md`) are executed exactly as written.
2. `python verify_manifest.py` must print `{"valid": true, "errors": []}`. It also
   rejects files outside the manifest, so run it on a clean checkout without private
   working files.
3. `python audit_publication.py` must report `"pass": true` for the limited prohibited
   file-type and secret-pattern scan.
4. `python -m compileall -q .` must be silent.

## What this record does not claim

- No real conversation export, archive, account, title history or backup system was
  used in any entry; every fixture is synthetic and says so.
- Passing tests, audit and manifest checks show only that the generic code and the
  synthetic fixtures behave as documented on the tested interpreters. They are not
  proof of anonymity, copyright or legal clearance, semantic title quality, model
  behavior, remote renaming or remote recovery.
- A local pass does not establish that a push, a remote CI run or a remote backup
  succeeded. Exact-commit CI results are checked in the GitHub Actions history after
  publication, and recovery is never marked verified from a Git ref or push message.
- The supported runtimes are the CI interpreters. Observations under other interpreters
  are recorded in the history as observations, not as support.
