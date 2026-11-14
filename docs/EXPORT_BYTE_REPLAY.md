# Replay export bytes with explicit parsing parameters

`recaplib.session_workflow.import_export_bytes` is a Python API for replaying one
immutable export snapshot. It is a prerequisite for a future rebuild orchestrator,
not an automatic recovery command or an exclusive new-database wrapper.

The existing path-based `import` CLI is unchanged: it uses the input basename and
native platform newline serialization. The byte API takes the original parsing
`label` independently of where retained bytes are stored and requires `newline`
to be exactly `lf` or `crlf`. This allows a known serialization choice to be
reproduced on another supported platform without claiming which choice is correct.

## Synthetic example

Use an existing empty OUTPUT directory outside this repository. Run this ordinary
reference import from the repository root:

```sh
python recap.py --db OUTPUT/reference.sqlite import examples/web-export.json --source demo --format web
```

The following Python example is also executable from the repository root. Replace
OUTPUT with that same directory before running it. The explicit native newline
choice below is for comparing against the CLI import on **this** platform; a
real replay plan must supply the newline used for the original import, not guess
from the platform doing the replay.

```python
import os
from pathlib import Path
from recaplib.session_workflow import import_export_bytes

raw = Path('examples/web-export.json').read_bytes()
receipt = import_export_bytes(
    Path('OUTPUT/replayed.sqlite'), 'demo', raw, None, 'web',
    newline='crlf' if os.linesep == '\r\n' else 'lf',
)
assert receipt['inserted'] == 2
assert receipt['replay']['recovery_verified'] == 'NOT_ESTABLISHED'
```

Both imports use only fictional synthetic messages. The API does not read any
input path or create an intermediate plaintext file. It returns the ordinary
import counts and coverage plus `replay` metadata for newline, whether a label
was supplied, and the recovery boundary. Existing coverage may contain an
explicit selected conversation ID; keep receipts and labels private.

## Contract

- `raw` must be immutable `bytes`; `kind` is `web`, `local` or `local-codex`.
  Normalized JSONL continues to use `archive.ingest_bytes`, with its bytes intact.
- Local formats require a nonempty Unicode label. Use the original parsing label,
  including any parser-significant relative components, not a renamed object's
  storage name. Fallback message IDs depend on the label; some labels affect
  parser dispatch. Web permits `None` because its parser does not use the label.
- Optional `conversation` uses the same selection validation, single-record web
  requirement, branch retention and full-input coverage as file import.
- Explicit LF/CRLF changes derived normalized artifact hashes and hence message
  digests; original-export hash, locator and parent provenance still come from
  the supplied immutable original bytes. A wrong choice produces ordinary
  mismatches, not a diagnosed platform-cause code. Input order remains significant.
- Invalid arguments, malformed input and missing/ambiguous selection fail before
  ingest opens the archive. Actual ingestion uses the existing transaction,
  conflict/deduplication and provenance semantics. It can write to an existing DB.
- This API does not authorize an object against a recovery manifest, validate a
  replay plan, create DB paths exclusively, clean a multi-step partial rebuild,
  restore title/review history, authenticate content or verify a backup. The
  caller owns those orchestration responsibilities. No new resource limit or
  bounded-memory guarantee is introduced.

See [the normalized-object rehearsal](REBUILD_REHEARSAL.md) for the existing
operator-run fresh-DB check and its limits. Do not label a byte import a successful
recovery without comparing the appropriate manifest checks and unrebuilt ledgers.
