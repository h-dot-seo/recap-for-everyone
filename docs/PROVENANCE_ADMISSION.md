# Explicit Python provenance admission

The existing `ingest_bytes(..., provenance=...)` API and file `ingest` fallback
now validate supplied provenance before opening SQLite. This closes a case in
which an invalid original hash could be committed and later make recovery
manifest declaration fail. This is a narrowing of malformed API inputs, not a
new import mode, ledger, or recovery format.

Each entry is a mapping with `conversation_id`, `message_id`, `origin_sha256`,
and `origin_locator`. The first two must identify a record in this input, not
merely an older record in the archive. The hash must be 64 lowercase hexadecimal
characters. The locator must be a nonempty string (whitespace is not stripped).
`parent_id` may be omitted, null, or a string, including the empty string.
Stored strings must encode as UTF-8. Booleans and other wrong types do not stand
in for strings. Extra mapping members remain ignored, as adapter records also
carry text and other fields. Diagnostics identify the contract, not supplied
private values.

`None` still means no provenance ledger is requested. An empty iterable still
requests the existing empty ledgers. Iterables are consumed once before opening
SQLite; their ordering and duplicate entries retain the existing insertion and
`INSERT OR IGNORE` behavior. Partial provenance is allowed: this validation
neither requires full input coverage nor resolves conflicting supplied claims.
A failure while consuming or validating provenance occurs before any database
connection, so it does not create a new empty schema or change an existing DB.
Normal database failures retain the existing transaction and schema behavior.

This does not verify that a claimed hash identifies an authentic export, that a
locator resolves, or that a parent exists. It does not promote a supplied claim
to verified evidence, authority, or rights. It does not repair old malformed
ledgers. The public CLI still ignores optional origin members inside ordinary
normalized JSONL; it does not automatically accept them as provenance.

File ingestion with explicit provenance retains its single `read_bytes`
snapshot fallback. Ordinary file ingestion without provenance retains its
same-handle two-pass observation contract. Normalized byte APIs, built-in
adapter serialization, receipts, message/FTS rows, and recovery schemas remain
unchanged for valid inputs.
