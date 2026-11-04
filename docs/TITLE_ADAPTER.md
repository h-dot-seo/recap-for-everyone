# Title adapter contract

## Implemented boundary

`title_adapter.py` prepares a provider-neutral request and turns validated local/mock
or explicitly supplied response files into the existing proposal shape. It never changes a title. The operator
must separately preview and apply a proposal with the existing content/revision
checks. No actual semantic model is connected, and no semantic quality is claimed.

Only two built-in implementations execute: local excerpt selection and a synthetic
mock response. The external path is deliberately unconfigured. Enabling it and
providing matching consent still returns `EXTERNAL_NOT_CONFIGURED`; no HTTP client,
credential lookup, API call or payment behavior is included.

For a response already obtained through a separately authorized tool, use the
[saved-response workflow](SAVED_TITLE_RESPONSE.md). Its read-only `complete-response`
command revalidates the original preparation against current evidence before making
a proposal. It performs no external execution and does not attest model provenance.

## Frozen request

`prepare_request` reads the local conversation snapshot and creates immutable UTF-8
JSON bytes. Provider input contains the protocol, model, instruction and selected
user-message IDs/text only. Source/conversation identifiers, assistant/tool messages,
database paths and the full-conversation fingerprint remain in the local envelope.

Selection considers the most recent 20 user messages, includes at most the first
4,000 characters of each, and keeps at most 12,000 characters in total, favoring the
newest messages. Included rows are returned in original archive order. The final
serialized request is limited to 65,536 bytes. Long identifiers can still cause a
request-size rejection. The existing snapshot step reads the full conversation;
outbound bounds are not a whole-archive memory guarantee.

Bytes are canonicalized with sorted keys, compact separators and UTF-8 encoding.
The exact bytes are hashed. A future transport must send these approved bytes, not
reread the database, append hidden context, change the model, or serialize a modified
request after consent. Message content is untrusted quoted evidence, not instructions
to change application behavior.

## Choose verified evidence before request limits

The default `--evidence-scope raw` retains the existing archive-wide behavior.
It can include abandoned web branches, rolled-back local turns and harness text
carried in user-role records. User role alone is not proof of human authorship.
For narrower evidence, explicitly name an original export and one scope:

- `web-branch`: the selected mapping node's parent path, or the file's valid
  `current_node`. Optional `--node` selects an exact node. No node is guessed.
- `local-replay`: verified retained text turns under the existing fail-closed
  replay grammar. Unsupported or unresolved history remains an error.
- `local-attributed`: typed text parts explicitly labeled with producer
  provenance `user`. Missing, malformed or unknown attribution is not a reason
  to fall back to harness/unknown text. Labels remain unsigned, not authenticated
  authorship or authorization. This scope does not also apply replay filtering.

These modes use the same source-occurrence checks as the existing branch, replay
and attributed title commands. They read the explicitly named file once and match
its immutable bytes to imported provenance and current archive evidence. Web scope
checks the selected path; local scopes check all extracted raw messages in the
selected conversation. They do not reconstruct a selection from a saved proposal's
unsigned context. Changed or unimported source bytes, ambiguous occurrences and
unsupported shapes fail without raw fallback.

All eligible selected user texts, not just the first excerpt's evidence, feed the
existing recent-user limits. Selection occurs **before** the 20-message, 4,000-character
per-message and 12,000-character total bounds. Repeated selected occurrences with
one archive ID and identical text collapse at their most recent position. If the
same ID selects different text, preparation rejects rather than choosing an
attribution variant. The full raw archive fingerprint still guards preview/apply,
including excluded branches, discarded turns and harness content.

For the already imported synthetic web example in the walkthrough:

```sh
python title_adapter.py --db ../recap-demo/archive.sqlite --source web-demo --conversation synthetic-chat --evidence-scope web-branch --input examples/web-export.json --node m2 prepare
python title_adapter.py --db ../recap-demo/archive.sqlite --source web-demo --conversation synthetic-chat --evidence-scope web-branch --input examples/web-export.json --node m2 generate > ../recap-demo/adapter-proposal.json
```

