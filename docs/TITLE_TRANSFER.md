# Mock-only platform title transfer contract

This module is a **contract rehearsal, not a platform integration**. No ChatGPT,
Codex, browser, unofficial API, HTTP transport, credentials, plugins or network
calls are implemented. No provider other than `synthetic-mock` is accepted. Do not
use the result as evidence that a remote title changed or a remote identity was
verified. Real integrations would require a separately authorized, documented
platform API and a new security review; enabling one is not a configuration flag.

The contract separates four things that must not be conflated:

1. A locally reviewed display title and freshly checked manual title plan.
2. An explicitly supplied target **provider/account/conversation/title/revision**
   snapshot. Archive conversation IDs are never inferred to be remote IDs.
3. A dry-run request containing that plan, snapshot, proposed title and digest.
4. Explicit approval bound to that complete request, followed by a **mock-only**
   atomic compare-and-set. Approval does not skip the fresh local plan check.

## Try it with synthetic data

Complete either flow in [the walkthrough](TITLE_WALKTHROUGH.md) first. Use its
private scratch directory and UTF-8 shell guidance. These files may contain
sensitive title/identity metadata when used with private inputs: never publish them.

For its web example:

```sh
python recap.py --db ../recap-demo/archive.sqlite export-title-plan examples/web-export.json --format web --source web-demo --conversation synthetic-chat > ../recap-demo/manual-plan.json
```

Create `../recap-demo/mock-target.json` with **invented** values:

```json
{
  "provider": "synthetic-mock",
  "account_id": "invented-account",
  "conversation_id": "separate-invented-target",
  "revision": "synthetic-version-1",
  "title": "Mock old title"
}
```

The target has exactly these five fields. Identity and revision are nonempty
bounded strings; revision is opaque, not the local archive revision. Title
validation is the same as local title validation. Unknown fields/providers fail
closed. Neither the source file nor target file is changed:

```sh
python recap.py --db ../recap-demo/archive.sqlite title-adapter-dry-run examples/web-export.json ../recap-demo/manual-plan.json ../recap-demo/mock-target.json > ../recap-demo/request.json
```

Inspect the request. Its status is `NOT_EXECUTED` and `remote_mutation` is false.
`action` compares the proposed title to the **mock target** title, not the archived
original title. The target verification label explicitly says caller-supplied
synthetic snapshot. The full request is bound by `request_sha256` (canonical JSON,
SHA-256 excluding only the digest field). Additional/changed fields are rejected.

Only if you want to simulate this exact request, create `approval.json` in the
scratch directory, replacing the placeholder with the exact request digest:

```json
{
  "schema": "recap.title-transfer-approval.v1",
  "request_sha256": "COPY_THE_REQUEST_SHA256_HERE",
  "approve": true
}
```

Approval requires boolean `true`; missing approval, `1`, strings, extra keys,
other request hashes, or altered/stale requests are rejected. Then:

```sh
python recap.py --db ../recap-demo/archive.sqlite title-adapter-simulate examples/web-export.json ../recap-demo/request.json ../recap-demo/approval.json ../recap-demo/mock-target.json
```

The result says `SIMULATED_ONLY`, `remote_mutation: false`, and shows the target
**as it would be in memory**. No source, database, target/request/approval file or
service is written. The local example works identically: export a `local-codex`
plan for `synthetic-rollout` and use `examples/rollback-session.jsonl` consistently.
The raw-history warnings remain inside that plan; no replay support is expanded.

## Validation and limits

- The dry run and simulation independently run `check_plan` against the explicit
  source file and current archive. Modified source bytes, stale local title or
  evidence, altered plan values, and extra fields fail before mock mutation.
- Approval is a plain unsigned local JSON instruction, **not authentication,
  proof of human review, a signed capability or permission for a real service**.
  Anyone able to edit the files can create a new digest/approval. Keep the review
  boundary outside untrusted content and never auto-approve retrieved instructions.
- `MockTitleAdapter` owns one isolated in-memory snapshot and a lock. Its CAS
  checks provider/account/conversation/title/revision together. Two writers to the
  same instance with the same old version cannot both rename successfully. A
  successful rename produces a new opaque synthetic revision; no-op leaves it
  unchanged. Retrying that old rename on the same instance fails stale validation.
- Every CLI simulation constructs a **new ephemeral mock** from the supplied target
  file. Repeating the CLI with unchanged files repeats the simulation successfully;
  there is no persistent replay protection, live observation or durable receipt.
  Changing the target file's identity/title/revision while keeping the request
  yields `MOCK_TARGET_STALE`. To intentionally revise the request, create and
  inspect a new dry run and explicit approval.
- A changed source/plan requires fresh review. The local check and mock CAS are
  not a distributed transaction: local state could change after the check. There
  is no assertion of atomicity across a database and any future remote service.
- There is no timeout/retry/network failure behavior to test because no transport
  exists. The contract is not yet a production provider SDK. Future live work
  needs verified target resolution, permission checks, actual platform revision
  semantics, secure authentication, idempotency, timeout/uncertain-outcome
  reconciliation, and independent review before any transmission or mutation.

The Python API exposes `dry_run`, `MockTitleAdapter` and `simulate`. The mock CAS
primitive is a test fixture, not a security boundary; only `simulate` validates
request-bound approval. Custom/subclass adapters are rejected by `simulate`.
