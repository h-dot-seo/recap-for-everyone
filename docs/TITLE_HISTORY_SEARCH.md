# Find a conversation by an earlier local title

After organizing a conversation twice, you may remember its old label rather than
its current one. Default `find` deliberately searches only current display titles
and raw message text. It does not search old manual labels. An explicit option now
includes local title history:

```sh
python recap.py --db ../recap-demo/archive.sqlite find "watering" --source web-demo --include-title-history
```

The standalone equivalent is:

```sh
python conversation_search.py --db ../recap-demo/archive.sqlite "watering" --source web-demo --include-title-history
```

In the 24-conversation synthetic CLI regression, a deferred web conversation is
revisited, given the operator title `Orchard watering comparison`, then deliberately
renamed to `Irrigation shade plan`. Default `find watering` returns no matches
because neither current title nor raw synthetic messages contains that word.
The explicit history search finds the same conversation, shows its **current**
`Irrigation shade plan` title, and separately identifies the prior matching label
and local title revision. No title or state is changed by finding it.

## Search semantics and evidence

The existing literal case-insensitive substring matching remains. Terms are split
on whitespace and AND-connected **across the conversation**. With the option,
terms can be satisfied by different current/past title versions and message bodies.
A result does not claim that one title contained all terms at the same moment.
There is no fuzzy, semantic, chronological/date-range or remote-platform search.

Current-title matches rank first, historical-title matches next, then body-only
matches. Within each category the existing source/conversation ordering is retained.
A conversation appears at most once even when many history records match. Totals
count matching conversations, not matching history events. `limit` still bounds
returned conversations and `truncated` still reports more matching conversations.

Each result retains current title, current title revision and message snippets.
When opted in it also includes:

- `matched_historical_title`: whether any term matched a prior title record.
- `historical_title_match_count`: exact matching record count, not unique names.
- `historical_title_matches`: at most three matching title records.
- `historical_title_matches_truncated`: whether additional matching records exist.

Matching local overrides are sampled newest revision first, followed by the
archived original title if there is room. Each sample identifies its title,
`title_revision` and origin (`prior_local_override` or `archived_original_title`).
The original has revision 0. It is treated as prior only once a local override
exists. The latest override is searched as the current title, not counted again as
a prior override. Repeated/reverted labels can match multiple distinct historical
records. Samples may not show every term's supporting occurrence when capped.

The source filter applies to current and historical titles alike. A database
without title-history tables works as before. An old title record without an
archived conversation cannot create a ghost conversation result.

## Privacy, preservation and cost

**Opting in can display private wording intentionally removed from the current
sidebar title.** It does not redact old labels or classify them as safe. Results
can contain both old titles and message snippets; keep outputs private. The tool
never queries live ChatGPT/Codex titles, uploads data or renames a remote session.
Default searches do not gain historical matching merely because this code exists.

The query uses one SQLite read transaction for message text, current title and
history. A concurrent rename after the snapshot can make the reported current
revision outdated; this is a read-only search result, not an apply lease. Use the
normal fresh preview/apply process for any later explicit title change.

History is merged through an ordered cursor rather than loaded as one Python
collection. At most three history samples and three message snippets per retained
conversation are kept, with three result buckets each bounded by `limit`. Exact
counts require scanning all relevant history and messages; this is not an indexed
historical-title lookup or a constant-time operation. Individual strings can still
be large. No timing benchmark or large-archive speed guarantee is claimed.

All raw messages, original exports, title history and review decisions are preserved.
The command has no restore/undo/delete side effect. Prior titles describe local
archive history, not a verified chronology of remote platform titles.
