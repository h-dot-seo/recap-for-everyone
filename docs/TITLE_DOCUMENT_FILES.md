# Save title proposals and previews without shell redirection

After intentionally importing an export, you need local JSON files to move a
proposal through review and explicit apply. Use `--output NEW_JSON` on the supported
read-only title commands instead of shell `>`:

```sh
python recap.py --db ../recap-demo/archive.sqlite suggest-title --source web-demo --conversation synthetic-chat --output ../recap-demo/proposal.json
python recap.py --db ../recap-demo/archive.sqlite preview-title ../recap-demo/proposal.json --with-evidence --output ../recap-demo/reviewed.json
```

These examples assume the web import from [the walkthrough](TITLE_WALKTHROUGH.md)
and an existing private directory. Choose new filenames if those paths already
exist. This raw suggestion is not the walkthrough's verified branch selection;
add `--output` to `suggest-branch-title` when that is your intended evidence scope.

Open **the saved `reviewed.json`**, not just the terminal receipt. Verify its title,
source, conversation, evidence, previous title and expected revision. Only after
your explicit review use the existing `apply-title reviewed.json` command. Saving
a file does not apply, approve or schedule a title change.

## Supported commands and unchanged document shapes

The unified `recap.py` commands supporting this option are:

- `suggest-title`, including an exact `--message` choice.
- `suggest-branch-title`, `suggest-replay-title`, `suggest-attributed-title`.
- `review-titles`, including supplied proposals and selection filters.
- `preview-title`, including queue selection, explicit replacement wording and
  the optional private `--with-evidence` view.

The standalone `title_suggestion.py`, `branch_title.py`, `replay_title.py`,
`attributed_title.py` and `title_proposal.py preview` support the same option.
It is a command option, not a global switch for arbitrary output. It is deliberately
absent from import, apply, manual title writes, review-state writes and the separate
provider adapter. A save failure must not make a committed mutation look unsuccessful.
`prepare-web-export --output` retains its separate existing ZIP-member behavior.

The saved file contains the **same proposal, queue or preview object** that the
command normally prints. No receipt envelope is inserted. Evidence selection,
full-content fingerprints, revision checks, advisory hints and unsigned metadata
keep their existing meanings. Queue files still require an explicit conversation
at preview. The output helper validates serialization, not title meaning, source
authenticity, human review or arbitrary caller-provided document schemas.

With `--output`, stdout contains only a receipt with:

- `schema: "recap.saved-title-json.v1"` and `status: "SAVED"`.
- `document_kind`: `proposal`, `queue` or `preview`.
- `encoding: "UTF-8"`, the exact byte count and SHA-256 of the saved bytes.
- Staging cleanup status and, if needed, the leftover staging basename.

The receipt does not print the saved title/body, source/conversation ID or output
path. It is not a proposal or reviewed document and cannot replace one at the next
step. Hashes and metadata are not anonymization, authenticity or approval. Apply
still checks the saved preview's content fingerprint and revision, not this receipt.
Without `--output`, stdout behavior and JSON shapes remain unchanged.

## Encoding and no-overwrite publication

The program writes UTF-8 **without a BOM**, readable Unicode and a final newline.
It does not depend on the shell's redirection encoding. Korean and emoji remain
literal characters in the saved JSON; the metadata receipt remains ASCII-safe.
If an editor subsequently saves a proposal, queue or reviewed preview as UTF-8
with one BOM at the very start, title preview/apply, supplied-candidate review and
`review-state --from-queue` accept it. The same applies to standalone preview/apply.
This only removes the initial file signature during decoding: a U+FEFF character
inside a JSON string stays unchanged. Repeated signatures or signatures outside
JSON strings elsewhere remain invalid. The supplied-proposal byte budget still
counts every original byte, including the BOM. Reading never rewrites the file.

Existing UTF-16/UTF-32 or malformed proposal files are not converted or repaired.
This tolerance does not change shared JSON parsing, provider payload/consent files,
transfer documents or title plans. Native output remains UTF-8 without a BOM.
Generate a fresh valid file rather than renaming or editing encodings blindly.
All document-shape, evidence, content-fingerprint and revision checks still apply;
a file signature does not establish authenticity, approval or currentness.
Deeply nested selected queue items or supplied candidates fail with a fixed diagnostic if copying
exceeds the runtime recursion capacity, rather than printing a traceback. There is
no new fixed nesting guarantee or raised interpreter recursion limit.

The destination's parent must already exist. Full generation/validation and JSON
serialization complete before staging. A private same-directory temporary file is
written, flushed, synced and closed, then published by an atomic no-overwrite hard
link. Existing files, directories and valid/dangling symlinks are refused, including
the input proposal, original export or archive database selected as an output path.
Competing writers cannot both publish to the same name. There is no replace/rename
fallback and no automatic overwrite or deletion of existing user files.

This requires filesystem hard-link support. Some removable, network or restricted
filesystems may reject it even when Python and SQLite work. Use a suitable local
directory you control; the runtime checker does not test this capability. The writer
does not defend against a hostile concurrent directory namespace or promise full
power-loss durability. File creation permissions depend on the OS/filesystem;
choose a private directory rather than treating a temporary-file mode as encryption.

Validation errors leave no new destination. Ordinary pre-publication I/O failures
remove staging when cleanup succeeds. If cleanup itself fails, a private staging
file may remain and the error is reported. If publication succeeds but staging
cleanup fails, the command instead returns `SAVED` with
`staging_cleanup_complete: false`: the **complete destination already exists**.
Inspect the reported leftover staging link before removing it; do not blindly
rerun with the same name. A crash or interrupted command can also leave files, so
inspect the directory before retrying an uncertain outcome.

## Continue the explicit review workflow

The primary [start-here](START_HERE.md) and [web/local](TITLE_WALKTHROUGH.md) guides
use native saving and test the files the CLI actually creates. Title generation
and preview remain read-only **against the archive**; the requested output file is
an explicit local write. Saving neither protects a stale preview from later archive
changes nor relaxes any apply checks. Use new filenames for fresh proposals/previews.

Older examples or unsupported commands that still use `>` need a UTF-8-capable
shell. Shell redirection opens/truncates its target before the command runs, so
it can destroy a same-named input even when validation then fails. Do not combine
`--output` with redirection to its input or output path; the program cannot prevent
an earlier shell write. Native saving avoids those shell hazards only when used
without such redirection.

Saved queues and previews can contain private titles, identifiers and message text,
especially with `--with-evidence`. Keep all generated files outside public repositories
and shared directories. No account collection, model transmission or remote rename
is performed.
