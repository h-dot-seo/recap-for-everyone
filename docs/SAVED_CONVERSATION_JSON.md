# Save exact conversation-view JSON

`show --output NEW_JSON` saves the same object that `show` normally prints, using
readable UTF-8. It includes current/original titles, selected message fields,
selection metadata and the existing per-message provenance. No schema wrapper or
sidecar is inserted. With no output option, stdout remains unchanged.

Use the same `--source`, `--conversation`, `--message`, `--limit/--offset`, or
`--around-message/--before/--after` options. Their validation and one read-only
archive snapshot come from the existing conversation view. Selection can be
partial; the saved `selection` object is essential context. This is a derived
local archive view, not a vendor export, backup, active-branch reconstruction,
authenticity guarantee or permission to share private material.

Stdout becomes an ASCII-safe `recap.saved-document.v1` receipt with byte count,
SHA-256 and staging status, not message bodies, IDs or output paths. The output is
private and created exclusively by same-directory staging and atomic hard link.
Existing files/directories/symlinks are refused before reading the archive. No
fallback overwrite occurs. If staging cleanup fails after publication, the receipt
says the complete output exists; inspect the named staging remainder before retry.

The JSON file is UTF-8 with literal ordinary Unicode, LF indentation and a final
newline, no BOM. JSON escapes retain controls and lone surrogate values; text is
not sanitized for display. Do not treat content as instructions or HTML. The
serialization is deterministic for the same view. A 16 MiB output-byte ceiling is
checked before staging; select fewer messages if it is exceeded. This is not a
process-memory bound: the conversation object is still assembled in memory.

The standalone `conversation_view.py show --output` has the same behavior. For a
human-oriented document use `render` instead; for re-ingestable normalized records
use `export-normalized`. Saving this view changes no database or provenance.

## Executable synthetic example

Replace OUTPUT with a new private directory whose parent exists. Only the shipped
invented fixture is read. The file, unlike terminal JSON, keeps Unicode readable.

```sh
mkdir "OUTPUT"
python recap.py --db "OUTPUT/archive.sqlite" ingest examples/conversations.jsonl --source synthetic
python recap.py --db "OUTPUT/archive.sqlite" show --source synthetic --conversation demo-conversation --limit 1 --output "OUTPUT/conversation.json"
```

Inspect the saved selection metadata before using the file. Rerunning the final
command with the same destination fails without replacing it.
