# Prepare one web-export JSON from a downloaded ZIP

OpenAI's official [data export guide](https://help.openai.com/en/articles/7260999-exporting-your-chatgpt-history-and-data)
explains that a downloaded export is a ZIP containing chat history and other
account data. Its [conversation transfer guide](https://help.openai.com/en/articles/9106926-transfer-exported-conversations-between-chatgpt-accounts)
identifies `conversations.json` or, for larger exports, numbered conversation JSON
files. These sources were checked on 2026-11-03. They do not establish a stable
complete JSON schema. Recap's supported mapping/text subset remains limited.

This increment closes the local ZIP-to-JSON preparation step. It does **not**
request/download an export, sign in, upload a file, restore a sidebar, merge
accounts or connect to a service. A local Codex JSONL session still uses the
existing direct `local`/`local-codex` import path, not this web ZIP adapter.

## Explicit input, member and new destination

Use an export you are authorized to read and a private existing directory outside
the repository. Choose the exact member name using the [metadata-only candidate inventory](WEB_ZIP_INVENTORY.md)
or your normal ZIP viewer. Preparation does not guess or auto-select a part.
The inventory shows only conventional conversation-file candidates, not unrelated
account-metadata filenames. For example:

```sh
python recap.py prepare-web-export ../private-data/export.zip --member conversations.json --output ../private-data/prepared-conversations.json
python recap.py inspect ../private-data/prepared-conversations.json --format web
python recap.py --db ../private-data/archive.sqlite import ../private-data/prepared-conversations.json --format web --source web-demo
```

For a numbered part, pass its exact name, such as `--member conversations-001.json`.
A safe nested member name is accepted; it is copied to the **explicit output file**,
not to an automatically created directory tree. No other member is extracted.
Optionally add `--expected-archive-sha256` from the inventory receipt to reject
changed ZIP bytes before decompression/output. The source ZIP is unchanged and no database is accessed by preparation, even if
`--db` is supplied. No private files are bundled with this project; tests generate
invented ZIPs in temporary directories.

Follow the existing inspect/import/branch/title-review/search workflow after
preparation. Inspect warnings before importing and optionally use the explicit
conversation selector. Preparing multiple numbered parts requires separate explicit
commands and output paths. Their later imports are separate transactions; no
all-parts completeness or all-parts atomic import is implied.

## Validation and fixed safety bounds

Before any output is staged, preparation requires:

- One exact, unambiguous selected `.json` member. Duplicate selected names fail.
- A portable relative member name, without traversal, absolute paths, backslashes,
  drive separators, empty/dot segments or ASCII control characters.
- A regular selected file, not a directory, symlink or special file.
- No encryption; only stored or DEFLATE compression.
- A ZIP at most **64 MiB**, a selected uncompressed member at most **16 MiB**,
  no more than **1000 central-directory entries**, and at most **200:1** declared
  expansion ratio for the selected member.
- Bounded decompression, consistent declared/result size and ZIP CRC validation.
- UTF-8 strict JSON and successful validation by the existing web-export normalizer.

The archive is read once into a bounded byte snapshot. A conservative central-header
signature count occurs before ZIP entry objects are constructed; matching bytes in
compressed content can cause a false rejection. Unselected members are not decoded,
shape-validated or extracted; unsafe unrelated names are harmless here because no
extraction path is derived from them. This is not a general-purpose ZIP scanner.

Unsupported/oversized archives fail rather than weakening these bounds. This
helper will reject some legitimate large exports. You can use an appropriate local
archive tool outside Recap to prepare a supported JSON separately; the helper does
not split, repair, decrypt or recover corrupt files. It is not a complete export
compatibility guarantee, malware scan or sandbox for arbitrary archives. JSON is
parsed in memory, so bounded bytes are not a constant-memory guarantee.

## New-file publication and failures

Output never overwrites an existing path, including an existing symlink. The
parent directory must already exist. Data is fully validated, written to a private
same-directory staging file, flushed, and published by an atomic no-overwrite hard
link. Competing writers to the same path cannot both publish. Filesystems without
hard-link support fail; there is no overwrite/rename fallback. This implementation
assumes an operator-controlled destination directory, not a hostile concurrent
filesystem namespace. It does not promise durability against all crashes or power
loss, and does not fsync a directory entry on every platform.

Normally the staging link is removed. A successful publication with failed staging
cleanup is reported as `staging_cleanup_complete: false`, with the remaining staging
basename. The requested output already contains the complete prepared file; do not
blindly retry. Verify it, then remove only the named leftover staging link when
appropriate. A crash can also leave a staging file. This is not a multi-file
transaction. Existing output is never removed as part of error recovery.

## Hashes, privacy and provenance

The receipt separates `archive_sha256` (outer ZIP) and `prepared_sha256` (the exact
selected JSON bytes). `coverage.original_sha256` equals the latter. Subsequent
normalization/import/search provenance uses the **prepared JSON hash**, not the ZIP
hash. The receipt is the separate local link between them; it is not automatically
stored in the archive database or signed. `find --export-sha256` should therefore
use the prepared JSON hash.

The selected JSON is copied byte-for-byte, not reserialized. Preparation validates
only the supported shape; extraction omissions and branch warnings remain in the
coverage report. It does not restore deleted chats or certify that all exported
conversations/messages were included by the service. The prepared file and receipt
can contain sensitive data/identifiers, so keep them private. CRC and hashes check
consistency, not sender authenticity or privacy. No title is generated/applied,
no remote state is changed, and nothing is transmitted.

## Declared fixed resource limits

Successful v1 receipts now include `limits`: `member_bytes` (16777216),
`ratio` (200), `entries` (1000), `archive_ceiling` (67108864), and
`operator_supplied` (false). These disclose existing fixed safety bounds; the default ceiling is unchanged. An operator may lower the member bound as
described below; no limit increase is permitted. Invalid or over-budget archives still
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
new compression formats or chunked archive handling.

## Lowering the member budget

Both `inspect-web-zip` and `prepare-web-export` accept `--max-member-bytes N`.
N must be an integer from 1 through 16777216 (the existing 16 MiB hard maximum).
Omitting the option retains the previous default. The value is validated before
archive access. It can reduce the decompressed-member byte budget on a constrained
computer; it cannot raise any safety bound or make a rejected large member eligible.
It does not cap total process memory: the ZIP snapshot and decoded JSON also use
memory. Archive-size, entry-count and 200:1 ratio bounds stay unchanged.

Repeat the selected value in both commands when carrying a metadata selection to
preparation. `--expected-archive-sha256` binds archive bytes, not this option.
Preparation independently rechecks its effective member bound and reads at most
N+1 bytes before size/CRC/JSON checks and before staging. No streaming or partial
output is introduced. Successful `limits.member_bytes` echoes N and
`operator_supplied` is true even when N equals the default.
