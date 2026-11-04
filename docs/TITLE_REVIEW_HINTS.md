# Title review hints and explicit wording changes

A useful title must be readable, distinctive and appropriate to display in a
sidebar or search result. Recap cannot certify those properties. It can provide
small deterministic **advisory checks** while you decide what to keep.

The `title` command's informational `suggested_title` and ordinary `suggest-title`
use the same local excerpt rules: skip usable greeting-only messages when a later
user request exists, clean whitespace/control characters, then limit to 80 code
points. The original messages are unchanged. With no usable user evidence,
`title` still lets you inspect/revise the current title and reports the placeholder
`Untitled conversation`; `suggest-title` instead rejects rather than inventing
evidence. A placeholder is not an approved proposal or an automatic rename.
This raw-content rule does not select a web branch, retained turns or source labels.
Those remain separate opt-in workflows.

Every `READY` item from `review-titles` and every title `preview` now includes a
`title_advisory` object. This is computed locally from the proposed title only.
No model, external service, source-message scan or additional database write is
performed by the assessment.

## Choose a more informative user message

The first non-greeting request can still be generic, such as `Can you help with
my project?`, while a later request names the actual subject. Recap does not infer
which topic matters most. After inspecting the conversation, use an exact archived
user-message ID to generate an excerpt from that message only:

```sh
mkdir ../recap-title-focus-demo
python recap.py --db ../recap-title-focus-demo/archive.sqlite import examples/title-focus-web.json --format web --source demo
python recap.py --db ../recap-title-focus-demo/archive.sqlite find irrigation --source demo
python recap.py --db ../recap-title-focus-demo/archive.sqlite show --source demo --conversation synthetic-title-focus --message u2
python recap.py --db ../recap-title-focus-demo/archive.sqlite suggest-title --source demo --conversation synthetic-title-focus --message u2 > ../recap-title-focus-demo/proposal.json
python recap.py --db ../recap-title-focus-demo/archive.sqlite preview-title ../recap-title-focus-demo/proposal.json --with-evidence > ../recap-title-focus-demo/reviewed.json
```

