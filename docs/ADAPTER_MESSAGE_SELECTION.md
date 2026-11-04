# Use the request you found in a saved-response workflow

A useful request can be older than twenty later user messages. The adapter's
ordinary recent-user window may omit it even after `find` identifies the right
message. Direct excerpt selection already handles this case. The adapter now also
accepts an explicit `--message ID`, so the same choice can feed a locally prepared
request and a separately supplied response. Nothing is sent to a model here.

This is an optional extension, not automatic relevance ranking. With no selector,
the existing recent-user window, output shape and scope rules are unchanged. The
adapter still produces a proposal only; preview and explicit apply remain separate.

## Try the complete path with invented data

Run from the repository root after [installation](INSTALL.md). Create a new private
directory with an existing parent. Use native `--output` files, not shell
redirection: each destination must be new. A `SAVED` receipt is metadata about the
file, not its contents, permission to transmit it or approval to change a title.
See [saved documents](TITLE_DOCUMENT_FILES.md) for no-overwrite and cleanup limits.

The supplied local fixture has 22 records: session metadata, one substantive
user-attributed request at `line:2`, and twenty later user-attributed `Thanks`
messages. The first request also has a harness-labeled text part. This is a raw
local-attribution example, not a supported completed-turn replay fixture. Both
files in `examples/` are synthetic; the response is invented, not model output.

```sh
mkdir ../recap-adapter-focus-demo
python recap.py --db ../recap-adapter-focus-demo/archive.sqlite import examples/adapter-message-focus.jsonl --format local-codex --source demo
python recap.py --db ../recap-adapter-focus-demo/archive.sqlite find irrigation --source demo
python recap.py --db ../recap-adapter-focus-demo/archive.sqlite show --source demo --conversation synthetic-adapter-focus --message topic
python title_adapter.py --db ../recap-adapter-focus-demo/archive.sqlite --source demo --conversation synthetic-adapter-focus --kind external --provider-id synthetic-provider --model synthetic-title-v1 --endpoint https://example.invalid/title --evidence-scope local-attributed --input examples/adapter-message-focus.jsonl prepare --output ../recap-adapter-focus-demo/recent.json
```

The archive contains 21 user messages. Search finds `topic`; the raw `show` view
includes its harness text as well as the meaningful request. Open `recent.json`:
the default payload contains only `followup-01` through `followup-20`. Do not edit
that payload or its hashes to force another message into a saved preparation.
Create a fresh explicit preparation instead:

```sh
python title_adapter.py --db ../recap-adapter-focus-demo/archive.sqlite --source demo --conversation synthetic-adapter-focus --kind external --provider-id synthetic-provider --model synthetic-title-v1 --endpoint https://example.invalid/title --evidence-scope local-attributed --input examples/adapter-message-focus.jsonl --message topic prepare --output ../recap-adapter-focus-demo/focused.json
python title_adapter.py --db ../recap-adapter-focus-demo/archive.sqlite --source demo --conversation synthetic-adapter-focus --kind external --provider-id synthetic-provider --model synthetic-title-v1 --endpoint https://example.invalid/title --evidence-scope local-attributed --input examples/adapter-message-focus.jsonl --message topic complete-response ../recap-adapter-focus-demo/focused.json examples/adapter-message-response.json --output ../recap-adapter-focus-demo/proposal.json
python recap.py --db ../recap-adapter-focus-demo/archive.sqlite preview-title ../recap-adapter-focus-demo/proposal.json --with-evidence --output ../recap-adapter-focus-demo/reviewed.json
```

Open the actual saved files. The focused payload contains only the user-labeled
text from `topic`: `Compare synthetic orchard irrigation schedules`. Harness text
is excluded from that payload. The supplied response proposes
`Synthetic orchard irrigation comparison`, citing only `topic`.

**Stop and review `reviewed.json`.** Check source `demo`, conversation
`synthetic-adapter-focus`, the chosen message, proposed wording, previous title and
revision zero. Its optional review-evidence view is raw archive text and can still
include the harness part. It is not the filtered adapter payload or proof that a
model saw the chosen text. Only after this review:

