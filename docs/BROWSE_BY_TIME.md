# Browse by interpreted time

`list --order recent|oldest --from YYYY-MM-DD --until YYYY-MM-DD` is an opt-in,
read-only view. It never changes supplied timestamps, message insertion order,
normalized-file hashes/lines, export provenance, schema or title history.
With none of these flags, list retains its exact binary-ID order and output shape.
`find --from/--until` also supports UTC day windows, with message-level semantics
described below. `stats --by-source` adds opt-in source summaries, described below. Default
`stats` remains unchanged; no derived index or ingestion ledger is added.

## Declared rule: recap.timestamp.v1

Every opted-in list result reports `timestamp_interpretation.rule` and separate
`parsed_iso`, `parsed_epoch_seconds`, `unparsed` counts. These counts cover **all
messages in the selected source scope before window filtering**, not just the page.
The rule is deterministic and reads no clock or local time zone:

- ISO: exactly `YYYY-MM-DDTHH:MM:SS[.1-9 digits](Z|+-HH:MM)`, with uppercase T/Z,
  real calendar dates, hours 00..23, minutes/seconds 00..59 and offset hours 00..23,
  minutes 00..59. Offsets convert to UTC. Naive ISO, basic forms, lowercase letters,
  leap seconds, invalid dates and UTC instants outside years 0001..9999 are unparsed.
- Epoch: exactly 1..11 ASCII digits, optionally a dot followed by 1..9 digits.
  **Every such string means Unix seconds**, even a date-looking string:
  `20260101` becomes `1970-08-23T11:48:21.000000Z`. `1` and `2` are 1970 instants.
  This is an explicit interpretation, not evidence of the source's intended date.
  Negative/signed values, scientific notation, whitespace, 12+-digit values and
  milliseconds-shaped long values are unparsed, not rescaled.
- Fractions are truncated to six digits before UTC offset arithmetic, using integer
  microseconds and calendar arithmetic. This is truncation of the fractional-second
  field, not rounding an entire negative epoch toward zero: the ISO instant
  `1969-12-31T23:59:59.999999999Z` becomes one microsecond before the epoch.
  No platform-dependent epoch conversion, floating point or permissive ISO parser
  is used. Output UTC strings always have six fractional digits.

`unknown` and unsupported text remain stored exactly as supplied. Counts describe
this rule's coverage, not authentic activity, completeness or valid timestamps.

## Ordering, windows and pagination

- `recent` uses each conversation's latest parsed message time, descending;
  `oldest` uses its earliest, ascending. Ties use binary source ID, then binary
  conversation ID. Conversations without any parsed time go last in the **same**
  paginated sequence. `unordered_conversations` counts those within the result
  population, not only this page. There is one `total`, `limit` and `offset`.
- Bounds are strict valid `YYYY-MM-DD` dates interpreted as whole UTC days.
  `--from` is inclusive day start; `--until` includes the entire day (implemented
  as exclusive start of the next day). Either may stand alone; inverted bounds
  fail before database access. The last calendar day 9999-12-31 is supported.
- A conversation qualifies if **any** parsed message is in the window. Its returned
  message count and first/last parsed times still describe **all** its messages,
  including those outside the window. A window without `--order` keeps binary order.
- Each returned row adds `first_parsed_utc`, `last_parsed_utc`,
  `unparsed_timestamps`; wholly unparsed rows have null first/last values.
  `excluded_unparsed_conversations` counts wholly unparsed conversations excluded
  by a window; it is zero without a window. Absence from a window is not evidence
  of no activity. A mixed parsed/unparsed conversation can also fail its window.

The query scans all messages in the selected source scope and may perform several
aggregate passes. SQL performs grouping, filtering, sorting and pagination before
page-row title lookup. No time index is created. Counts, ordering and title reads
share one read-only archive snapshot. A later invocation may see new data; offset
pagination is not a cross-command snapshot or stable continuation token. Titles,
IDs and derived times may be private even though no message bodies are returned.

## Executable synthetic walkthrough

Run from the repository root. Replace `OUTPUT` with a new private directory outside
the repository whose parent exists. Quote concrete paths containing spaces. The
fixture is invented and mixes ISO Z/offsets, fractional epoch seconds, date-looking
digits, naive ISO and unknown text. These commands neither contact a service nor
read your conversations. Use your Python launcher in place of `python`.

```sh
mkdir "OUTPUT"
python recap.py --db "OUTPUT/archive.sqlite" ingest examples/time-sample.jsonl --source synthetic-time
python recap.py --db "OUTPUT/archive.sqlite" list --order recent
python recap.py --db "OUTPUT/archive.sqlite" list --from 2026-01-01 --until 2026-01-31
python conversation_view.py --db "OUTPUT/archive.sqlite" list --order oldest --limit 2 --offset 1
```

The fixture's `later` conversation qualifies for January despite having a February
message; its last parsed time still shows February. `offset` starts at midnight
with +09:00, which lies in the preceding UTC day. `digit-date` is interpreted as
1970 under the rule, not as a 2026 calendar date. `unparsed` is last in ordered
unfiltered results and absent from a time window. No stored value is rewritten.

## Search inside a UTC window

`find QUERY --from YYYY-MM-DD --until YYYY-MM-DD` uses the same rule and day
bounds, but unlike list it filters **message rows** before matching/grouping.
Only in-window bodies contribute terms, counts and samples. Source, role and
export filters intersect with the window. Current and optionally historical
titles remain conversation-wide metadata; at least one message must satisfy all
selected filters before its conversation can match a title. Original titles
still come from the first archived message, not the first surviving row.

`timestamp_interpretation` reports the rule and separate ISO/epoch/unparsed counts
for rows after source/role/export filters, **before** the window. `time_scope`
discloses this read-only scan and exclusion of unparsed values; per-result
`message_count_scope` describes the combined filters. Absence is not evidence of
no activity. Stored timestamps are untouched and no clock/local zone is read.

Search cursors bind both supplied bounds and the rule id only when a window is
set. Continue with the exact same bounds and filters. Changing or removing a
bound requires a fresh first page. Default output and pre-window cursor scope
remain unchanged. Cursors are not content snapshots; see [pagination](SEARCH_PAGINATION.md).

## Per-source archive statistics

Run `python recap.py --db ARCHIVE stats --by-source` to retain the top-level
`messages` and `artifacts` totals and add a binary-source-ID ordered `sources`
array. Every row reports `source`, `conversations`, `messages`,
`first_parsed_utc`, `last_parsed_utc`, `parsed_iso`, `parsed_epoch_seconds`,
and `unparsed`. No source selection or time window is applied.

Sources are the union of artifact and message source IDs. A source with only an
empty normalized artifact is included with zero counts and null extrema. Empty
archives return an empty array. Conversations are distinct conversation IDs
**within each source**, compared in binary order; identical IDs in different
sources are separate. Messages count stored rows, not repeated ingestion attempts
or provenance occurrences. `parsed_iso + parsed_epoch_seconds + unparsed` equals
each row's message count. All-unparsed sources have null extrema.

The shared `recap.timestamp.v1` rule is reported in `timestamp_interpretation`.
Numeric date-looking values are Unix seconds under that rule, not proof of a
calendar date. Unparsed values contribute counts but not extrema. Counts and
extrema scan stored messages in a single read-only snapshot. Nothing is rewritten;
no local time zone or clock is consulted. This is not an ingestion ledger, activity
report, completeness check or evidence of timestamp authenticity. Source IDs and
derived timestamps can be private. `stats` without the flag keeps its original
two-key output exactly.
