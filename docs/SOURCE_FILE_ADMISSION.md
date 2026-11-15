# Source file admission

Explicit source reads now stat the supplied path and require a regular file before
opening it. This prevents an ordinary FIFO from waiting for a writer and rejects
directories, devices (including Windows NUL) and filesystem sockets. Regular-file
symlinks remain supported: stat follows the link, but parsing labels and reading
continue to use the original supplied path, not a rewritten resolved filename.
Missing paths retain FileNotFoundError or each entry point's existing translation.

## Exact scope

| Entry point | Coverage | Nonregular error |
| --- | --- | --- |
| archive.ingest | Normalized file, including explicit provenance fallback | Fixed ValueError |
| session_workflow._read_export_bytes | Export inspection, normalization, import and callers using this shared reader | Fixed ValueError |
| replay_local.reconstruct | Local retained-turn projection from a path | Existing SOURCE_ERROR result |
| web_branch.branch_view | Explicit source web branch | Fixed ValueError |
| title_plan.make_plan | Original source export, not a plan document | Fixed ValueError |
| attributed_title.attributed_evidence | Original attributed local source | Fixed ValueError |
| replay_title.replay_evidence | Original local source | Fixed ValueError |
| local_parser.parse_artifact | JSONL path only | Fixed LocalImportError |

The shared diagnostic is `source must be an existing regular file`, with no source
path or content. Each module keeps earlier option validation ordering and its
existing CLI/result error handling. Direct byte APIs, plan/approval/title document
readers and SQLite-artifact handling are not changed by this increment. Existing
bounded ZIP/document readers and recovery's stricter symlink rejection are not
weakened or replaced.

Regular inputs retain the same output shapes, hashes, source-line identity, FTS
and DB transaction behavior. Snapshot readers retain their Path.read_bytes seam;
normalized file ingest retains its one-handle two-pass verification. No successful
receipt is emitted for rejected nonregular input, and source-first rejection does
not open or create a database.

## Source size admission

The eight entry points above now share a 2 GiB inclusive source limit:
`2 * 1024**3 = 2147483648` bytes. Exactly that count is admitted; one byte
more is refused. This intentionally narrows previously unbounded regular-source
acceptance, following roadmap #23 and its reader adjustment 5. There is no new
override option. ZIP preparation retains its smaller 64 MiB archive/16 MiB member
limits, and title/plan/transfer documents retain 8 MiB or their smaller existing
budgets. These inputs have different parsing and operational scopes.

Stat checks the size before opening. Snapshot paths retain one Path.read_bytes
call and then check the actual byte length. Normalized file ingest retains one
open descriptor and checks accumulated raw bytes in each hashing pass. The
provenance file-API fallback checks its snapshot, while direct ingest_bytes and
adapter byte APIs keep their existing contracts. The diagnostic is a fixed,
path-free size refusal, translated by each module as before.

An oversized preflight never opens the input or database. Growth beyond the limit
in pass one is rejected before SQLite opens; pass-two refusal rolls back the
existing write transaction. As before, a newly created empty schema file can
remain after a pass-two failure. Do not infer that every failure leaves no file.

## Limits

Stat and open are separate operations. A hostile process can replace a path in
between; this is NOT an atomic lease, inode binding, sandbox or comprehensive
TOCTOU defense. The source byte refusal limit is not a parsing-memory ceiling. A file that grows
after stat can be fully allocated by Path.read_bytes before its actual-length
check rejects it. JSON decoding, rows and SQLite can consume additional memory.
No 2 GiB allocation or full-process memory benchmark is claimed. Large admitted
regular source files may still consume substantial memory. It grants no collection, transmission or write authorization.

Before this change, synthetic FIFO `ingest` and web `inspect` subprocesses did not
finish within a one-second test timeout. Tests now require these same operations
to return a clean rejection within a bounded subprocess timeout. POSIX FIFO and
filesystem-socket tests are skipped where unavailable; deterministic socket-type
metadata checks still run. No private source or existing user DB was used.

## Synthetic regular-file example

Create an empty OUTPUT directory outside the checkout and replace the placeholder:

```sh
python recap.py inspect examples/web-export.json --format web
python recap.py --db OUTPUT/regular.sqlite ingest examples/conversations.jsonl --source synthetic
```
