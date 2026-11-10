# Read-only saved title review queue

`render-queue QUEUE.json --output NEW_FILE` reads an explicitly saved
`recap.title-review-queue.v1` JSON file and writes a readable HTML page. It takes
no database and rejects `--db`. No standalone script exists. Save the queue first;
rendering never refreshes it from a different database snapshot.

Create an empty directory outside the repository and replace `OUTPUT`:

```sh
python recap.py --db OUTPUT/archive.sqlite ingest examples/render-adversarial.jsonl --source synthetic
python recap.py --db OUTPUT/archive.sqlite review-titles --source synthetic --output OUTPUT/queue.json
python recap.py render-queue OUTPUT/queue.json --output OUTPUT/queue.html
```

These examples are fictional. Open the HTML locally. Keep the JSON for
`preview-title QUEUE.json --conversation ID` with the selected archive; the HTML
is not a proposal or preview and cannot approve or apply anything. Browser edits
are not review artifacts; not a substitute for apply-title. Saved queues are
unsigned and may be stale. Schema validation does not authenticate their claims.

## Binding, content and limits

The page records `recap.queue-html.v1`, the original file's `input_sha256` and byte
count, including a leading UTF-8 BOM if supplied. The hash matches the SHA-256 in
the queue-saving receipt, not a reserialized JSON hash. Identical input bytes
produce identical HTML bytes. No clock, hostname, input/output path or database
path is added. Supplied metadata may itself contain paths and private text.

Input is bounded to 16 MiB before UTF-8 decoding (one leading BOM is accepted).
Duplicate keys, unpaired surrogates, invalid/deep JSON and nonfinite numbers are
rejected with a fixed diagnostic. The current queue envelope and item field sets,
types, unique identities, counts, page bounds, proposal identities, state lease,
advisory and collision shapes are checked. Supplied proposal metadata remains
open-ended JSON, inertly displayed rather than interpreted or verified. Unknown
envelope/item fields are rejected; regenerate with the current `review-titles`.
This is structural validation, not evidence validation or a freshness check.

The original queue order is retained, with no sorting options or color-based
judgments. Each item shows current title/revision, review state, proposal and
retained metadata, full title advisory including its privacy warning, collision
counts and samples, or the supplied UNAVAILABLE reason code. No new advice or
score is generated. Empty pages retain their page metadata.

The shared HTML display rule escapes all data, isolates it in `bdi`/`pre`, and
makes controls except LF/TAB, format characters except ZWJ/ZWNJ, and Unicode line
and paragraph separators visible as escapes. ZWJ/ZWNJ remain for shaping. Data
never becomes markup, attributes or URLs; ordinal anchors are program-generated.
No scripts, forms, buttons, links or external loads exist. CSP allows only the
hash-bound static style; referrer policy is no-referrer. Literal escapes can look
like escaped characters. This is not a reversible or byte-exact display, privacy
clearance, or a guarantee about every viewer.

Output is capped incrementally at 16 MiB before publication. If either cap is
exceeded, save a smaller `review-titles --limit` page. Memory includes the bounded
input, decoded JSON and bounded output, not a constant-memory streaming parser.

## Exclusive output and receipt

The shared publisher creates a private same-directory stage, closes it, and uses
an atomic hard link to publish. The filesystem must support hard links. Existing
files, directories, symlinks and dangling links are refused; there is no overwrite
fallback. The input file is never changed, even when used as the output target.
stdout is an ASCII JSON `recap.saved-view.v1` receipt with HTML kind, encoding,
bytes, SHA-256 and staging cleanup status, not queue IDs, titles or file paths.
If cleanup fails after publication, SAVED remains true and the receipt names the
leftover staging basename. Inspect it rather than blindly retrying.

PRIVATE FILE: keep JSON and HTML outside public repositories and shared folders.
No database read/write, model call, network, remote title change, authentication,
semantic validation or approval occurs. Existing `review-titles`, `show`, HTML
conversation and Markdown outputs are unchanged.
