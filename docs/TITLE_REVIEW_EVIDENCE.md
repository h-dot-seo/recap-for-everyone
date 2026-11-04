# Read the evidence before choosing a title

An evidence ID tells you which archived user message a proposal cites, but does
not show whether the title is useful or accurate. Add `--with-evidence` when you
want a small amount of raw evidence directly in the private preview:

```sh
python recap.py --db ../recap-demo/archive.sqlite preview-title ../recap-demo/web-proposal.json --with-evidence > ../recap-demo/web-reviewed.json
```

Use the existing [web/local walkthrough](TITLE_WALKTHROUGH.md) to create the
archive and proposal first. The standalone equivalent is:

```sh
python title_proposal.py --db ../recap-demo/archive.sqlite preview ../recap-demo/web-proposal.json --with-evidence
```

The flag also works when selecting one queue item with `--conversation`, or using
explicit replacement wording with `--title`. It is a **preview-only** option, not
an apply command. Python callers use
`preview(db, proposal, replacement_title=None, with_evidence=True)`; the option must
be a boolean. The default is false and retains the existing output structure.
Default previews add no message-body excerpts, although caller-supplied proposal
metadata may itself already contain private text.

## What is shown

The separate `review_evidence` object contains:

- Up to **five distinct cited user messages**, in first appearance order in the
  proposal's `evidence_message_ids`. Repeated IDs do not consume extra slots.
- An unchanged prefix of up to **2,000 Unicode code points** per message as
  `text_excerpt`, with `excerpt_start`, `excerpt_end`, `text_characters` and
  `text_truncated`. Offsets are zero-based and half-open, not byte or UTF-16 units.
- The message ID, role, normalized-artifact SHA-256 and source line.
- Up to three original-export provenance occurrences per selected message,
  ordered by original hash, locator and parent. The legacy/additive ledger union
  removes duplicate occurrences. Exact `export_provenance_count` and
  `export_provenance_truncated` show whether more exist. Normalized-only archives
  have an empty provenance list, rather than an invented original-export source.
- Total references, distinct messages, duplicate references, returned messages
  and omitted messages. The full raw-content fingerprint identifies the validated
  archive evidence, not just these visible excerpts.

Only cited messages appear. Adjacent assistant/system messages, uncited users and
other conversations or sources are not added. All evidence IDs are validated
before sampling; an invalid or stale ID does not become a silently omitted item.
Inspect the counts and flags before concluding that you have seen enough.

For complete archived text and all recorded occurrences, use the existing exact
message view with the returned source, conversation and message identity. In the
shipped synthetic example:

```sh
python recap.py --db ../recap-demo/archive.sqlite show --source web-demo --conversation synthetic-chat --message m1
```

Use your actual explicitly selected source, not the example's. See
[message selection](MESSAGE_SELECTION.md). No generated shell commands are built
from arbitrary IDs. Full message views can contain much more private information.

## Raw evidence is not the selected generation passage

These are **raw archived message prefixes**, even when a proposal was generated
from a selected web branch, retained local turns or attributed user content.
A raw user-role message can contain harness material or other parts excluded from
the generator's evidence selection. A useful selected passage may also be beyond
the prefix limit. A source-attributed proposal is therefore not proof that every
character in this raw preview was authored by the user.

The view does not reconstruct source branches, replay history or content-part
attribution, and does not trust caller-supplied context to select or fabricate a
verified passage. Follow the specific source workflow when that distinction
matters. Source labels, generation metadata and the displayed evidence remain
descriptive and unsigned. A citation or fingerprint cannot prove semantic support.

## Review remains explicit

Read the proposed title, current title, evidence, omissions and advisory flags.
If wording needs changing, create a fresh preview with `--title` and review it.
Do not apply just because the command succeeded or the excerpt looks plausible.

Only after reviewing the saved file, use the existing separate command:

```sh
python recap.py --db ../recap-demo/archive.sqlite apply-title ../recap-demo/web-reviewed.json
```

The additional evidence display does not add authority or bypass checks. Apply
still checks the actual proposal's user IDs, whole raw-content hash and expected
title revision, including the final locked stale-write check. Editable evidence
and advisory fields are not signatures or approval tokens. Preview itself changes
no titles, database records, original files, permissions or remote services.

## Snapshot and privacy boundaries

Preview now reads the content fingerprint, current title/revision and optional
evidence/provenance through one SQLite read transaction. A concurrent import or
title change does not mix old evidence with a new title within that preview.
Separate previews can observe newer state, and a saved preview may become stale.
The existing detached-input rules for Python callers still apply.

The body budget is at most 10,000 code points, **not a total JSON-byte or memory
limit**. Existing proposal metadata, identifiers and provenance locator strings
are not length-bounded by this option. Fingerprinting still reads the full selected
conversation, and counting provenance can inspect more rows than are displayed.
No claim of constant memory or bounded database work is made.

Saved previews with evidence contain more private data. Keep them outside this
repository, inspect them before any sharing, and do not assume Unicode escaping
or advisory flags redact anything. There is no model call, upload, privacy
clearance, semantic validation or automatic title application.
