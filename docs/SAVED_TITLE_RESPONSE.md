# Turn a saved title response into a reviewable local proposal

An operator may already have a title response from a separately authorized tool.
`complete-response` validates that local JSON against a saved preparation and the
current archive. It does not call a model, send data, ask for credentials, prove
which model ran, or apply a title. Use this path rather than mislabeling a real
response as a synthetic mock or manually copying fingerprint fields.

## A complete example with invented input and output

Run from the repository root with Python 3.10+ and SQLite FTS5. Choose a **new**
private directory outside the repository. The commands below use
`../recap-response-demo`; replace it consistently if needed. Its parent must exist.
Stop if directory creation or any command fails. Do not reuse an existing folder.
The read-only adapter commands now save directly with `--output NEW_JSON`, using
UTF-8 without a BOM and the existing atomic no-overwrite writer. No shell `>` or
special shell encoding is needed. Use new filenames whose parent exists in an
operator-controlled private directory. Filesystems must support hard links.
Inspect each exit status and stop on failure.

The provider, model and `example.invalid` endpoint below are invented configuration
labels. The response in `examples/` is also invented, not actual model output.
None of these commands contacts the endpoint. Preparation saves private user text
to a local file even though the default external execution setting is disabled.

```sh
mkdir ../recap-response-demo
python recap.py --db ../recap-response-demo/archive.sqlite import examples/web-export.json --format web --source demo
python title_adapter.py --db ../recap-response-demo/archive.sqlite --source demo --conversation synthetic-chat --kind external --provider-id synthetic-provider --model synthetic-title-v1 --endpoint https://example.invalid/title --evidence-scope web-branch --input examples/web-export.json --node m2 prepare --output ../recap-response-demo/prepared.json
python title_adapter.py --db ../recap-response-demo/archive.sqlite --source demo --conversation synthetic-chat --kind external --provider-id synthetic-provider --model synthetic-title-v1 --endpoint https://example.invalid/title --evidence-scope web-branch --input examples/web-export.json --node m2 complete-response ../recap-response-demo/prepared.json examples/synthetic-title-response.json --output ../recap-response-demo/proposal.json
python recap.py --db ../recap-response-demo/archive.sqlite preview-title ../recap-response-demo/proposal.json --output ../recap-response-demo/reviewed.json
```

With `--output`, stdout is a metadata-only `SAVED` receipt, not the saved document.
The adapter's prepare receipt has `document_kind: request`; completion has
`document_kind: proposal`. The preview command reports `document_kind: preview`.
Each receipt gives exact saved-file bytes/hash and staging cleanup status, but no
payload or destination path. It does not grant permission to transmit data or apply
a title. If cleanup is incomplete, the complete output already exists: inspect the
reported staging basename rather than retrying blindly. See [native saving limits](TITLE_DOCUMENT_FILES.md).

**Stop and open `prepared.json`, `proposal.json` and `reviewed.json`.** Check the
selected user payload, original export hash and scope. In the reviewed document,
verify `proposal.source: demo`, `proposal.conversation: synthetic-chat`,
`proposal.title: Synthetic orchard experimental design`, `previous_title: New chat`
and `expected_revision: 0`. Inspect meaning and possible private details yourself.
Only after that explicit review:

```sh
python recap.py --db ../recap-response-demo/archive.sqlite apply-title ../recap-response-demo/reviewed.json
python recap.py --db ../recap-response-demo/archive.sqlite find "experimental design" --source demo
```

The search finds the newly titled local conversation. Original messages and source
bytes are unchanged; no ChatGPT or Codex title changed remotely. The proposal also
works with `review-titles --proposal FILE --supplied-only` before fresh individual
preview/apply. Completion itself is read-only and repeatable; applying the same
reviewed preview twice remains a stale-revision error.

## Native saving keeps the same offline contract

Only adapter `prepare` and `complete-response` accept this option. `generate`,
consent processing, external execution and transfer simulation are unchanged;
`generate --output` rejects at argument parsing. No network or credential transport
is added. The Python preparation/completion APIs remain read-only and return the
same objects. Without `--output`, both commands still print their original JSON.

