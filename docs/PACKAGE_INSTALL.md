# Optional local command installation

The checkout commands and walkthroughs remain supported. Alternatively, install
only `recaplib` and one `recap` console command in an isolated environment outside
the checkout. The root scripts, examples, tests, publication manifest, audit and
verification tools are not installed. Walkthroughs still need the checkout.

From an outside working directory, an operator may use
`pipx install git+https://github.com/h-dot-seo/recap-for-everyone.git@main`.
For a downloaded checkout, create a virtual environment outside it and run that
environment's `python -m pip install /absolute/path/to/checkout`.
The no-Git archive download remains available at
[main source archive](https://github.com/h-dot-seo/recap-for-everyone/archive/refs/heads/main.zip).
Use an isolated environment, not a system Python or an in-checkout editable build.
An existing `recap` name on PATH may belong to another tool; do not overwrite it
without checking. pipx may refuse such a conflict.

Installation downloads a build-only backend, exactly `flit_core==3.12.0`, from
PyPI unless it is already supplied. The installed application has no runtime
package dependencies. Metadata uses the numeric `recaplib.__version__` directly,
so the package and CLI version stay aligned without a second version constant.
Python 3.10 remains the minimum. These choices follow the versioned
[Flit metadata documentation](https://flit.pypa.io/en/3.12.0/pyproject_toml.html)
and the [published backend](https://pypi.org/project/flit-core/3.12.0/), checked
2026-11-15. No backend download step was added to CI.

```sh
recap --version
recap describe ingest
```

`python -m recaplib` is an equivalent package entry point and can be used from
another working directory. The offline guide tests substitute that invocation
for `recap` with an explicit package path; they do not prove a console command
exists on the operator's PATH. Separate isolated wheel build/install observations
are recorded in validation history, not claimed as every-platform install CI.
Standalone package modules retain `python -m recaplib.<module>` entry points.

The installed command catalog normally reports `release: null` because the
checkout publication manifest is absent. Numeric `--version` is a label, not an
installed-file integrity check. `verify_manifest.py` and `audit_publication.py`
remain checkout-only; never run them over site-packages as if that were a release
checkout. Developer benchmark/fixture modules also require a checkout.

No license was selected, package index publication performed, or release tag
created. `Private :: Do Not Upload` is an accidental-publication guard, not a
license. Installing locally does not grant redistribution rights; see
[RIGHTS](../RIGHTS.md). This implementation reverses the earlier deliberate choice
to keep the unified CLI at the root while preserving that root compatibility
entry point. Importing implementation modules is not a stable library API
promise; the installed supported entry point is the `recap` command.
