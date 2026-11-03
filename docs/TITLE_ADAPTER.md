# Title adapter contract

## Implemented boundary

`title_adapter.py` prepares a provider-neutral request and turns validated local/mock
responses into the existing proposal shape. It never changes a title. The operator
must separately preview and apply a proposal with the existing content/revision
checks. No actual semantic model is connected, and no semantic quality is claimed.

Only two built-in implementations execute: local excerpt selection and a synthetic
mock response. The external path is deliberately unconfigured. Enabling it and
providing matching consent still returns `EXTERNAL_NOT_CONFIGURED`; no HTTP client,
credential lookup, API call or payment behavior is included.

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
`EXTERNAL_NOT_CONFIGURED`, `INVALID_RESPONSE`, `PROVIDER_FAILED`, and `TIMEOUT`.
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
