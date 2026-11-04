# Search excerpts that point to the evidence

`recap.py find` and `conversation_search.py` now show up to 240 Unicode code points
around the first matching term in each sampled message, rather than always showing
its beginning. This helps locate a request or decision near the end of a long
web conversation or local session message.

```sh
python recap.py --db ../archive.sqlite find "orchard"
```

Each entry in `message_matches` retains its message identity and source hash/line.
When searching with `--export-sha256`, original-export provenance remains included.
Additional fields describe the exact excerpt:

- `snippet`: an unchanged slice of the archived message, preserving whitespace,
  capitalization and original Unicode characters. No ellipsis is inserted.
- `snippet_start` / `snippet_end`: zero-based, half-open offsets into the original
  message text, measured in Unicode code points, not bytes or UTF-16 code units.
- `snippet_truncated_before` / `snippet_truncated_after`: whether text was omitted
  on that side of the excerpt.
- `first_match`: the case-folded query `term`, its original-text `start` / `end`
  offsets and `fully_visible`. A term longer than the excerpt can be only partly
  visible; its full original-text span is still reported.

For example, searching `STRASSE` matches the original `Straße`. The reported span
covers the six original characters, not the seven characters in its case-folded
representation. A query matching part of an expanded character still points to
that whole original character. Korean and emoji use the same code-point offsets.
By default, combining sequences are not normalized: search retains its existing
case-folded literal-substring semantics. Opt-in [canonical Unicode search](CANONICAL_UNICODE_SEARCH.md)
equates normalization forms and reports original covering offsets, including
composition and reordering caveats.

The earliest match in source order is used, regardless of query term order. Up to
60 characters of leading context are included when the full match fits. Excerpts
remain bounded to 240 code points, and at most three matching messages per
conversation are sampled. A sample does not prove that all query terms occur in
that excerpt: AND matching still spans the current title and all selected messages
(and historical titles only when explicitly requested).

Title-only matches produce no invented message excerpt. Ranking, exact conversation
match totals, source/export filters and history opt-in are unchanged. These are
read-only views of one archive snapshot. Original exports, archived text, titles
and provenance are not rewritten.

## Diverse bounded body samples

When more than three messages match, search now prefers a bounded sample that
covers more distinct query terms instead of always keeping the first three hits.
For example, if several early messages contain `orchard` and a later message
contains `rainfall`, a search for `orchard rainfall` can retain the later evidence
rather than returning three redundant `orchard` samples.

Each matching conversation includes:

- `message_match_count`: the exact number of eligible message bodies matching at
  least one query term, before sampling.
- `message_matches_truncated`: whether some matching bodies were omitted.
- `message_term_coverage.matched_terms`: distinct case-folded query terms found
  anywhere in the eligible message bodies, in query order.
- `sampled_terms`: those terms found in the complete selected message bodies.
- `unsampled_terms`: matching body terms absent from the selected bodies.
- `all_matched_terms_sampled`: whether the selected bodies cover all body-matched
  terms. It is true with empty lists when there are no matching bodies.

These counts and coverage fields describe **message bodies only**. Terms supplied
by a current or opted-in historical title do not create body evidence. With
`--export-sha256`, only bodies associated with that export contribute to these
fields. Repeated query terms do not receive additional sample weight.

The streaming selector retains at most three samples. It replaces a sample when
the incoming body improves their combined distinct-term coverage, or improves
summed per-body coverage without losing combined coverage. Equal scores retain
earlier messages, and selected records remain in archive insertion order. The
selector does not retain every matching body and does not guarantee the globally
best combination or semantic relevance. Conversation ranking is unchanged.

Coverage describes full selected bodies, not just their 240-code-point excerpts.
A term far from the first match in the same body may still fall outside the visible
excerpt. Use [exact message selection](MESSAGE_SELECTION.md) to read the complete
selected evidence. More than three separate messages may be necessary to show
all matching terms; `unsampled_terms` makes that limitation explicit.

Excerpt/provenance details are fetched only when an incoming body enters the
retained sample. A retained body may later be replaced, so a streaming search can
perform more than three such fetches even though at most three samples are returned.

To continue past a truncated set of conversations, use [search pagination](SEARCH_PAGINATION.md).
Each page preserves these excerpt and coverage rules. Pagination order consistency
is separate from evidence freshness and title approval.

## Read matching messages that were not sampled

`next_cursor` continues conversations, not the omitted messages indicated by
`message_matches_truncated`. It can be null while many matching bodies remain
unsampled. A larger `find --limit` also does not raise the three-message sample cap.
Use scoped `show --limit ... --offset ...` pages and follow `selection.next_offset`
to read the remaining raw conversation, then choose useful user evidence explicitly.
[The synthetic later-message walkthrough](OMITTED_SEARCH_MESSAGES.md) demonstrates
assistant-only search samples, four existing message pages, and a reviewed title
from the later user request. Paging is not restricted to matching messages or a
verified branch/replay scope.
