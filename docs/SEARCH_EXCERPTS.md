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
Combining sequences are not normalized: search retains its existing case-folded
literal-substring semantics and does not equate different normalization forms.

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
