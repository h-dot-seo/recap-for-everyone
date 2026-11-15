# Streamed ZIP validation

Inspection and preparation no longer allocate the entire ZIP byte string. Each
operation opens one file object, hashes it in chunks of at most 1 MiB, validates
bounded EOCD/ZIP64 and directory records, and lets ZipFile use that same object.
Preparation still reads the selected member and validates CRC and JSON before
creating any staging file. A second complete bounded hash must match before a
successful result or output publication. An expected hash is checked before ZIP
metadata parsing. SourceChanged refuses detected changes without output; parsing
errors also close the handle without output, without claiming a final hash check.

The fixed archive 64 MiB, member 16 MiB, 1000-entry and 200:1 bounds remain. The
existing member option can only lower its bound. CLI and receipt fields do not
change. Larger legitimate archives can still be refused. No new upper-bound
policy, extraction-to-staging stream, automatic retry or DB access is introduced.

Two equal digests do NOT establish an immutable snapshot. A concurrent writer can
change bytes during processing and restore them before the final pass. This is
not protection against hostile concurrent modification or namespace races. The
file object, not a second pathname open, supplies both passes and ZIP parsing.
Use operator-controlled stable inputs. Historical validation entries describing
one immutable in-memory snapshot describe earlier releases, not this contract.

## Synthetic observation, not a performance guarantee

Python 3.12, three fresh subprocesses per version/operation, same ZIP_STORED input:
a 32 MiB synthetic attachment and a two-byte `[]` conversations.json. Total ZIP
size 33,554,692 bytes; SHA-256
`7f9ee7a9630b2ae3a9d9d37b6c0503e43457639e7eb6e454ee454e8b1b5cd9c7`.
After imports and garbage collection, tracemalloc measured Python heap allocation
peaks during the operation. Prior release 0.100.5 versus this implementation:

| Operation | Prior peak bytes (3 trials) | Current peak bytes (3 trials) |
| --- | --- | --- |
| inspect | 67,114,645 / 67,114,645 / 67,114,645 | 2,147,983 / 2,147,983 / 2,148,011 |
| prepare | 67,114,645 / 67,114,645 / 67,114,645 | 2,150,473 / 2,150,473 / 2,150,473 |

These are environment-specific observations, not total process/RSS memory,
throughput measurements or guarantees. ZipFile's central directory and the
selected member/decoded JSON still allocate memory; the fixed byte ceilings are
not total memory ceilings. Both complete digest passes still read the ZIP.
No memory/timing threshold is asserted by CI.

## Synthetic checks

```sh
python -m unittest tests.test_zip_directory_preflight -v
```

The synthetic tests include the limitation itself: changed bytes restored before
the final hash can evade this observation. Passing that test does not make the
operation safe against malicious writers. No real export or private data was used.