```sh
python recap.py --db ../recap-adapter-focus-demo/archive.sqlite apply-title ../recap-adapter-focus-demo/reviewed.json
python recap.py --db ../recap-adapter-focus-demo/archive.sqlite find "irrigation comparison" --source demo
```

The search now finds the new local display title. Source bytes, raw messages,
original titles and provenance are unchanged. Nothing is renamed in another app.
The placeholder provider/model/endpoint do not make a connection; external
execution remains disabled or unconfigured. A real tool needs separate
appropriate authorization to receive actual data.

## Choose exactly within the verified scope

Put `--message` before `prepare`, `generate` or `complete-response`, with the other
adapter flags. Use the **archive message ID** shown by `show` or search, not a
replay projection ID, title, source line or fuzzy phrase. Repeat the same choice
and scope when completing a saved preparation. No selector is inferred from a
response, proposal or saved document.

- `raw`: one archived user-role message. This does not filter branches, rollback
  history or harness parts and does not authenticate human authorship.
- `web-branch`: one user message on the already selected node's parent path.
  `--node` selects the endpoint; `--message` does not choose a different branch.
- `local-replay`: one resolved archived user occurrence in retained turns under
  the existing narrow replay grammar. Rolled-back messages remain ineligible.
- `local-attributed`: one occurrence with eligible producer-labeled user text.
  Only its attributed typed text is selected, not the whole raw message.

If an attributed archive ID has multiple eligible occurrences, add
`--origin-locator line:N` with the exact physical locator in this original export.
Even equal extracted text does not resolve an occurrence ambiguity. This option
requires `--message` and `local-attributed`; it is not a raw archive line selector.
Use provenance for the chosen export, not normalized `source_line`. Renamed,
byte-identical exports can still resolve their imported archive IDs through the
existing provenance checks. Never guess a new filename-based fallback ID.

Malformed selector syntax fails before source/archive reads. Missing, non-user,
out-of-scope or ambiguous choices fail without selecting an alternative. Existing
source verification runs first, so a mismatch or malformed record elsewhere in
that verified scope still rejects. This does not reduce file reading or memory.
Attribution labels remain unsigned, and attribution does not also apply replay.

## Frozen choice and unchanged safety limits

The optional local `evidence_selection` describes the exact message, scope,
requested locator and resolved attributed locator. It is frozen, limited to 65,536
encoded bytes, and returned with the request envelope/proposal, but is not added
to the provider payload. It is not authenticated evidence or permission. Requested and resolved
locators are separate: dropping an explicit locator changes the recipe even if a
unique occurrence would select the same text. Dropping `--message` similarly does
not turn a selected single-message preparation into a default one.

For scoped requests, `adapter_selection` counts still cover the full eligible
source scope before the explicit choice. `omitted_messages` counts distinct archive
IDs, not excluded physical occurrences. Choosing one of two eligible occurrences
of the same ID therefore reports two occurrences, one unique message, one included
message and zero omitted messages. The full source context, including attributed
`evidence_parts`, can describe unchosen occurrences. It is private local context,
not additional provider evidence; the payload alone defines allowable response IDs.
Metadata checks do not reauthenticate a caller-constructed `PreparedRequest` or
prove its descriptive counts. Use the normal prepare/complete workflow for source
verification rather than constructing trusted-looking envelopes yourself.

Completion rebuilds and checks this choice along with the entire saved preparation.
Do not edit its metadata, IDs or hashes to bypass a stale error. Full raw
conversation fingerprints remain in force, including messages excluded from the
payload, and source-backed scopes still require the exact imported original bytes.
An edited source, new conversation content or changed selection requires a fresh
preparation and renewed review. Current display-title changes are still checked by
the later preview/apply revision guard.

The chosen message is still capped at its first 4,000 code points; the existing
12,000-character total and 65,536-byte request limits remain. The 1 MiB scoped
context and 8 MiB saved-preparation limits also remain; choosing one message does
not shrink the full scope metadata or guarantee that a large source fits. Selection
does not extract a later substring or recover truncated text. A response can cite only IDs
actually included in the payload, not other messages in the source context. No
semantic accuracy, privacy clearance or title quality is certified. Local excerpt
generation retains its 80-code-point cap, including possible grapheme cuts.
