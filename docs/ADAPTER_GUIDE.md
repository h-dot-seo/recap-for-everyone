# An invented adapter illustration

This runnable illustration connects one **invented** JSON shape to the
[normalized input contract](NORMALIZED_JSONL.md). It is not a parser for any real
vendor, an automatic format detector, or a completeness guarantee. Core formats,
archive schemas and import/title-plan dispatch remain unchanged.

A reuse license has not been selected. [RIGHTS.md](../RIGHTS.md) remains authoritative;
this page does not grant copying, modification or redistribution rights and does
not invite community contributions. The example illustrates behavior, not a
licensed template. No model, service, API key, paid API or network is involved.

## Explicit invented mapping

`examples/foreign-sample.json` contains `format: invented-chat-demo.v1` and `threads`.
Each thread has exactly `key`, `label`, `entries`; each entry has exactly `key`,
`speaker`, `when`, `body`. These fields map respectively to conversation ID, title,
message ID, role, timestamp and text. No IDs, roles, dates or titles are guessed.
Input thread/entry order becomes output line order; timestamps remain supplied text.
Roles are exactly user, assistant, system or tool. IDs, timestamps and bodies must
be nonempty strings; labels may be empty. Whitespace-only nonempty strings are
preserved, not silently trimmed. Empty thread lists and empty entry lists produce
no message rows; empty threads have no representation in the normalized output.

The illustration reads one explicit UTF-8 or UTF-8-BOM JSON file once. It rejects
duplicate JSON members, nonfinite numbers, unknown members, duplicate thread keys,
duplicate message keys within a thread, missing fields, unsupported roles and
invalid Unicode. Same message keys in different threads are distinct. This narrow
example is intentionally stricter than normalized ingest; it changes none of that
contract's accepted inputs. There are no attachment, branch or original-origin
fields in this invented format. Never assume an unknown field is unimportant.

## Executable walkthrough

Run from the repository root. Replace `OUTPUT` with a **new directory outside the
repository**, whose parent exists. Use your Python launcher instead of `python`.
Quote concrete paths containing spaces for your shell; the example below keeps
quoted placeholders as single arguments. `HASH` means the lowercase
`normalized_sha256` in the converter's stdout receipt. Copy it into the last two
commands after checking the receipt. There is no shell-specific JSON extraction.

```sh
mkdir "OUTPUT"
python examples/adapter_illustration.py examples/foreign-sample.json --output "OUTPUT/normalized.jsonl"
python recap.py inspect "OUTPUT/normalized.jsonl" --format normalized --expected-export-sha256 HASH
python recap.py --db "OUTPUT/archive.sqlite" ingest "OUTPUT/normalized.jsonl" --source synthetic-adapter --expected-sha256 HASH
```

The converter creates UTF-8 JSONL without a BOM and with explicit LF line endings,
so its output hash is platform-independent. All validation and byte construction
finish before opening the output exclusively. Existing files, directories and
final symlinks are not overwritten; a missing parent is not created. Parent
symlinks are not a containment boundary: choose a trusted private directory.
An I/O failure can leave a partial **new** output; inspect it manually and choose a
new destination before retrying. A failed conversion prints no successful receipt.
The script holds both files in memory and is not a streaming or resource-bounded
production adapter. It neither discovers private files nor creates a database.

Stdout is a receipt, not converted message text. It records
`recap.adapter-illustration-receipt.v1`, original `source_sha256`/`source_bytes`,
`normalized_sha256`/`normalized_bytes`, record count, `database_access: false` and
`remote_mutation: false`. Keep this receipt privately with the original and the
normalized file. Hashes and sizes may themselves be sensitive. The receipt links
observed bytes; it does not authenticate authors, validate semantics, or prove
lossless conversion. Conversion is not permission to collect, publish or ingest.

Inspection reports structure and repeated-identity counts; it is not admission.
For an existing archive, also use `check-import --format normalized --source SOURCE`
with `--expected-export-sha256 HASH` before ingest. Ingest rechecks the hash before
SQLite access and checks archive conflicts under its write lock. A changed file
requires another inspection, not bypassing the guard. Changing an adapter's ID
mapping creates different identities, not updates to previously imported messages.

## Preserve both source layers

- Keep `normalized.jsonl`: ingest records its hash and physical line. Recovery
  requires referenced artifacts without full export-occurrence coverage; empty,
  unreferenced or fully covered artifacts may be optional. See
  [recovery declarations](RECOVERY_REHEARSAL.md).
- Keep the original foreign file separately: Recap never declares it as an archive
  recovery object. Retain the conversion receipt to explain the two byte snapshots.
- `find --export-sha256` selects original-export ledger occurrences, not ingested
  normalized artifacts. This illustration does not create those ledger rows, and
  inserting extra origin fields into normalized JSONL would not create them either.

## Maintainer checklist for a future built-in format

This is a maintainer's checklist, not a contribution invitation or approval of a
second vendor adapter. A new built-in adapter remains a separate reviewed change.

1. Identify the exact source grammar from an authoritative **commit-pinned** public
   format reference and record its URL/commit and observed scope in INPUT_SCOPE.md.
   Mutable `blob/main` links are not sufficient evidence of the implemented grammar.
   Do not invent vendor field names from this synthetic illustration.
2. Define identity derivation, role/text extraction, timestamps, title behavior,
   ordering, branch policy and explicit unsupported/lossy fields. Fail closed on
   ambiguous identity or unknown structural shapes; never stringify attachments.
3. Use only synthetic fixtures. Check rights before including any third-party
   material; public visibility does not grant redistribution rights. Never bundle
   real conversations, credentials or privately derived examples.
4. Preserve one immutable byte snapshot and report original hash/byte count,
   extracted messages, conversations, role counts, skipped/unsupported content,
   warnings, limitations and `contains_message_text: false`. Do not label coverage
   as completeness or source attribution as authenticated authorship.
5. Test malformed/duplicate/Unicode input, empty files, all supported roles,
   conflicting/repeated identities, ordering, hash mismatch, unchanged archives on
   rejection, provenance and standalone CLI parity. Keep shared dispatch allowlists
   explicit so unrelated title workflows do not acquire accidental format support.
6. Execute the documented walkthrough with a fresh temporary checkout/output,
   including paths with spaces and Windows separators. Tokenize documentation
   before replacing placeholders; never run native paths through POSIX shlex.
7. Update command references, input boundaries, English/Korean indexes, SKILL,
   validation history and publication manifest. Run the full synthetic suite,
   audit and manifest verification on the exact tree, then both OS/Python CI
   matrices before publication readiness and after merge.