The saved request contains the exact same logical preparation envelope, not a
receipt wrapper or newly approved consent. Its canonical `payload_sha256` still
binds the model payload; the receipt's `sha256` instead describes the pretty-printed
saved file. These hashes have different purposes and need not match. Completion
reads the actual request file, never its receipt. Formatting a file does not bypass
canonical freshness, evidence, selected scope or provider configuration checks.

Existing destinations, including inputs, archive files, hard links and symlinks,
are refused without replacement. A missing parent is not created. Output is staged,
synced, closed and linked only after successful preparation/completion. A stale or
invalid request produces no new output. Ordinary save failures use fixed
`OUTPUT_FAILED`, without echoing private paths or contents. Check the destination,
parent and filesystem capabilities instead of changing source hashes or bypassing
validation. A successful `SAVED` with incomplete cleanup is not a failed save.

Native files remain UTF-8 without a BOM. This feature does not change input-decoding
rules: adapter prepared-request, response, mock and consent readers still require
UTF-8 without a BOM, even though separate proposal/preview readers tolerate one
initial signature. No conversion or repair is performed. Legacy redirection remains
possible but has shell encoding/overwrite hazards; do not combine it with native
`--output` or use it on an input path.

## Use a separately obtained response

A response is one UTF-8 JSON object with a single-line `title` and nonempty unique
`evidence_message_ids` from the prepared payload. IDs omitted by branch, replay,
attribution or request limits cannot support its title. Extra response metadata is
not copied into the proposal. A valid evidence ID does not establish that the title
accurately summarizes its text; semantic validation is not performed.

Save the original `prepare` output unchanged. Completion takes the same explicit
source/conversation, provider/model/endpoint and optional evidence-scope arguments.
It reconstructs the request from current, verified archive/source evidence and
compares the entire canonical preparation envelope. Changed text, selected scope,
source hash, payload, configuration or unknown added fields reject with
`PREPARED_REQUEST_STALE`; unreadable or now-unverified sources can reject earlier
with `SOURCE_ERROR`. Do not edit hashes or copy new hashes into an old preparation.
Inspect a fresh request and obtain/review a corresponding response instead.

Local title revisions alone do not change the message request. A fresh preview
still reports the current title and revision and must be reviewed before apply.
Reimporting changed source bytes does not authorize reuse of an old scoped request.
Identical renamed files can match when existing provenance resolves their identities.

The command requires `--kind external` only to label the locally supplied output
path. It does not require `--allow-external` or a consent file because it performs
no transmission. It never makes the existing external `generate` path operational.
The result records `provider: external-adapter`,
`response_origin: supplied_local_file` and `provider_execution: NOT_PERFORMED`.
Those fields and provider/model labels are descriptions, not execution receipts,
authenticated authorship or proof the model saw the saved payload.

Your separate tool still needs appropriate authorization to receive the actual
data. This command grants none. The full preparation envelope contains local source
identifiers and provenance as well as user text; do not upload it as a diagnostic
log or assume all its fields belong in an external request. Keep all real request,
response, proposal and archive files private and outside version control.

## Bounds and failures

Prepared-document files are read once with an 8 MiB limit, allowing the CLI's ASCII
escaped local envelope. Response files are read once with the existing 16 KiB
limit. The stricter prepared payload and 1 MiB selection-context limits still apply
when reconstructing the request. Duplicate JSON keys, malformed Unicode, nonfinite
values and nonobject inputs reject before archive reads. File errors use fixed
`REQUEST_INVALID` or `INVALID_RESPONSE` codes without echoing private file contents.
Oversized library objects are also refused after serialization; these bounds are
not a guarantee of constant memory for an already supplied Python object.

Completion reads a fresh archive snapshot and returns a proposal only. Concurrent
changes after that snapshot are still caught by the normal full-content and title
revision checks at apply. No retry, background process, automatic fallback, remote
write or network integration is introduced.
