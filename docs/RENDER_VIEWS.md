# Read-only HTML conversation views

`render --format html --output NEW_FILE` saves a readable UTF-8 local view. It uses
exactly the `show` single read snapshot and selectors: `--message`, `--limit` with
`--offset`, or `--around-message` with `--before` / `--after`. Validation and defaults
are shared, not reimplemented. [Markdown views](RENDER_MARKDOWN.md) use the same
command with `--format markdown`; there is no standalone render script. Saved
[review-queue views](RENDER_QUEUE.md) use a separate `render-queue` command. The
conversation HTML behavior is unchanged.

Create an empty directory outside this repository and replace `OUTPUT` below:

```sh
python recap.py --db OUTPUT/archive.sqlite ingest examples/render-adversarial.jsonl --source synthetic
python recap.py --db OUTPUT/archive.sqlite render --source synthetic --conversation fictional --format html --output OUTPUT/full.html
python recap.py --db OUTPUT/archive.sqlite render --source synthetic --conversation fictional --around-message two --before 1 --after 0 --format html --output OUTPUT/context.html
```

Open the saved file locally. stdout contains only the ASCII JSON
`recap.saved-view.v1` receipt: kind, encoding, bytes, SHA-256 and staging cleanup
status, without conversation IDs, bodies or destination paths. Existing files,
directories, symlinks and dangling links are refused. A private same-directory
stage is closed before atomic hard-link publication; the filesystem must support
hard links. No replacement fallback exists. If cleanup fails after publication,
SAVED remains true and the receipt gives the leftover staging basename. Inspect
that file rather than retrying blindly. The title JSON receipt remains unchanged.

## Display and provenance

Ordinary Unicode including Korean and emoji stays readable. HTML special
characters are escaped in every value; values are isolated using `bdi` and
`unicode-bidi:isolate`. Cc controls except LF/TAB, Cf format characters except
ZWJ/ZWNJ, surrogates, Zl and Zp appear as literal Unicode escapes. ZWJ/ZWNJ remain
for linguistic and emoji shaping. Literal escape strings and escaped controls can
look alike: this is a readable view, not a reversible or byte-exact encoding.

No supplied value becomes an attribute, ID or URL. Message anchors use ordinals.
No scripts, forms, links or external resources are generated; body URLs stay plain
text. CSP denies resources except the exact hash-bound static style, and denies
base URLs, forms, objects and frames. Referrer policy is no-referrer. These are
rendering defenses, not privacy clearance or a guarantee about every viewer.

The page retains original/display titles and revision, whole-conversation message
count, selection/context warnings, message order, branch scope, source hash/line
and all returned export provenance. A page is not the entire conversation.
`view_sha256` hashes the exact show object with sorted keys, compact separators,
ASCII JSON escapes and finite JSON values. It is not `content_sha256` and is not a
whole-conversation fingerprint for partial selections. Identical snapshots and
selectors produce identical bytes. No clock, host or database/output path is added.
Supplied message text can itself contain paths; rendering does not redact data.

## Limits and boundary

Encoded output is capped incrementally at 16 MiB before publication. Narrow the
selection if it exceeds the cap. Message-count bounds are not byte limits. An
unselected full conversation has the same input memory exposure as `show`.

PRIVATE FILE: keep output outside public repositories and shared folders. This is
local archive rendering, not a vendor export or active-branch reconstruction.
Titles are local only. Browser edits are not review artifacts; not a substitute
for apply-title. No archive mutation, model call, network, authentication or
approval is established. The original `show` JSON output is unchanged.
