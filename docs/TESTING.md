# Observing synthetic test durations

The release gate remains `python -m unittest discover -v`. The optional
`python -m tests.timing` command observes all published `tests.test_*` modules.
It does not migrate tests, patch subprocess calls or change their assertions.
To observe a small explicitly selected module:

```sh
python -m tests.timing tests.test_cli_harness
```

Additional distinct, exact published module names may follow. File paths, arbitrary
imports and individual test selectors are rejected. With no selectors, every
published test module runs; this can take a long time. Modules run sequentially in
one fresh worker process, not one subprocess per module. Each module is loaded
and run through standard unittest with its usual fixtures. The observer does not
promise identical timing to discovery, a hard timeout or bounded memory.

Stdout contains one strict `recap.test-timing.v1` JSON object. No result file is
created. Existing tests retain their normal temporary-file behavior. Module rows
report module, tests, seconds, failures, errors, skipped, expected_failures and
unexpected_successes; total aggregates counts and records elapsed worker time.
Module seconds include imports and fixtures. Interpreter information is restricted
to major.minor; no machine, platform, path or SQLite-build metadata is reported.

Failure, error or unexpected success sets success=false and exit 1. Expected
failures and skips remain visible, not relabeled as passed tests. An incomplete
worker or invalid selection returns a fixed error object and exit 1, not invented
partial timings. Diagnostics and incidental test output are withheld: Python
streams are redirected in the worker and its process output is captured by the
parent. Use the ordinary unittest command separately when diagnosing failures.

These are local observations, not benchmark guarantees, performance claims or a
promise that every CI job fits its budget. Do not commit receipt output. Keep only
appropriate prose totals in validation records. No network operation, product
schema, publication or default CI command is added by this observer.
