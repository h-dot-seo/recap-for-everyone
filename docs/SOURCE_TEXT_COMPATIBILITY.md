# UTF-8 signatures and physical source lines

Web JSON, generic local JSONL, typed Codex local JSONL and normalized `ingest`
accept strict UTF-8 with or without **one initial UTF-8 byte order mark (BOM)**.
The three signature bytes are ignored only when decoding the beginning of the
file for parsing. They remain part of its original byte count and SHA-256.
No source file is rewritten or silently re-encoded.

This is an explicit compatibility choice, not encoding detection or a claim that
all exporters emit signatures. RFC 8259 permits JSON readers to tolerate an
initial signature, while discouraging its addition to network JSON.
See [RFC 8259, section 8.1](https://www.rfc-editor.org/rfc/rfc8259#section-8.1).
The implementation uses Python's strict `utf-8-sig` decoding, which skips an
optional signature at the start. See the [Python 3.10 codec documentation](https://docs.python.org/3.10/library/codecs.html#module-encodings.utf_8_sig).

## Consistent across the source workflow

Source inventory, inspection, selected imports, conflict diagnostics, web-branch
selection, local replay, source-attributed text selection and manual title plans
share the same decoding policy. The title adapter inherits it through those
verified source selections. No source is read again merely to decode its signature.

Successful export coverage adds `utf8_bom_present: true` when a signature was
present. Normalized `ingest` receipts and successful replay projections also add
that field for signed input. No-BOM response shapes remain unchanged. This flag
describes byte framing, not a verified exporter, person or authorization.

ZIP preparation validates a selected member under the same rules, then copies its
bytes unchanged. A BOM in that member therefore remains in the prepared file and
its hash. Archive size, compression, CRC, selection and no-overwrite checks still
apply. No additional archive member is selected or imported.

## Line numbers without changing message text

Local and normalized JSONL readers recognize LF, CRLF and bare CR as physical
record boundaries, including files that mix them. Blank physical lines still
count toward `line:N`, fallback message IDs and normalized `source_line` values.
CRLF counts as one boundary. A signature is not a line and never increments a
locator. Replay and its title bridge now use the same boundaries as raw imports,
so a supported CR-framed file does not import successfully only to fail title
reconstruction because of a different line splitter.

Unicode separators U+0085, U+2028 and U+2029 inside JSON strings do not become
record boundaries. A U+FEFF character inside a quoted JSON value remains message
data. Escaped `\r` and `\n` inside strings are decoded normally and preserved in
the extracted text. The existing legacy local profile still applies its documented
text trimming; typed Codex text retains its existing whitespace rules.

This affects framing only. Duplicate-key detection, surrogate checks, roles,
identity conflicts, branch validation and the narrow replay grammar are unchanged.
It does not add support for unknown event kinds, compaction or inherited history.

## Deliberate failures and recovery

- UTF-16, UTF-32, malformed UTF-8 and partial UTF-8 signatures are not guessed or
  repaired. The reader never falls back to a system encoding or replacement text.
- Two leading signatures, a signature after leading whitespace, or another
  signature outside JSON strings in the middle of a JSONL file remain malformed.
  Only the optional first three bytes are ignored for parsing.
- Malformed exports reject before database access. Invalid ZIP members do not
  publish a prepared output. Unsupported replay returns no partial projected text.
- Request, response, proposal and review-document JSON loaders are unchanged.
  This compatibility applies to source exports and normalized ingestion, not an
  implicit relaxation of every JSON contract.

Adding/removing a BOM or changing newline bytes changes the original source hash,
even when extracted text is identical. An old `--expected-export-sha256` still
rejects. A branch or source-scoped title request still needs matching imported
provenance. Inspect and intentionally reimport changed bytes when appropriate;
do not replace old hashes inside a saved proposal or preparation. Reimporting
identical parsed identities adds provenance without inventing new messages, while
real content/metadata conflicts remain transactionally rejected.

Keep originals, inspect coverage and use the normal fresh preview and explicit
local-title apply steps. This increment sends nothing externally, changes no remote
session title and introduces no source-repair or format-conversion command.
