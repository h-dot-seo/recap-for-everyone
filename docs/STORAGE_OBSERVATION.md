# Observe SQLite storage before opening it

Use `describe-schema --observe-storage` when you need to see which SQLite sidecars
were already present before the metadata reader opens the archive. This is an
observation, not a backup, consistency test, safe-copy approval or recovery verdict.
The ordinary `describe-schema` output stays unchanged. `describe` still describes
commands and does not open an archive.

```sh
python recap.py --db OUTPUT/synthetic-storage.sqlite ingest examples/conversations.jsonl --source synthetic
python recap.py --db OUTPUT/synthetic-storage.sqlite describe-schema --observe-storage
```

## Separate observations

The opt-in schema is `recap.archive-storage-observation.v1`:

- `pre_open.main` records the file kind and byte count, plus at most 100 header
  bytes interpreted as fixed numeric observations. Raw header bytes are not shown.
- `header.sqlite_signature` is true only for a 100-byte header with the SQLite
  signature. Read/write version bytes and `user_version` are then reported as
  stored. Header versions 2 indicate the WAL format; this is not a guarantee
  about pending commits, completeness or the safety of copying the main file.
- `pre_open.sidecars` has only the fixed keys `wal`, `shm`, `journal`, each with
  kind and size (or null when absent/unavailable). The observer does not read
  their contents or follow symlink targets.
- Only after all these observations does the existing read-only metadata
  inventory open SQLite. Its result is nested under `inventory`; this is a later
  observation, not an atomic snapshot of the pre-open filesystem state.

A read-only SQLite open can create or change WAL/SHM files. Consequently,
`main_file_write_requested:false` does not mean every file is unchanged. A main
file alone can omit committed WAL content, and a journal's mere presence does not
prove that recovery is needed. The fixed fields `snapshot_consistency`,
`copy_safety`, and `backup_completeness` stay `NOT_ESTABLISHED`. No checkpoint,
repair, pragma stamp, migration, or automatic copy is performed.

## Failures retain observations

`OBSERVED` means the observations and inventory were obtained, not that the archive
is valid. Failure JSON is still emitted to stdout with exit 1:

- `OBSERVATION_ERROR`: preflight stat/header read failed, or a nonregular main or
  sidecar was refused. Main symlinks, directories, FIFOs and devices are not read.
  Nonregular sidecars prevent SQLite opening as well.
- `OPEN_ERROR`: the read-only connection could not be obtained.
- `INVENTORY_ERROR`: a connection was obtained but the inventory could not be
  completed, for example a hot rollback journal requires writes or required
  archive tables are absent. Open success is not reported as open failure.

`error` contains a fixed reason and exception type, never the operating-system
exception message. The pre-open observations remain visible even when later
SQLite access fails. Connections and bounded header reads are closed. These
checks do not protect against hostile concurrent path replacement or provide a
whole-process memory or SQLite query-work bound.

## Privacy

The added observations emit no paths, raw header, SQL or sidecar contents.
The nested existing inventory echoes schema object names and column names/types,
which may themselves contain private text. File sizes and header values are also
metadata, not permission to share it externally. The examples and tests use only
synthetic databases, including WAL and intentionally interrupted transactions.
