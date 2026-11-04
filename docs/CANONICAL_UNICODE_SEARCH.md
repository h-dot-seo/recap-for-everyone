# Find canonically equivalent Unicode text

Copied web and local conversation text can use different Unicode representations
of the same text. For example, `기전` may be stored as separate Hangul Jamo, and
`café` may contain a separate combining acute accent. Default `find` still uses
case-folded literal substrings and does not equate those representations.

Opt in when this difference is hiding a conversation:

```sh
python recap.py --db ../archive.sqlite find "기전 café" --canonical-unicode
python conversation_search.py --db ../archive.sqlite "기전 café" --canonical-unicode
```

The Python API appends `canonical_unicode=False` after the existing `cursor`
parameter. Pass `canonical_unicode=True` to opt in. Other values fail before
opening the archive. There are no additional dependencies, network requests,
model calls or source-file reads.

## Matching behavior

Query, current display titles and message bodies use the same temporary search
transform: `NFC(NFD(text).casefold())`. Prior local titles use it only with the
existing `--include-title-history` option. Terms remain whitespace-separated,
AND-connected literal substrings across the selected conversation. Ranking,
source/export filtering and the three-body evidence sample are unchanged.

Canonical normalization handles composed/decomposed accents, Hangul and canonically
reorderable combining marks. Decomposition before folding also handles the Greek
ypogegrammeni case correctly. The NFC result is a composed search representation;
an unaccented query `cafe` does not match `café` merely by decomposing its final
letter. No marks are stripped, and no NFKC/NFKD compatibility transform is used.
Full-width and circled characters therefore remain distinct from ordinary Latin
letters where case folding itself does not equate them. Existing case-fold
expansions, such as `ß` to `ss` and some ligatures, still apply. This is not fuzzy,
transliterated, locale-specific or semantic search.

This follows the canonical caseless comparison model in the
[Unicode Standard, section 3.13](https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/),
using NFC rather than NFD for the final substring representation. The runtime's
[Unicode database](https://docs.python.org/3.10/library/unicodedata.html) supplies
normalization, composition and combining classes. Responses report
`canonical_unicode: true`, the exact `normalization` expression and
`unicode_version`. Different Python runtimes can have different Unicode versions.

## Original evidence and offsets

Nothing is normalized in the database or original exports. Hashes, IDs, titles,
message text, source locators and title proposal fingerprints remain unchanged.
This option changes only the read-only search view, not message-level FTS `search`,
import identity conflict checks, title collision review or title validation.

The returned `snippet` is still an unchanged slice of the original message, with
at most 240 Unicode code points. `snippet_start` and `snippet_end` remain original
zero-based, half-open code-point offsets. `first_match.term` is the normalized
query term, while its `start` and `end` are a covering interval in the original
text. Composition combines the contributing original positions; reordering can
make the covered interval include intervening marks that did not themselves
match. Do not assume that normalizing that interval in isolation exactly equals
the query, or that these offsets count bytes, UTF-16 units or grapheme clusters.

Canonical mode chooses the first hit in **normalized search order**. Reordered
marks can make this differ from original code-point order. Partial case-fold
expansion matches still cover the whole original character. Long covering spans
may extend outside the excerpt; `first_match.fully_visible` makes this explicit.
Use `show --message` to retrieve the full original message when needed.

Offset mapping streams through the message and buffers combining sequences,
rather than retaining a position map for every character of every message.
An exceptionally long combining sequence can still require memory proportional
to that sequence. Search already materializes one original body and its transformed
copy at a time; it is not a fixed-byte-memory or constant-time operation.

## Pagination and safety

Keep `--canonical-unicode` on every cursor page. The cursor scope binds this mode,
the runtime Unicode version, normalized query terms and the existing source,
history and export filters. Canonically equivalent queries can continue the same
search; changing mode or Unicode version requires restarting without a cursor.
Default-mode token generation and result shapes remain unchanged.

As before, a cursor binds matching identities and ranks, not a frozen content
snapshot. A later page can return updated wording with unchanged identities/ranks.
Search output and cursor identities may contain private information. Keep them
outside the public repository. Normalization is not sanitization, authentication,
permission to transmit data, or proof that a title is accurate.
