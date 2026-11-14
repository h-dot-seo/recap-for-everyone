# A private, text-free message locator

`export-provenance` saves one explicitly selected archived message's locator and
hashes in a new `recap.message-provenance.v1` card. `check-provenance` compares that
card with the same exact source/conversation/message tuple in one current read
snapshot. This provides a pointer back into private research notes without also
exporting the message body, unlike `show --message`.

The card contains no message text or titles. It contains private source,
conversation and message IDs, role and timestamp labels, a UTF-8 text hash and
byte count, the normalized-artifact `source_sha256`/`source_line`, and the same
union of legacy and complete `export_provenance` entries used by `show`:
`original_sha256`, `locator`, `parent_id`. `declared_at` is supplied text, not a
clock read. A plain normalized ingest has an empty original-export list.

`text_sha256` hashes the archived extracted text's UTF-8 bytes, not the original
export file. `source_sha256` identifies accepted normalized bytes, which adapter
imports can construct in memory using platform-dependent newlines. Those bytes
may never have existed as a file. Original export hash plus locator is the
portable original-export anchor, when recorded; this tool does not fetch it.

## Privacy and meaning

IDs and locators are private. A short or predictable text's hash can be confirmed
by guessing; this card is not anonymized. Role does not authenticate authorship,
and an archived timestamp is only a supplied label. No validity, authorship,
consent, retrieval, research-report status or publication citation is established.
Do not automatically treat a conversation as an authored paper or a retrieved
report in another tool. Sharing or reusing a card requires a separate operator
decision about permission and scope. No cross-repository field mapping is made.

Both commands open the archive read-only and close their connection explicitly.
The saved file is created exclusively; existing paths and dangling links are
refused. It is bounded at 64 MiB, exact-schema checked and deterministic for the
same snapshot and supplied date. This is not an archive UUID or a signed document.
The stdout declaration receipt contains file bytes/hash, not the card's IDs.
`--text` changes only the receipt presentation, not the saved bytes.

## Rechecking

A matching card reports `PASS` with exit 0. A well-formed card whose selected
message is missing, altered or has different provenance reports `STALE`
with exit 1 and no private values. Malformed or oversized cards fail before
archive access. A changed display title or review decision alone does not make
the card stale: neither title revisions nor review state is part of the card.
A newly recorded original-export occurrence does change it. The comparison is
not proof that the card was originally created by this tool; a consistently
edited unsigned card can match a matching archive. No automatic refresh occurs.

A card's file SHA-256 from the declaration receipt identifies the whole card;
its `text_sha256` identifies only the extracted message text. Do not confuse them
when retaining or checking files. Failed checks do not alter the card or database.

## Executable synthetic example

Create an empty `OUTPUT` directory outside the repository and substitute its path.
The supplied fixture is fictional. The final check reads the private card and
archive, but its stdout contains no IDs, titles or body text.

```sh
python recap.py --db OUTPUT/provenance.sqlite import examples/web-export.json --source synthetic --format web
python recap.py --db OUTPUT/provenance.sqlite export-provenance --source synthetic --conversation synthetic-chat --message m2 --declared-at 2026-11-14 --output OUTPUT/message-card.json
python recap.py --db OUTPUT/provenance.sqlite check-provenance OUTPUT/message-card.json
```
