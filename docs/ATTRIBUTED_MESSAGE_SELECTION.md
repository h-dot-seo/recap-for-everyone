# Choose a specific source-labeled request

A local conversation can start with a user-labeled but generic request such as
`Can you help with my project?`, then name the useful topic later. The default
source-attributed excerpt stops at that first non-greeting request. Use an exact
archived message ID to choose a later request without including its harness or
unknown-source parts in the proposed title.

This adds selection to the existing [source-attributed title contract](SOURCE_ATTRIBUTED_TITLES.md),
not new attribution formats or verified human authorship. The source is still one
explicit local-codex JSONL export. Producer labels remain unsigned and the command
does not reconstruct retained turns, call a model or rename a live thread.

## Select a later request

Use the shipped synthetic example and a new private directory outside this
repository. Choose another directory if it already exists. The fixture has six
records, five extracted message occurrences and four distinct archived messages.
The final two occurrences share an identical raw message ID/text but label different
content positions as user text. They are intentionally not combined for attribution.

```sh
mkdir ../recap-attributed-focus-demo
python recap.py --db ../recap-attributed-focus-demo/archive.sqlite import examples/title-focus-attributed.jsonl --format local-codex --source demo
python recap.py --db ../recap-attributed-focus-demo/archive.sqlite show --source demo --conversation synthetic-attributed-focus --message focus-user
python recap.py --db ../recap-attributed-focus-demo/archive.sqlite suggest-attributed-title examples/title-focus-attributed.jsonl --source demo --conversation synthetic-attributed-focus --message focus-user --output ../recap-attributed-focus-demo/proposal.json
python recap.py --db ../recap-attributed-focus-demo/archive.sqlite preview-title ../recap-attributed-focus-demo/proposal.json --with-evidence --output ../recap-attributed-focus-demo/reviewed.json
```

Read the actual UTF-8 proposal and reviewed document. The title is
`Compare synthetic orchard irrigation designs`, with archive ID `focus-user`,
`line:3` and zero-based content index `1`. `Synthetic runtime instructions` remains
in the raw archive and is not part of this title evidence. Preview's evidence
excerpts show **raw archived message text**, so they can include those excluded
parts. The `attribution_context.evidence_parts` identifies the selected positions;
a raw preview excerpt is not a separately filtered or authenticated attribution view.

Check the source, conversation, chosen occurrence, proposed and previous titles,
content hash and expected revision. A `SAVED` receipt is not the saved document or
approval. Only after reviewing that document, explicitly apply the local title:

```sh
python recap.py --db ../recap-attributed-focus-demo/archive.sqlite apply-title ../recap-attributed-focus-demo/reviewed.json
python recap.py --db ../recap-attributed-focus-demo/archive.sqlite find "orchard irrigation" --source demo
```

The source bytes, complete raw messages and provenance remain unchanged. Titles
change only in this archive. All saved output filenames must be new.

## Disambiguate repeated source occurrences

An archive message can be associated with more than one physical occurrence in
the same export. Identical raw text can have different producer-attributed parts.
If `--message` matches multiple eligible occurrences, the command rejects rather
than picking the first, merging their labels or deciding that equal excerpts make
them equivalent. Use the exact `line:N` locator from the supplied source/provenance:

```sh
python recap.py --db ../recap-attributed-focus-demo/archive.sqlite show --source demo --conversation synthetic-attributed-focus --message repeated-user
python recap.py --db ../recap-attributed-focus-demo/archive.sqlite suggest-attributed-title examples/title-focus-attributed.jsonl --source demo --conversation synthetic-attributed-focus --message repeated-user --origin-locator line:6 --output ../recap-attributed-focus-demo/occurrence-proposal.json
python recap.py --db ../recap-attributed-focus-demo/archive.sqlite preview-title ../recap-attributed-focus-demo/occurrence-proposal.json --with-evidence --output ../recap-attributed-focus-demo/occurrence-reviewed.json
```

The repeated message's raw body has both requests. At `line:5`, only content index
`0` is labeled user text. At `line:6`, only index `1` is, yielding
`Choose synthetic orchard watering sensors`. `--message repeated-user` without a
locator rejects. Supplying `line:6` with a different message ID also rejects.
The new proposal does not apply itself. Review its saved preview before any later
explicit apply; the earlier displayed title stays in effect until then.

## Exact selection, validation and compatibility

Both unified and standalone commands accept `--message ID` and optional
`--origin-locator line:N`. The Python API appends `message_id=None,
origin_locator=None` to `suggest_attributed(db, source, conversation, path)`.
No-option behavior and proposal shape remain unchanged. Existing queues and model
context builders keep their current default selection; they do not pick an
occurrence automatically. A deliberately saved proposal can use the existing
supplied-proposal review workflow.

- A locator requires a message ID. It must be exactly `line:` followed by a positive
  ASCII decimal integer, without leading zeros, signs or whitespace. It is a
  one-based physical line, including blank lines, not a message ordinal or content
  index. Invalid selector argument shapes fail before source/database access.
- Use the exact **archived** ID, not a guessed ID for a renamed file, title or search
  substring. An ID-less export renamed without changing its bytes can resolve its
  original archive ID through the existing hash/line provenance check.
- Selection narrows eligible nonblank user-labeled text occurrences in the chosen
  source/conversation. Assistant, missing, outside-conversation, unlabeled, wholly
  excluded and empty-attributed-text selections reject. Exactly one eligible
  occurrence must remain. Repeated raw occurrences without eligible text do not
  create candidate ambiguity, but are still source-verified.
- Normal source parsing, attribution validation and **all selected-conversation
  raw message** provenance/content checks run before this narrowing. Selection
  cannot hide malformed other user attribution, missing assistant provenance,
  changed source bytes or ambiguous archive associations. It does not newly
  validate attribution on skipped roles or other conversations.
- The chosen occurrence uses the same whitespace/control cleanup, greeting hint
  and 80-code-point excerpt cap. A greeting is allowed; an unusable prefix rejects
  without substituting another occurrence. The cap can split grapheme clusters.
  No semantic relevance check or automatic wording improvement is performed.

The new top-level `evidence_selection` records the resolved archived ID and exact
locator, with mode `explicit_source_attributed_occurrence`. Existing
`attribution_context.evidence_parts` narrows to the chosen occurrence, while its
coverage still describes all extracted user-role messages in the selected raw
conversation. The original whole-file hash, extraction warnings and fingerprint of
**the complete current archived conversation** are preserved. Unselected archive
content changes still stale a preview, and title revision checks still apply.

Generating and previewing are read-only against the archive; `--output` explicitly
writes only the requested new local document. Source verification is at generation
time, not a new live source-file lease at apply time. Selection/context fields are
unsigned descriptive metadata, not independently authenticated by preview/apply
and not an approval token. Keep source files, IDs, messages and titles private as
needed. This selection reduces candidate scope, not the amount of source data read
or a guaranteed memory/byte bound.
