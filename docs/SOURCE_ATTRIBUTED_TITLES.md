# Titles from source-labeled user parts

A local user-role message can contain both a request and injected environment or
instruction text. `suggest-attributed-title` uses explicit per-content producer
labels from an original local-codex export to select user-source text for a title,
while keeping the complete raw archive unchanged. This is an opt-in local excerpt,
not a semantic model summary or verified human authorship.

## Public format reference

The implementation was checked against official Codex commit
[`f2b94ef8b52196f127d162c6db71e390b9bb265c`](https://github.com/openai/codex/commit/f2b94ef8b52196f127d162c6db71e390b9bb265c).
The [message model](https://github.com/openai/codex/blob/f2b94ef8b52196f127d162c6db71e390b9bb265c/codex-rs/protocol/src/models.rs)
stores the optional array under
`payload.internal_chat_message_metadata_passthrough.content_item_metadata`.
[Attribution definitions](https://github.com/openai/codex/blob/f2b94ef8b52196f127d162c6db71e390b9bb265c/codex-rs/protocol/src/models/item_metadata.rs)
distinguish user, harness, skills, AGENTS.md, tool, developer-instruction and unknown
sources independently from role and trust. [Positional alignment](https://github.com/openai/codex/blob/f2b94ef8b52196f127d162c6db71e390b9bb265c/codex-rs/context-fragments/src/annotated_content.rs)
includes nontext parts. Missing upstream entries can be unknown; the stricter Recap
proposal contract below does not reproduce upstream's permissive fallback behavior.
This pinned implementation detail is not a universal stable export schema.

## Synthetic walkthrough

Create a fresh private scratch directory outside the public repository. If a path
already exists, choose another rather than overwriting files. The supplied example
is entirely invented; its producer labels are synthetic fixtures, not identity proof.

```sh
mkdir ../recap-attribution-demo
python recap.py inspect examples/source-attributed-session.jsonl --format local-codex
python recap.py --db ../recap-attribution-demo/archive.sqlite import examples/source-attributed-session.jsonl --format local-codex --source demo
python recap.py --db ../recap-attribution-demo/archive.sqlite suggest-attributed-title examples/source-attributed-session.jsonl --source demo --conversation synthetic-attributed > ../recap-attribution-demo/proposal.json
python recap.py --db ../recap-attribution-demo/archive.sqlite preview-title ../recap-attribution-demo/proposal.json > ../recap-attribution-demo/reviewed.json
```

Read both files before deciding to apply. The proposal is
`Design a synthetic lunar calendar`, backed by message `synthetic-u1`, `line:2`
and zero-based content index `2`. The image at index `1` is not extracted and does
not shift text attribution. To apply that reviewed local title:

```sh
python recap.py --db ../recap-attribution-demo/archive.sqlite apply-title ../recap-attribution-demo/reviewed.json
python recap.py --db ../recap-attribution-demo/archive.sqlite find "lunar calendar" --source demo
python recap.py --db ../recap-attribution-demo/archive.sqlite show --source demo --conversation synthetic-attributed --message synthetic-u1
```

The last command still shows the raw environment text and user request. Nothing
was deleted or rewritten to produce the cleaner title. The standalone equivalent
is `attributed_title.py --db DB --source SOURCE --conversation ID INPUT`.

## Exact selection and rejection contract

- The input is one explicitly supplied local-codex JSONL export, read into one
  immutable byte snapshot. The original whole-file hash and physical locators
  must match archived occurrences for the selected conversation.
- Only extracted user-role messages are title candidates. Only typed input/output
  text parts with explicit `provenance.type` equal to `user` are eligible.
- Metadata positions refer to every content part, including media. If an array is
  present, its length must equal the full content array length. Recap rejects
  shorter/longer arrays instead of padding or ignoring entries.
- Missing/null metadata is unknown. User role, content kinds, XML-like tags,
  `harness_injected:false` and `user_configured` do not establish user attribution.
- Recognized provenance variants and their field types are checked. Unknown entry
  or provenance fields, invalid types, unknown variants and mixed explicit/legacy
  non-null encodings reject the proposal. Unrelated outer passthrough fields are
  ignored. Current explicit records and separate legacy records are supported;
  permissive upstream deserialization is not reproduced.
- Legacy tool namespaces classify as tool; a true harness flag classifies as
  harness. Neither produces user-source text. No eligible text yields an error,
  not a fallback to injected or unknown material.

The selected text goes through the existing deterministic greeting-skip/80-character
excerpt function. Its title may still be unhelpful or reveal private information;
normal review remains required. This operation does not create a trust boundary,
verify who typed the text, reconstruct UI visibility or interpret quoted text as
instructions. It does not send content to a model or rename a remote thread.

## Evidence, compatibility and limits

`attribution_context` records the protocol, original SHA, selected archive IDs,
physical line locators and original content indices. Its fixed coverage counts
refer only to extracted user-role messages in the selected raw conversation.
Raw inspection reports `content_attribution_records` as presence only, with a
warning that imports do not filter by labels; presence is not validity or trust.

All selected-conversation raw messages, including assistant/noncandidate messages,
are checked against archived text, role, timestamp and original-export occurrences.
Fallback archive IDs resolve by unique hash/line association, so renaming the source
file can still work. Ambiguous duplicate imports, missing provenance or changed
source bytes reject rather than guessing. The proposal's content fingerprint covers
the entire current archived conversation; normal preview/apply content and revision
checks remain in effect. Attribution context is descriptive and unsigned, and is
not separately authenticated during preview/apply.

The archive and default `suggest-title` behavior are unchanged. This command reads
raw records, including discarded turns; it does not combine attribution with the
separate retained-turn replay grammar. It carries the parser's extraction warnings.
The bounded replay grammar now accepts explicit `history_mode:"legacy"`, matching
Codex's default representation, but still rejects paginated/unresolved inheritance
and unsupported metadata. See the pinned [history-mode definition](https://github.com/openai/codex/blob/f2b94ef8b52196f127d162c6db71e390b9bb265c/codex-rs/protocol/src/protocol.rs).

Older local exports without labels can still use the existing raw excerpt or an
explicit operator title. Web exports retain their existing shape-scoped adapter;
this local attribution schema is not inferred from undocumented web metadata.
