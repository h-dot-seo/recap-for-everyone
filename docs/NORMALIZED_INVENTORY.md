# Browse normalized JSONL without a database

`list-export --format normalized` lists conversation IDs and distinct supplied
original titles from a normalized JSONL snapshot. It uses the same whole-file
validation and coverage report as normalized inspection. This is not import
admission, an effective-history reconstruction, or evidence that supplied origin
claims are authentic. IDs, titles and echoed queries may be private.

For each conversation, `metadata_records` counts normalized input rows, including
repeated identical or conflicting identities. `extracted_messages` and role counts
count the same occurrences, not unique archive messages. `original_titles` keeps
distinct effective titles in input-line order; an omitted title is the empty
string. Conversation ordering and pagination retain Unicode code-point ID order.
The shared coverage report retains identical/conflicting repeated-identity counts.
Conflicts do not prevent inventory but can prevent subsequent ingest.

Every normalized item has `selection_supported: false` and
`selection_blocker: NOT_SUPPORTED`. Selected normalized ingest and selected
normalized inspection are not supported. Listing an ID does not enable those
operations, change import authorization, or predict a conflict-free write.
`import --format normalized` and normalized title plans remain unavailable.
Use ordinary `ingest` for the complete normalized file after checking it.

Metadata filters match IDs or titles. Text filters match individual supplied
normalized message occurrences, optionally by role; only counts and metadata are
returned, not message-body fields. A query itself may disclose private text.
Filtering and pagination never avoid reading or validating unselected input.
Optional expected-export hash validation binds pages to the complete file bytes.
No new byte ceiling, original-export provenance, database writes, or selected
write path is introduced.

```sh
python recap.py list-export examples/conversations.jsonl --format normalized --limit 1
python export_inventory.py examples/conversations.jsonl --format normalized --limit 1
```
