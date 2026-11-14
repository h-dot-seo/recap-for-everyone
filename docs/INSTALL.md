# Get the code and check your runtime

Recap runs directly from this source checkout. These instructions do not require
`pip install`, a model, an account or an API key. Downloading Python or the code
initially needs network access; the local import/search/title workflow does not.

## 1. Obtain the code these guides describe

The implemented web/local/title workflow is on the default `main` branch of
[h-dot-seo/recap-for-everyone](https://github.com/h-dot-seo/recap-for-everyone)
since the workflow branch was merged on 2026-11-08. A `main` checkout downloaded
before that date is a smaller extraction without these commands; clone or
download again rather than assuming an old copy matches this guide.

With Git already installed, choose a **new** destination directory:

```sh
git clone --branch main --single-branch https://github.com/h-dot-seo/recap-for-everyone.git recap-for-everyone-workflows
cd recap-for-everyone-workflows
```

Without Git, open the repository page, download the `main` source ZIP and
extract it locally. Open a terminal in the extracted directory containing
`recap.py`, `runtime_check.py` and `PUBLICATION_MANIFEST.json`. Folder names can
differ; do not guess the extracted path. This code ZIP is **not** your conversation
export ZIP. It contains synthetic examples, not your account history.

Do not replace an existing checkout or private data directory to follow this
example. If you already have another checkout, a separate new checkout avoids
changing its files. `main` can advance; its manifest identifies the downloaded
file set, not a permanently pinned release or an authenticity signature.

## 2. Choose one working Python launcher

Use a currently supported Python distribution from [Python.org](https://www.python.org/downloads/)
or your trusted operating-system distributor. The code's compatibility minimum is
Python **3.10**, not a recommendation to install an old, unsupported release.
The configured CI matrix is Python **3.10, 3.12 and 3.15** on Ubuntu and Windows
(six jobs). Configuration alone does not establish a passing runtime result; see the
[validation record](../VALIDATION.md) for observed runs. The compatibility floor remains
3.10; changing it requires an explicit recorded decision. In particular,
passing the small check below is not full testing of every newer version or OS.

The command name depends on your installation. Try the version command for an
installed launcher: `python --version`, `python3 --version`, or on Windows with
the launcher available, `py -3 --version`. Choose one that runs the intended
supported Python 3 interpreter. A missing command or a store/setup prompt does
not mean Recap failed. Follow the official [Windows](https://docs.python.org/3/using/windows.html)
or [Unix](https://docs.python.org/3/using/unix.html) setup guidance when needed.

**Every leading `python` in this repository's guides means that chosen launcher.**
For example, if only `python3` works, use `python3 runtime_check.py` and
`python3 recap.py ...` throughout. If using `py -3`, use
`py -3 runtime_check.py` and `py -3 recap.py ...`. Keep the script paths and remaining
arguments unchanged. Recheck after switching environments or reopening a terminal;
different launchers can select different Python/SQLite builds. An optional virtual
environment is not required for dependencies; keep any environment outside the
checkout if using the strict publication-manifest check below.

## 3. Check before opening an export or creating an archive

From the checkout root, with your chosen launcher substituted if needed:

```sh
python runtime_check.py
python recap.py --help
python verify_manifest.py
```

Run one command at a time and stop on a nonzero exit status. The runtime check
should report `status: "READY"`, `python.supported: true` and
`sqlite.fts5_probe: "PASS"`. It imports this interpreter's SQLite module, creates
one **in-memory** FTS5 table, inserts invented text, performs a search and closes
the connection. It does not open your archive, read exports, contact a service,
load an external extension, install software or change settings. SQLite's
[FTS5 documentation](https://www.sqlite.org/fts5.html) describes the search extension;
having a separate `sqlite3` command installed does not establish what Python uses.

The checker exits zero for `READY`, one for an unsupported/failed runtime, and two
for invalid command arguments. Failure reason codes are fixed and do not include
machine paths or underlying error text:

- `PYTHON_TOO_OLD`: select a suitable Python version; the SQLite probe was not run.
- `SQLITE_IMPORT_UNAVAILABLE`: this interpreter could not import SQLite. Use a
  trusted Python installation with its SQLite support available.
- `SQLITE_FTS5_PROBE_FAILED`: the memory probe failed. Missing FTS5 is one possible
  cause, not a proven diagnosis. Check that Python installation's SQLite support
  before importing; do not use a real archive as the test target.
- `FTS5_UNEXPECTED_RESULT`: the basic synthetic search did not return its expected
  text. Stop and investigate the runtime rather than assuming search is correct.

`READY` checks only the interpreter and this small memory operation. It does not
check source compatibility, memory capacity, shell output encoding, filesystem
permissions, ZIP hard-link support, the selected branch or the complete workflow.
The help output should include `inspect`, `import`, `review-titles` and
`preview-title`. Missing commands suggest the wrong checkout or script, not a
reason to install a similarly named package.

`verify_manifest.py` should report `valid: true`. It verifies local bytes and the
declared file inventory, not repository trust or provenance. Extra private files,
logs or environments inside the checkout can make it fail; do not delete valuable
files merely to satisfy it. Keep original data elsewhere. To run the broader
synthetic regression suite when you want to check this interpreter further:

```sh
python -m unittest discover -v
```

These tests use temporary synthetic data; they do not inspect your conversations.
The documented walkthrough tests verify program arguments and workflow results
using the test runner's interpreter. They do **not** prove that a literal `python`
command exists on your PATH, or exercise every shell's quoting/redirection behavior.

## 4. Continue with a private working directory

Follow [Start here](START_HERE.md) for the complete synthetic web/local journey,
or [the two-format title walkthrough](TITLE_WALKTHROUGH.md) for scoped proposals.
Keep the database, actual exports, proposals and previews in an operator-controlled
directory outside the repository and shared folders. Quote paths containing spaces
and substitute the same database/source identity consistently.

The primary guides now use [native `--output` title JSON saving](TITLE_DOCUMENT_FILES.md):
UTF-8 files are created without shell redirection, and existing paths are refused.
This requires hard-link support in the output filesystem; the runtime check does
not test it. Open the saved document, not just its receipt, before explicit apply.

Older examples or unsupported commands that save JSON with `>` still require UTF-8
redirection, such as a POSIX shell or PowerShell 7. Windows PowerShell 5's default
UTF-16 output is incompatible with those saved documents. The runtime check does
not detect or change this. Redirection can overwrite a file before the command
runs; do not combine it with native saving to the same input/output path.

An existing web export uses `--format web`; supported typed local sessions use
`--format local-codex`. Inspect format coverage before import. This tool neither
downloads your account history nor discovers installed session files. Titles are
local display overrides, and default suggestions are excerpts rather than semantic
summaries. [Choose a useful exact user message](TITLE_REVIEW_HINTS.md#choose-a-more-informative-user-message)
or supply reviewed wording when the first excerpt is too generic.

## Report the CLI version

Run `python recap.py --version` with your chosen launcher to print
`recap-for-everyone 0.99.6`. This reads the bundled numeric identity, not an archive
or the publication manifest; a missing manifest does not prevent this command.
A version number is not proof of file integrity, authenticity or API stability.
Keep using the manifest verification and validation record for their stated scope.