Choose a new private scratch directory outside this repository; do not overwrite
existing files. Keep saved JSON as UTF-8, following [the walkthrough's shell
guidance](TITLE_WALKTHROUGH.md). Read the proposal and complete reviewed document
before deciding to apply. This example's title is `Compare synthetic orchard
irrigation schedules`, with evidence `u2`, rather than the generic first request.
The source bytes, original title and archive messages remain unchanged.

Only after explicitly reviewing the result, apply the conversation-wide local
display title with the existing checked operation:

```sh
python recap.py --db ../recap-title-focus-demo/archive.sqlite apply-title ../recap-title-focus-demo/reviewed.json
```

The standalone equivalent is `title_suggestion.py --db DB --source SOURCE
--conversation CONVERSATION --message ID`; the Python API appends
`message_id=None` to `suggest(db, source, conversation)`. Omission preserves
the earlier proposal shape and first-non-greeting behavior. To use this candidate
in a queue, pass its saved file to `review-titles --proposal FILE`, optionally
with `--supplied-only`. Ordinary queues still generate their default raw excerpts.

Selection is exact within the specified source and conversation, not a substring,
title, source line, Unicode-normalized ID or automatic search choice. A missing
ID, assistant/system/tool message or unusable selected prefix fails without
falling back to another message. A selected greeting is still allowed and receives
the existing greeting-fallback hint: that describes the excerpt rule applied to
the **one selected message**, not substitution of a different message. The new
`evidence_selection` object identifies the explicit raw-message choice. These
descriptive fields are unsigned and do not prove human authorship or approval.

The same whitespace/control cleanup, evidence ID and 80-code-point cap apply.
No later sentence or substring is invented if the selected prefix is unhelpful.
Use explicit replacement wording at preview when needed. The proposal retains
the fingerprint of **all messages in this archived conversation**, not only the
selected one: an import changing other conversation content still makes it stale.
Generating and previewing remain read-only; title revision checks still run at
apply. Selection reads the full content snapshot, so it is not a bounded-memory
or private-text minimization option.

This works on messages imported from web, local, local-codex or normalized JSONL,
but it does not re-read or verify an original export. An archived `user` role is
not proof that every part was human-authored. A selected message may belong to an
alternate web branch, discarded local turn or contain harness text. Use the
separate verified branch/replay/source-attributed workflows when those scopes
matter; do not treat this flag as equivalent. No model, remote rename, automatic
relevance score or approval is added. Review before sharing: IDs, text and titles
can be private.

## Unicode excerpt boundaries

Greeting-only detection uses NFC on the comparison key before case folding and
the existing punctuation trimming. For example, a decomposed `안녕하세요!` is
recognized like its composed spelling, so a later useful user request can supply
the title and its own evidence ID. This is a small fixed greeting list, not a
language detector or meaning classifier. Full-width/compatibility spellings and
other unlisted greetings are not added through NFKC normalization. Canonical
equivalence and NFC are defined in the [Unicode normalization specification](https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/).

Only comparison is normalized. A selected decomposed request or greeting fallback
retains its decomposed spelling in the label. Original message text, source bytes,
IDs, provenance and the raw-content fingerprint remain untouched.

Whitespace cleanup preserves U+200C ZERO WIDTH NON-JOINER and U+200D ZERO WIDTH
JOINER instead of replacing them with spaces. These characters affect [text
shaping](https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-23/), and ZWJ can join
parts of an [emoji sequence](https://www.unicode.org/reports/tr51/tr51-27.html).
For example, a short `Synthetic 👩‍🔬 field study` label keeps its joiner. Other
Cc/Cf characters, including bidi controls, zero-width spaces and emoji tags, still
become spaces. This narrow exception is not full Unicode/emoji preservation or
validation of joiner placement. It can retain confusing or inappropriate joiners.
The existing `FORMAT_CHARACTERS_PRESENT` review hint still reports them.

The 80-code-point cap is unchanged. It can cut inside a combining or emoji sequence,
including immediately after a joiner. There is no grapheme segmentation, font check
or rendering guarantee. Usability now requires an alphanumeric code point inside
the actual cleaned 80-code-point prefix, not merely somewhere later in the full
message. A prefix containing only retained joiners, punctuation, combining marks
or non-alphanumeric emoji is skipped in favor of a later usable user message.
If none exists, generation fails rather than suggesting an invisible/non-word label
or inventing a later excerpt. Controls removed by cleanup do not consume the cap.
Review awkward cuts and use explicit replacement wording when necessary.

Raw suggestions, informational `title` suggestions, review queues, verified
web-branch/local-replay/source-attributed excerpts and the offline local adapter
all use this shared rule after their own evidence selection. It does not broaden
any scope, confer approval or change title validation. Saved proposals and prior
titles are not rewritten or invalidated merely because the generator changed;
fresh generation can choose a different evidence message or wording, which must
still be reviewed before application.

## What the hints mean

- `character_count`: Unicode code points, not visible width, words or grapheme
  clusters. The validator's maximum is 200; the local excerpt generator uses 80.
- `OVER_LOCAL_EXCERPT_LENGTH`: wording exceeds the local generator's 80-code-point
  length. This is permitted up to 200, not an error or quality score.
- `REPORTED_TRUNCATION` / `REPORTED_GREETING_FALLBACK`: the proposal's generation
  metadata reports truncation or greeting fallback. This metadata is unverified
  and caller-editable; the hints do not reconstruct how wording was generated.
- `EMAIL_LIKE`, `URL_LIKE`, `LONG_DIGIT_SEQUENCE`, `LONG_IDENTIFIER_LIKE`: simple
  patterns that may deserve a privacy review. A date, harmless URL, ordinary long
  word or public identifier can trigger a false positive.
- `FORMAT_CHARACTERS_PRESENT`: invisible Unicode formatting characters appear in
  the proposed title. This does not identify their intent.

For pattern detection only, Unicode NFKC normalization is applied and format
characters are removed. Neither the proposal nor source text is rewritten.
The assessment returns **categories, never matched substrings**. The surrounding
proposal/queue still contains its original title and therefore may itself be
private. Collision warnings remain separate and advisory as described in
[the review queue guide](TITLE_REVIEW_QUEUE.md).

**No flags does not mean safe.** These patterns do not comprehensively identify
names, addresses, health/financial information, credentials or other private data.
No sensitive attribute is inferred, no redaction is done, and no semantic quality
score or privacy clearance is produced. Inspect the title yourself. Flags neither
automatically block nor authorize applying it. This is not a DLP/security product.

## Use your own title before applying

If an otherwise valid proposal is too vague, duplicates another title, includes
unwanted details or was truncated awkwardly, provide your own wording during the
fresh preview step:

```sh
python recap.py --db ../recap-demo/archive.sqlite preview-title ../recap-demo/queue.json --conversation synthetic-chat --title "Synthetic orchard experiment plan" > ../recap-demo/reviewed.json
```

For a single proposal JSON, omit `--conversation`. The standalone equivalent is:

```sh
python title_proposal.py --db ../recap-demo/archive.sqlite preview ../recap-demo/proposal.json --title "Synthetic orchard experiment plan"
```

Use the private UTF-8 scratch-directory guidance from the walkthrough. Shell
arguments can appear in shell history/process listings, so do not type secrets
as replacement titles. The original proposal must still pass identity, provider,
title, evidence and content-fingerprint validation; replacement cannot rescue a
stale or invalid proposal by bypassing those checks.

A replacement becomes a new **`operator` proposal**. It preserves only the checked
source, conversation, full raw-content hash and copied evidence IDs, plus your
replacement title. Old extraction/model/branch/projection metadata is omitted so
human wording is not misattributed to a generator. The source excerpt and original
proposal file are not modified. The new title receives its own advisory checks.

Read the full preview, current title and expected revision before applying:

```sh
python recap.py --db ../recap-demo/archive.sqlite apply-title ../recap-demo/reviewed.json
```

The replacement is **not verified to summarize the evidence accurately**. Evidence
IDs bind the selected conversation, not the meaning of arbitrary human wording.
Current full-content and revision checks still apply. No bulk apply, automatic
suffixing, remote rename, provider connection or transmission is added.

Preview advisory fields are unsigned display information, not authorization or
policy enforcement. Apply performs the existing proposal checks again but does
not enforce advisory flags. Do not edit a reviewed document to work around a
failure: generate a fresh preview and inspect it. Existing callers that do not
supply `--title` keep the original proposal unchanged.

## Independent input snapshots for Python callers

`preview(db, proposal)` takes its own JSON value snapshot before reading the
archive. The returned proposal, evidence-ID list and nested descriptive metadata
no longer share mutable objects with the caller. Changing the original proposal
after preview does not silently change an already returned review or leave its
advisory describing different wording. Explicit replacement titles still produce
operator wording and discard old generation metadata as described above.

`apply_preview(db, reviewed)` also takes its own JSON snapshot before revalidation
and uses that same detached value through the checked title write. Changes to the
caller's object after that copy cannot substitute a title, evidence list or
revision between validation and writing. Callers should still avoid mutating an
object while its initial copy is being serialized; this is not a shared-object
thread synchronization API. Ordinary CLI file round-trips retain their existing
proposal/preview structure and behavior.

All retained API document data must be finite JSON values. Cycles, unsupported
Python objects, nonfinite numbers and unpaired surrogates fail before archive
reads or title writes, even in unused metadata. Excessively nested title files
fail cleanly in both CLI entry points. This does not add a file-size limit or
change other commands' input contracts.

Snapshot identities must be nonempty strings: a numeric or boolean ID cannot
select a text ID through SQLite's implicit type conversion. Source names must
also contain a non-whitespace character. Literal accepted strings are preserved,
including Unicode, quotation marks and meaningful padding; no normalization is
used to redirect a proposal to another identity.

These are consistency and safe-failure checks, not signing or authentication.
Returned JSON remains editable and unsigned, advisory fields are still descriptive,
and a saved file is not proof of human approval. Inspect the complete current
preview and use a fresh preview for changed wording. Transactional content-hash
and revision checks remain the final stale-write protection; no title is changed
by preview, and no remote service is contacted.

For optional raw user-message excerpts beside the title, use
[`preview-title --with-evidence`](TITLE_REVIEW_EVIDENCE.md). The added view is
bounded and private, comes from the same archive snapshot as the title revision,
and does not make the title semantically verified or approved.
