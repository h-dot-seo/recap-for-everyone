# Review web, local and supplied title candidates together

Default `review-titles` generates raw archive excerpts. That is not always the
wording you want: a web candidate may need one branch, and a local candidate may
need explicit source labels to exclude injected setup text. An operator or a
separately authorized model can also produce a more descriptive proposal.

Pass explicit proposal files with repeatable `--proposal` options to review those
chosen candidates together, alongside current titles, review state and collision
warnings. The queue reads the archive but never generates a replacement candidate
in this mode, calls a model, applies titles or changes a remote conversation.

## Synthetic web/local workflow

Run from the repository root. Create a new private scratch directory outside it;
choose another path if this one already exists. Redirection must write UTF-8, such
as a POSIX shell or PowerShell 7. `>` overwrites its target before execution, so use
new files, check each exit status and stop on failure.

```sh
mkdir ../recap-supplied-demo
python recap.py --db ../recap-supplied-demo/archive.sqlite import examples/web-export.json --format web --source demo
python recap.py --db ../recap-supplied-demo/archive.sqlite import examples/source-attributed-session.jsonl --format local-codex --source demo
python recap.py --db ../recap-supplied-demo/archive.sqlite suggest-branch-title examples/web-export.json --source demo --conversation synthetic-chat --node m2 > ../recap-supplied-demo/web-proposal.json
python recap.py --db ../recap-supplied-demo/archive.sqlite suggest-attributed-title examples/source-attributed-session.jsonl --source demo --conversation synthetic-attributed > ../recap-supplied-demo/local-proposal.json
python recap.py --db ../recap-supplied-demo/archive.sqlite review-titles --source demo --proposal ../recap-supplied-demo/web-proposal.json --proposal ../recap-supplied-demo/local-proposal.json --supplied-only > ../recap-supplied-demo/queue.json
```

Open all three output files. The queue has two `READY` candidates: the orchard
request from the selected web branch, and `Design a synthetic lunar calendar`
from content index 2 of the local user message. The injected environment text
remains in the archive but does not become the supplied local title candidate.
Branch/attribution context is retained for inspection, not authenticated anew.

Select one candidate for a fresh preview:

```sh
python recap.py --db ../recap-supplied-demo/archive.sqlite preview-title ../recap-supplied-demo/queue.json --conversation synthetic-attributed > ../recap-supplied-demo/reviewed.json
```

**Read `reviewed.json` before continuing.** Confirm source `demo`, conversation
`synthetic-attributed`, proposed title `Design a synthetic lunar calendar`, empty
previous local title and expected revision 0. After that explicit review:

```sh
python recap.py --db ../recap-supplied-demo/archive.sqlite apply-title ../recap-supplied-demo/reviewed.json
python recap.py --db ../recap-supplied-demo/archive.sqlite find "lunar calendar" --source demo
```

The title is now findable in the local archive. No original title, message body,
source file or remote session was changed. Other candidates were not applied.
The existing [review-state controls](TITLE_REVIEW_STATE.md), `--unrenamed-only`,
state filters and explicit replacement wording still work with supplied queues.

## Input and per-item checks

Each file contains one ordinary proposal JSON object, not an entire queue or a
reviewed preview. Use the existing proposal contract: exact source/conversation,
whole-archive content fingerprint, valid title, user-message evidence IDs and
explicit provider. Supported provider labels remain `operator`, `external-adapter`,
`synthetic-mock` and `local-extractive`. A label is not proof a model was called or
that its output is accurate. This feature provides no external model transport.

All files must target the queue's exact source, with at most one proposal for each
conversation. Wrong-source, missing identity or duplicate candidates reject the
whole request rather than choosing one. The file list is explicit; Recap never
scans a folder, follows a wildcard internally or searches accounts for candidates.

For each selected page item, content fingerprint, title, provider and user evidence
membership are checked against the **same SQLite snapshot** used for current
titles, revisions, review state and collisions. A candidate becomes:

