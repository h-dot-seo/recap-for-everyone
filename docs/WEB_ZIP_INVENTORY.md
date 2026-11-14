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

## Keep candidate pages on one ZIP snapshot

For a small page, start with:

```sh
python recap.py inspect-web-zip ../private-data/export.zip --limit 1 --offset 0
```

Save this first response's `archive_sha256`. If `next_offset` is not null, use that
exact offset and **the first page's digest** on the next request:

```sh
python recap.py inspect-web-zip ../private-data/export.zip --limit 1 --offset NEXT_OFFSET --expected-archive-sha256 ARCHIVE_SHA256
```

Replace `NEXT_OFFSET` and `ARCHIVE_SHA256` with those returned values, not literal
placeholder text. Continue deliberately using each returned `next_offset` and the
same first-page digest until `next_offset` is null. Keep the same page size unless
you intend to change it; the offset is a candidate index, not a page number.

Without the optional hash, every call independently lists the ZIP currently at the
path. Replacement, reordering or added entries can then repeat or skip candidates
across pages even when `total_candidates` is unchanged. With the hash, a mismatch
fails before ZIP metadata parsing, including requests past the last candidate.
Invalid hash syntax fails before source-file reading. The expected hash must be
exactly 64 lowercase hexadecimal characters, as for preparation.

The digest binds **all ZIP bytes**, including unrelated entries and archive comments,
not just displayed candidates. Every page still reads the full bounded snapshot;
this is not a streaming cursor or a cached inventory. A matching digest does not
validate member contents or prove all parts exist. If the file changed, restart at
offset zero and review the new inventory; do not combine old and new pages or simply
replace the expected hash while continuing an old offset. Use the original page
digest again for the explicit preparation below. Nothing is prepared or imported by
paging, and separate preparations/imports are not one atomic operation.

## Bind selection to the inspected ZIP

Copy the exact candidate `member` and the first inventory page's `archive_sha256`,
then prepare one part to a new private file:

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

## Declared fixed resource limits

Successful v1 receipts now include `limits`: `member_bytes` (16777216),
`ratio` (200), `entries` (1000), `archive_ceiling` (67108864), and
`operator_supplied` (false). These disclose existing fixed safety bounds; there
is no override flag and no limit increase. Invalid or over-budget archives still
fail without a successful receipt. Archive bytes are still read once into the
same bounded immutable in-memory snapshot. This is not streaming support.

Inventory candidates additionally carry `exceeded_limits`, an ordered list of
`member_bytes` and/or `ratio` derived only from declared metadata. The ratio test
is `declared_bytes > max(compressed_bytes, 1) * ratio`; equality passes either
limit. `MEMBER_EXPANSION_LIMIT` remains unchanged. Higher-priority reasons such
as unsafe paths or duplicate names remain primary even when this independent
list is nonempty. An empty list is not eligibility or content validation: CRC,
JSON shape and all other safety checks still apply during explicit preparation.
No candidate is decompressed to produce these diagnostics.

The central-directory signature pre-count is unchanged and remains conservative:
signatures inside stored attachments can count toward the entry bound. This
increment neither fixes that false rejection nor introduces EOCD/ZIP64 parsing,
new compression formats, chunked archive handling or operator-controlled bounds.
