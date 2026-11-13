# Continue a conversation search

`find` returns at most 20 conversations by default. When more match, copy its
`next_cursor` value into the next call's `--cursor` argument. Keep the same query
and filters. Both the unified and standalone commands support this:

```sh
python recap.py --db ../archive.sqlite find "orchard rainfall" --source demo --limit 20
python recap.py --db ../archive.sqlite find "orchard rainfall" --source demo --limit 20 --cursor COPIED_NEXT_CURSOR
```

`COPIED_NEXT_CURSOR` is a placeholder, not a valid token. Use the value from your
own result, without editing or decoding it. Keep following returned tokens until
`next_cursor` is null and `remaining_matches` is zero. A null cursor alone is not
proof of completion if a `pagination_blocker` is present.

The per-call limit remains 1 through 1,000, but pagination can traverse more than
1,000 matches. You may change the page size while continuing. No cursor means a
fresh first page. This applies to conversation `find`, not the separate FTS message
`search` command or export inventory.

A null conversation cursor can coexist with `message_matches_truncated: true`
inside a returned conversation. Those omitted body samples are not another cursor
page. Browse that exact source/conversation with existing `show` message pages;
[the omitted-message walkthrough](OMITTED_SEARCH_MESSAGES.md) connects this to
selecting user evidence and reviewing a useful local title.

## Ranking and counts

The existing ranking is preserved across page boundaries:

1. Conversations with a matching current display title.
2. Matching historical titles, only with `--include-title-history`.
3. Matching message bodies without a matching title.

Within each group, source ID then conversation ID use the existing binary order.
AND matching still spans title/history/body evidence according to the selected
filters. A cursor never changes those matching rules or treats a literal query as
SQL. Message excerpts, original offsets, term-coverage samples and export provenance
are unchanged for each returned conversation.

Each response includes:

- `total_matches`: every matching conversation in this call's snapshot, including
  earlier pages.
- `skipped_matches`: matches at or before the cursor position, zero on a first page.
- `remaining_matches`: matches after the returned page.
- `truncated`: whether additional matches remain after this page.
- `next_cursor`: the token to continue after the last returned conversation, or null.

Thus `skipped_matches + len(matches) + remaining_matches == total_matches`.
First-page match contents and `truncated` behavior are unchanged; later final pages
have `truncated: false` even though `total_matches` includes earlier pages.

## Freshness and scope

When `--from` or `--until` is supplied, the cursor also binds both UTC date
bounds and `recap.timestamp.v1`. Repeat the exact bounds on continuation. The
window filters messages, not whole-conversation bodies; see [time browsing](BROWSE_BY_TIME.md).
Without a window the previous cursor scope is unchanged.

A token binds the case-folded, deduplicated query terms, source filter, history
opt-in and original-export filter. Case changes, repeated spaces and duplicate
terms do not change scope. Keep term order unchanged because term-coverage reporting
preserves that order. Changing a filter or term order requires a fresh search.

Each call scans the selected archive once in one read transaction and hashes the
matching conversation identities and ranking groups. If a later call changes that
membership or order, it rejects the old cursor and asks you to restart. This catches
new or removed matching conversations and title changes that move a match between
ranking groups. The selected cursor position must still be a matching conversation.

This is **not a frozen content snapshot across calls**. Message text, title wording,
snippets, provenance or history can change while the matching identities and groups
stay the same. Those later pages show fresh evidence. A change that affects no
matching identity or rank need not invalidate the cursor. Normal title previews
and their full-content/revision guards remain separate and mandatory.

Tokens are unsigned pagination data, not authentication, authorization, title-review
approval or an encrypted archive identity. They contain source/conversation IDs and
consistency hashes. Treat them and search results as private, and use them with the
intended archive rather than publishing them as diagnostics. Equivalent logical
results in an identical copy of an archive can share a token; it is not tied to a
filesystem path or a particular machine.

## Bounds and recovery

Search retains at most one page per ranking group and the existing bounded body
samples. It does not keep all matches, increase storage with page depth, or perform
an increasing SQL OFFSET scan. It still reads the eligible archive on every call;
the cursor is not a promise of indexed or constant-time search. Exact totals and
order consistency require that scan.

Malformed, overlong, duplicate-key or wrong-scope tokens reject before database
access. Tokens are limited to 16,384 URL-safe characters. An unusually long identity
at a page boundary can exceed that limit: the valid page is returned with
`pagination_blocker: CURSOR_IDENTITY_TOO_LARGE`, null `next_cursor`, and the honest
nonzero remaining count. Narrow the query/source or choose a different page size;
do not rewrite archive IDs to manufacture a cursor.

For a stale cursor, restart without `--cursor` and inspect the new result. Do not
edit its hashes to force continuation. All search pages are read-only: no messages,
original exports, titles or review states are modified.

With `--canonical-unicode`, also keep that flag and the same runtime Unicode
database version on every page. Canonically equivalent normalized query terms
share a cursor scope. See [canonical Unicode search](CANONICAL_UNICODE_SEARCH.md).