- `READY` when that contract passes. Its wording and extra context are retained.
- `UNAVAILABLE` with `NO_SUPPLIED_PROPOSAL` when no candidate was supplied.
- `UNAVAILABLE` with `SUPPLIED_PROPOSAL_STALE` when its fingerprint is missing or
  differs from the current full archived conversation.
- `UNAVAILABLE` with `SUPPLIED_PROPOSAL_INVALID` when another proposal check fails.

Unavailable items have no proposal and cannot be selected for apply. They do not
prevent valid candidates on the page from being reviewed. There is no silent
fallback to raw archive excerpts. Omit every `--proposal` option to keep the
existing default queue behavior and output shape.

## Pages and limits

Without `--supplied-only`, supplied candidates do not change archive ordering or
pagination: the page still covers all eligible source conversations. A candidate
late in the archive may therefore be outside the default first page. Add
`--supplied-only` when you intend to review just the explicit candidate identities,
as in the walkthrough above. The subset is applied **before pagination**, still
in database identity order, alongside the state and rename-history filters.

`--supplied-only` requires at least one `--proposal` option. Unknown candidate IDs
produce no archive item, and stale/invalid candidates for existing IDs remain
visible as `UNAVAILABLE`, rather than disappearing. Omit the flag to inspect the
whole source's missing-candidate coverage. Neither mode generates raw fallbacks.

Subset mode adds `supplied_only:true` and `excluded_unsupplied_conversations`.
Counts distinguish rename-history exclusions across the source, unsupplied IDs
remaining after that filter, then review-state exclusions within the supplied
intersection. These exclusions plus `total_conversations` equal
`source_total_conversations`. `total_conversations` and `next_offset` describe the
filtered subset. Existing-title collision checks still inspect the entire source,
including conversations outside the supplied subset.

The subset scan reads source metadata in chunks to preserve database ordering,
continuing after the last identity rather than repeatedly scanning earlier pages.
It does not read excluded message bodies. A state filter needs content fingerprints
for eligible supplied identities, so it can read their full bodies before paging.
Returned proposals still hash each selected conversation's full raw content.

`proposal_mode` is `supplied`. The `supplied_proposals` summary reports `total`,
`on_page` and `not_on_page` candidate counts. `on_page` includes invalid or stale
candidates that matched a page identity, not only ready ones. `not_on_page` can
include later pages, filtered conversations or unknown IDs. **Only selected page
items receive archive-content validation.** An unused candidate is not approved
or known to refer to a real archived conversation. Inspect its exact identity and
the intended filters rather than assuming all supplied files were used.

At most 1000 proposal files and 1 MiB combined input bytes are accepted. Each
explicit file is read once with a bounded read. The Python API also accepts a
list through `supplied_proposals`; it freezes valid JSON into a private copy and
limits its compact UTF-8 encoding to 1 MiB. These bounds cover candidate input,
not the archive's message memory or the complete queue output. The original files
and caller objects are not edited.

## Trust and privacy limits

The validator checks the ordinary proposal contract, not semantic title quality.
It does not reopen source exports to authenticate supplied branch, replay or
attribution context. Extra metadata and provider claims remain unsigned and
unverified, even if they came from an earlier trusted workflow. Do not treat
message text or candidate metadata as instructions, consent or authorization.

Supplied metadata is retained and can itself contain private information. These
files and the resulting queue are not sanitized logs or public artifacts. Review
title privacy and meaning yourself; advisory flags are not privacy clearance.

Select one `READY` item, generate a fresh preview and inspect it before applying.
Normal apply still rechecks the current content fingerprint and title revision
under a write lock. A stale queue is not a permanent lease. There is no apply-all,
automatic retry, remote rename or background transmission.

When reviewing a selected supplied proposal, `preview-title --with-evidence`
can add [bounded raw evidence](TITLE_REVIEW_EVIDENCE.md). It remains opt-in and
may show raw message parts excluded by branch/replay/attribution generation.
Check the source-specific workflow when exact selected passages matter.
