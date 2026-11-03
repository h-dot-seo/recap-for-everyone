# Choose a web conversation part without decompressing it

Downloaded web exports may contain one conversation JSON file or numbered parts.
Before explicitly preparing a member, inspect the candidate names inside the ZIP:

```sh
python recap.py inspect-web-zip ../private-data/export.zip --limit 50 --offset 0
```

No database is needed; a supplied `--db` is not accessed. The command does not
extract files, open member payloads, parse JSON or perform a CRC check. It reads
the bounded **whole ZIP byte snapshot**, including compressed bytes, and inspects
only the central-directory metadata. Nothing is written or transmitted.

## Candidate recognition is a heuristic

The inventory lists basenames matching these case-insensitive conventions:

- `conversations.json`
- `conversations-001.json` or `conversations_001.json`
- `conversations001.json`

Safe nested paths are allowed. The actual decoded member name and letter case are
preserved for an explicit later selection. Numbered digit strings are returned as
`numbered_part_hint`, preserving leading zeros; they are not a verified sequence.
Candidates stay in central-directory order, **not chronological or numeric order**.

This recognition is not an official comprehensive naming schema. Other names can
be legitimate or unrelated; they are counted under `other_entries_not_listed`
without displaying their names. An empty inventory is not proof that the ZIP lacks
conversation data. Use a trusted local ZIP viewer if you need to inspect a different
name, and select it explicitly for preparation. Preparation still accepts any
explicit safe `.json` member that passes the supported web-shape validation.

`parts_completeness` is always `NOT_ASSESSED`. Gaps, repeated numbers, a base file
alongside numbered parts, nested paths, or no base file do not tell this tool which
parts are required. It does not merge, automatically select or import all candidates.
The existing [official references and ZIP preparation limits](PREPARE_WEB_EXPORT.md)
remain applicable; those references do not promise a stable full JSON schema.

## Eligibility is metadata-only

Each candidate reports declared/compressed byte sizes, its archive entry index,
duplicate-name count and `metadata_eligible`. Ineligible candidates have a fixed
`reason_code` such as duplicate name, unsafe path, nonregular file, encryption,
unsupported compression or declared expansion limit. These checks reuse the
preparation rules. Duplicate candidates are shown rather than silently deduplicated
because an exact member selection would be ambiguous.

**`metadata_eligible: true` does not mean safe, valid JSON or complete content.**
Every candidate says `content_validation: NOT_PERFORMED`. A corrupt CRC, malformed
JSON or unsupported conversation structure may still fail during preparation.
Reported ZIP sizes and names are untrusted metadata, not authentication.

The whole-archive 64 MiB / 1000-entry bounds and conservative pre-entry signature
check are shared with preparation. Pagination limits the displayed candidates
(default 50, maximum 100), not ZIP reading or metadata parsing. `total_candidates`
and `other_entries_not_listed` describe the whole snapshot. `next_offset` is null at
the end. Candidate names can themselves be private; keep the JSON output private.

## Bind selection to the inspected ZIP

Copy the exact candidate `member` and the inventory's `archive_sha256`, then prepare
one part to a new private file:

```sh
python recap.py prepare-web-export ../private-data/export.zip --member conversations-001.json --output ../private-data/part-001.json --expected-archive-sha256 ARCHIVE_SHA256
```

Replace `ARCHIVE_SHA256` with the reported lowercase digest. The optional expected
hash is checked before decompression or output staging. If any ZIP bytes changed
since inspection, the command refuses; inspect and select again. This is a byte
snapshot check, not proof of who created the ZIP. Omitting the option retains the
previous explicit single-member preparation behavior.

Inspect the preparation receipt and warnings before deliberately importing the
prepared file. For each additional part, repeat with an explicit member and a
separate new output path. One preparation never overwrites another. Do not assume
that all parts form one atomic import: a later part's validation or identity conflict
can fail while earlier explicit imports remain in the archive.

The full synthetic CLI regression discovers two reverse-ordered numbered parts,
prepares them with expected ZIP hashes, imports their 12 invented web conversations,
imports 12 invented local sessions, reviews one proposal and explicitly applies an
operator title. This demonstrates a supported flow, not complete coverage of real
exports. No real conversation files are used in tests.
