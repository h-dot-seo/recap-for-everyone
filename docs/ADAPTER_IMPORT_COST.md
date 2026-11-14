# Adapter import cost and boundaries

Web, local and local-codex imports parse one immutable source snapshot. The
adapter produces message rows and retains original export hashes and locators.
Those rows still become the same normalized JSONL bytes for artifact hash and byte
count, including native newline translation for path import and explicit LF/CRLF
for byte replay. The importer now validates the existing rows and incoming identity
conflicts without strict-decoding that generated JSONL again. Direct normalized
JSONL ingest still strict-parses its supplied bytes.

This is an internal cost reduction, not a new format, command or approval.
No table, provenance meaning, receipt or recovery authorization is added.
It does not establish authorship, consent, completeness or publication rights.
No model or network is called. Original files are not changed.

## Synthetic example

All shipped messages below are fictional. Replace OUTPUT with a new private
scratch directory outside this checkout. Import explicitly writes the selected DB;
the second import should insert no duplicate messages.

```sh
python recap.py --db OUTPUT/adapter.sqlite import examples/web-export.json --source demo --format web
python recap.py --db OUTPUT/adapter.sqlite import examples/web-export.json --source demo --format web
python recap.py --db OUTPUT/adapter.sqlite stats
```

The source snapshot, parsed rows and derived bytes remain in memory. There is no
constant-memory, streaming or timing guarantee. SQLite may use its own journal or
temporary storage. Input-only structural and repeated-identity conflicts are
checked before SQLite opens. Archive comparisons stay under the write lock and
share the existing data transaction. Schema initialization remains earlier and
separate, so not every possible failure promises an absent or byte-identical DB.

The synthetic regressions compare receipts, complete logical tables, FTS results,
source lines and hashes against the serialized-byte ingestion path. They also
check that adapter imports do not invoke the normalized JSON decoder. These are
behavior and work-count checks, not a published timing benchmark.
