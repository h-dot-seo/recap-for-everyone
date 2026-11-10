# Read-only Markdown conversation views

Use `render --format markdown --output NEW_FILE` for a readable UTF-8 local
conversation document. This extends the same command as [HTML views](RENDER_VIEWS.md).
There is no second export command, sidecar or standalone render script. `show`
continues to return its unchanged JSON object on stdout.

Create an empty directory outside this repository and replace `OUTPUT` below:

```sh
python recap.py --db OUTPUT/archive.sqlite ingest examples/render-adversarial.jsonl --source synthetic
python recap.py --db OUTPUT/archive.sqlite render --source synthetic --conversation fictional --format markdown --output OUTPUT/full.md
python recap.py --db OUTPUT/archive.sqlite render --source synthetic --conversation fictional --around-message two --before 1 --after 0 --format markdown --output OUTPUT/context.md
```

The commands use only fictional messages. stdout is an ASCII
`recap.saved-view.v1` receipt with `document_kind: "markdown"`, UTF-8 encoding,
byte count, SHA-256 and staging cleanup status. It contains no message text, IDs,
titles or destination paths. Output is file-only and required. Existing files,
directories, symlinks and dangling links are refused; the parent must exist.
Publication uses the same private stage and atomic hard link as HTML and requires
hard-link support. No overwrite or replacement fallback exists. After publication,
a cleanup failure still reports SAVED and the leftover staging basename. Inspect
it rather than retrying blindly. Each document is one independent file, with no
multi-file atomicity claim.

## Fenced display, not Markdown supplied by the conversation

Only fixed program headings, boundary text and generated message ordinals appear
outside fences. All supplied metadata, including titles, IDs, timestamps,
selection, revision, message counts, scope and every provenance occurrence, stays
in fenced JSON text. Message bodies are separate fenced text, not interpreted
Markdown. Every fence uses the fixed `text` info string and at least three
backticks, with its length strictly greater than the longest consecutive backtick
run anywhere in that block. Runs across internal encoding chunks count together.
Tildes, headings, links, images and raw HTML supplied in a block remain data under
CommonMark fenced-code rules. No data enters a heading, info string or URL.

Korean and emoji remain readable. The HTML display rule is shared: Cc controls
except LF/TAB, Cf format characters except ZWJ/ZWNJ, surrogates, and Zl/Zp become
literal Unicode escapes. ZWJ/ZWNJ remain for linguistic and emoji shaping. JSON
metadata also quotes newlines and tabs. A separator newline is added before each
closing fence. Literal escape strings and escaped controls can look alike.
This is not a reversible or byte-exact transcript; use `show` JSON for exact
supplied evidence. Rendering does not redact private text.

These fences are a CommonMark-based defense, not a guarantee that every Markdown
viewer is safe or displays the same content. Viewer extensions, auto-linking or
external-resource behavior are outside this tool's control. Inspect with a trusted
local viewer; do not upload private output merely to preview it.

## Selection, provenance and limits

The view uses exactly one existing `show` read snapshot. It retains the whole
conversation's message count, original/display titles and revision, message order,
branch scope, local scope, selection and context warnings. `--message`, page
`--limit`/`--offset`, and `--around-message`/`--before`/`--after` keep their existing
validation. A selected page or context is not the entire conversation. A full
archive view is only all imported text nodes, not proof that the original session
was complete or that an assistant turn finished. No completeness metadata is
inferred. Each message retains source hash/line and every returned export hash,
locator and parent ID inside its metadata fence.

The embedded `recap.render.v1` metadata labels the format and includes
`view_sha256`: the canonical sorted, compact ASCII JSON hash of the exact `show`
object, not a whole-conversation content fingerprint for partial views. Same
snapshot, selection and format yield identical bytes. No clock, host or database
or output path is added. Body text may itself contain such data.

The 16 MiB encoded-output cap includes all metadata, Unicode bytes, both fences
and banners; it is enforced before staging. A long backtick run lengthens both
fences and can itself exceed the cap. Narrow the selection on refusal.
Message-count limits are not byte limits. A full conversation keeps the same input
memory exposure as `show`; the output cap does not bound archive input memory.

PRIVATE MESSAGE TEXT: keep the file outside public repositories and shared
folders. It is local archive rendering, not a vendor export or an active-branch
reconstruction. Display titles are local only. Edits are not review artifacts or
a substitute for apply-title. No archive mutation, model call, network,
authentication, approval or privacy clearance is established. Saved review-queue
HTML uses the separate [render-queue command](RENDER_QUEUE.md).
