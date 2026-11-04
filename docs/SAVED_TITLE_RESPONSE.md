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
Redirection overwrites its target, so use a UTF-8-capable shell and inspect each
exit status. POSIX shells and PowerShell 7 are suitable; Windows PowerShell 5's
default UTF-16 redirection is not.

The provider, model and `example.invalid` endpoint below are invented configuration
labels. The response in `examples/` is also invented, not actual model output.
None of these commands contacts the endpoint. Preparation prints private user text
to a local file even though the default external execution setting is disabled.

```sh
mkdir ../recap-response-demo
python recap.py --db ../recap-response-demo/archive.sqlite import examples/web-export.json --format web --source demo
python title_adapter.py --db ../recap-response-demo/archive.sqlite --source demo --conversation synthetic-chat --kind external --provider-id synthetic-provider --model synthetic-title-v1 --endpoint https://example.invalid/title --evidence-scope web-branch --input examples/web-export.json --node m2 prepare > ../recap-response-demo/prepared.json
python title_adapter.py --db ../recap-response-demo/archive.sqlite --source demo --conversation synthetic-chat --kind external --provider-id synthetic-provider --model synthetic-title-v1 --endpoint https://example.invalid/title --evidence-scope web-branch --input examples/web-export.json --node m2 complete-response ../recap-response-demo/prepared.json examples/synthetic-title-response.json > ../recap-response-demo/proposal.json
python recap.py --db ../recap-response-demo/archive.sqlite preview-title ../recap-response-demo/proposal.json > ../recap-response-demo/reviewed.json
```

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
