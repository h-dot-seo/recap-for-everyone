# Read one recorded web-export path from the archive

This is a private, read-only archive view, not the website's current selection or
UI visibility. A web import now retains ID-only node topology and the supplied
current-node pointer in its existing transaction. It still imports all supported
text nodes and roles. Default `show`, imported message bytes and coverage reports
are unchanged.

## Synthetic walkthrough

Use a fresh output directory outside the repository. The shipped synthetic export
has no current-node pointer, so this example chooses its explicit endpoint.

```sh
python recap.py --db OUTPUT/branch.sqlite import examples/web-export.json --source demo --format web
python recap.py --db OUTPUT/branch.sqlite show --source demo --conversation synthetic-chat --branch --node m2
```

The selected path is `m1`, `m2`. The same flags work on `conversation_view.py show`.
Omit `--node` only when the chosen export supplied a valid `current_node`. A missing,
invalid or ambiguous pointer is not replaced by the latest message, a leaf or a
heuristic. A node literally named `current` is an ordinary explicit node ID.

When several recorded export hashes contain the conversation's topology, supply
`--export-sha256` with the exact lowercase hash you intend to read. There is no
implicit newest-export selection. Branch mode cannot be combined with an exact
message, page limit/offset or around-message window. The whole-conversation
`message_count` remains distinct from selected path counts.

## What the path establishes

The selection reports the endpoint and whether it came from the recorded pointer
or explicit input, the chosen export hash, root-to-endpoint node IDs, textless-node
count, excluded-node count, forks, continuations and whether the endpoint is a
leaf. Parent links, including textless roots and tips, come from that export's
mapping. A 0/1 extracted-text marker distinguishes a textless node from a missing
selected-export occurrence; detected disagreement fails closed. It is parser
metadata, not proof of authenticity or complete preservation. A deterministic
integer ordinal retains the original mapping order;
SQLite rowid and lexical node sorting are not evidence of that order.

Message selection requires an occurrence from the selected hash and mapping node.
Messages retain their archive provenance. All supported roles on the path are
included, including system and tool messages. The result is PRIVATE CONTENT with
node IDs and text, not a claim about UI visibility, authenticity, consent, rights,
completeness or live remote state. It creates no title/review approval.

## Legacy and recovery boundaries

Read-only calls do not create or backfill topology. An older archive, normalized
input or local export cannot supply web topology. Reimport the same original web
export bytes explicitly to fill the additive ledgers for an older archive; the
normal identity checks still apply and existing messages are not rewritten.
Without those original bytes, missing topology cannot be inferred from text-only
occurrences. Importing one selected conversation never stores another
conversation's node IDs. Repeated identical imports are additive and deterministic.

The two optional ledgers are `export_nodes` and `export_conversations`. They are
not a schema epoch or automatic migration. They are created only by an explicit
web import and commit or roll back with its other rows. Pre-existing archive
readers ignore the additional tables; they do not gain branch support.

Recovery manifest v1 neither declares nor compares these topology ledgers. A
successful v1 rehearsal therefore does not establish their preservation. Retain
the original exports, which are needed to reproduce the topology, and do not
interpret this feature as a new backup guarantee. No manifest v2, archive stamp,
private-archive migration or external connection is introduced.

Branch selection does not impose a small archive-read or memory bound: validating
the recorded graph and loading provenance may inspect more rows than the returned
path. Use only archives and original exports you are authorized to read or import.

The ordinal and extracted-text marker are additions to the initial topology
proposal needed for exact ordering and detectable occurrence-loss boundaries.
Existing readers ignore these tables. This release does not rewrite any same-name
table with an incompatible layout: a conflicting shape makes the explicit import
fail, preserving its previous data. There is no automatic compatibility repair.

For an explicitly chosen declaration that does compare these ledgers, see
[recovery v2](RECOVERY_V2.md). Default v1 continues to omit topology; v2 does not
make object-based rebuild restore title/review decisions.