For an imported local file, use `--evidence-scope local-replay --input INPUT` or
`--evidence-scope local-attributed --input INPUT` and its exact source/conversation.
The flags precede `prepare` or `generate`. Nonraw scopes require `--input`; raw
scope rejects it, and `--node` is only valid with `web-branch`. The local/mock
generation choices and external-disabled boundary are otherwise unchanged.
Each CLI invocation prepares a fresh request; `generate` does not load an earlier
`prepare` result. If the archive or an intentionally reimported export changes
between commands, inspect the new proposal and scope again before applying it.

Scoped preparation and proposals add local-only `evidence_context`: the mode,
descriptive selection details, and counts for input user occurrences, unique user
messages, included/omitted messages and truncated messages. Selection details cover
the eligible source scope, which can be larger than the bounded provider payload;
returned title evidence must still name IDs actually in that payload. Context is
frozen separately and limited to 1 MiB. It is private, unsigned and not reauthenticated
by preview/apply. Neither context, source hash nor source/conversation labels are
added to outbound payload bytes. Only a changed outbound payload changes the
consent hash. No actual transmission is implemented.

Review the resulting proposal through `preview-title`, then explicitly apply one
reviewed title, or supply it to `review-titles --proposal FILE --supplied-only`.
Do not mistake a narrower excerpt for a semantic summary. Existing raw output
shapes remain unchanged, and no source text or remote title is modified.

## Explicit external consent contract

External settings identify provider ID, HTTPS endpoint and model. Endpoints cannot
contain userinfo, query strings, fragments, whitespace or port zero. Scheme/host
case and default HTTPS port are normalized; the path remains explicit.

The consent record requires `approved: true` plus the exact provider ID, normalized
endpoint, model and payload SHA-256 returned by `consent_scope`. Any mismatch fails
before execution. The enabled setting alone is insufficient, and consent alone
cannot enable an external path. A changed prompt/body/model invalidates prior scope.

This record represents explicit consent already obtained by the calling application;
it is not an identity-verification mechanism, consent UI or permission inferred from
conversation text. A future real integration must obtain appropriate user approval
for its actual recipient and data, use an authorized credential mechanism, and honor
withdrawals. This release performs no transmission even with a valid record.

`prepare` writes private user text to stdout deliberately for local inspection. It
is not a sanitized log or a public artifact. Do not upload its output, mock/real
response files or proposals to the public code repository.

## Responses and failures

A response must contain a valid single-line title and a nonempty, unique list of
user evidence IDs that occurred in the outbound payload. Assistant IDs or excluded
user IDs are rejected. Only whitelisted fields are copied into the final proposal;
raw provider metadata and response bodies are not returned or persisted. The runner
limits raw/mock response input and its IPC envelope to 16,384 bytes.

Errors use fixed codes: `CONFIG_INVALID`, `SOURCE_ERROR`, `NO_USER_EVIDENCE`,
`REQUEST_INVALID`, `CONSENT_REQUIRED`, `EXTERNAL_DISABLED`,
`EXTERNAL_NOT_CONFIGURED`, `INVALID_RESPONSE`, `PROVIDER_FAILED`, `TIMEOUT`, and
`PREPARED_REQUEST_STALE` for changed saved preparations.
Provider exception strings, raw response text and private source paths are not
included in CLI errors. Generation does not write logs or title history.

## Deadline and process lifecycle

Built-in local/mock work runs in a spawned subprocess. Its Python stdout/stderr are
discarded. A monotonic execution deadline includes startup; timeout terminates the
worker, escalates to kill if needed and reaps it. Worker crashes/EOF produce a fixed
error. There are no automatic retries and no background worker is intentionally
left running after the call.

The configured timeout is an execution deadline, not a strict total-return-time
guarantee: process startup, termination grace and final OS reaping can add overhead.
The supported built-ins do not create descendants. A future external transport must
also control any descendants and honor its own bounded I/O. Local termination cannot
prove that a remote request was cancelled, not accepted, or not charged. Do not retry
an uncertain external outcome automatically.

The subprocess is a lifecycle/logging boundary, not a sandbox for arbitrary code.
No dynamic plugin/module loading is provided. Library callers must use an importable
entry point and a normal `if __name__ == '__main__'` guard when spawning; the shipped
CLI handles this. Tests use synthetic responses and do not access external services.

Adapter CLI JSON uses ASCII escapes for non-ASCII characters so titles remain
parseable even under a non-UTF-8 terminal encoding. Escaping is not redaction.
