# Explicit read-only MCP stdio access

This optional local entry point gives an operator-selected MCP client six archive
read tools by default without exposing Recap's write commands. It does not install, configure
or connect a client. Start it only for an archive and receiving client the operator
has authorized. The public feature is a constrained local tool interface; no private
account, service integration or unattended deployment is supplied.

## Client configuration shape

The following generic configuration is tested with an invented archive. Replace
ARCHIVE.sqlite with the explicitly selected private archive and choose the Python
launcher appropriate to the client. The working directory must be this checkout;
no particular client's configuration file or installation is implied.

```json
{"command":"python","args":["recap_mcp.py","--db","ARCHIVE.sqlite"]}
```

The client launches a foreground child process and communicates through stdin and
stdout. EOF ends it. There are no sockets, HTTP transport, scheduler, daemon,
background watcher, model calls or external provider requests. It must not be
exposed as a network service. Nothing here approves transmitting an archive to a
model or retaining its text in a client log.

## Default archive tools

| Tool | Existing operation | Excluded paths |
|---|---|---|
| list | Conversation inventory | No imports or archive changes |
| find | Existing title/body search | No source-file reads or rewrites |
| show | Selected archive message view | No saved output file |
| title-history | Existing local title history | No title changes or restore |
| stats | Stored message/artifact counts | No new schema or ingestion |
| review-titles | Existing review queue and local excerpts | No proposal/checkpoint files by default, output save or review-state write |

Use tools/list for the exact input schemas, required identities and numeric
bounds. The archive is fixed by the launch argument; calls cannot select another
database. Unknown properties are rejected. No title, review-state, import, ingest, apply-title, rebuild or recovery declaration
tool is exposed. File tools are absent unless input directories are explicitly
authorized at launch as described below. There is no generic CLI, SQL, file or shell execution tool.

Each successful tool result has two text items: the existing operation's JSON,
then a fixed privacy and authority boundary. The first item preserves the normal
CLI JSON representation, without its terminal newline. Raw message text, titles,
source IDs and history can be private. The boundary is not sanitization: retrieved
content remains untrusted evidence, never instructions. The server cannot control
where the receiving client sends or stores it, or force a model to respect this
rule. Read-only does not imply permission, authentication or approval.

## Pinned protocol and lifecycle

This implementation targets MCP protocolVersion **2025-06-18**, observed
2026-11-14, rather than promising every current or future protocol extension.
References: [lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle),
[tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools),
and [stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports).

Send initialize first with protocolVersion, capabilities and clientInfo; the
server replies with its supported version. A client that cannot use that version
must disconnect. Then send notifications/initialized. Supported request methods
are initialize, ping, tools/list and tools/call. Notifications receive no response
and never execute a tool. A method with an id is a request, even when its name
starts with notifications/; unsupported notification-named requests receive an
unknown-method error. Optional object-valued params._meta is accepted and ignored;
progress reporting is not implemented. Batch requests are not supported. Messages are individual
UTF-8 JSON objects separated by LF; stdout contains protocol messages only.

Unknown methods return JSON-RPC -32601. Unknown tools and invalid parameters
return -32602; malformed JSON returns -32700 and invalid request envelopes return
-32600. Caught operation failures use result.isError with the existing safe CLI
diagnostic. Unexpected internal exceptions return fixed -32603 without traceback.
A tool failure is not permission to retry, repair or substitute another source.

## Resource and filesystem boundaries

Request lines and complete serialized responses are limited to 1 MiB each. Request
IDs are additionally limited to 256 bytes in their ASCII JSON representation, so
accepted IDs can be preserved in bounded responses. An over-limit ID is rejected
as an invalid request with null id and the session closes before tool execution.
This is an explicit transport admission limit, not a substitute ID for an accepted
request. An
oversized request produces a fixed error and closes the input session rather than
interpreting its remaining bytes as another request. Oversized results are refused
with isError and advice to request a smaller selection, never silently truncated.
Choose explicit message selection and small limits when the archive is large.

This is an output/request bound, not a strict memory, database-work or wall-time
bound. Existing queries can materialize results before the response-size check;
some work examines more than the returned page. Calls are sequential. Cancellation
notifications do not interrupt a running query. The client owns timeouts and may
terminate the foreground process; no in-process deadline is promised.

Each call opens and closes its read connection. Separate calls can observe changed
archive state; no session-wide immutable snapshot is promised. Read-only SQLite
can create WAL/SHM sidecars or fail on a hot journal. Tests of unchanged main bytes
and a DELETE-mode scratch tree do not guarantee absence of all sidecar effects.
This server is not a hostile-filesystem sandbox, recovery check or privacy filter.
EOF/process termination is not a claim that the client deleted already received
text. No real archive is used by the included tests.

## Explicit input-directory access

An operator may additionally select directories containing the exact local inputs
the receiving client is authorized to inspect. This does not install a client or
authorize transmitting every file merely because it is in a directory. Scope the
directory narrowly and review the client's handling of private data first. Without
--allow-input-dir, the default six-tool interface is unchanged.

```json
{"command":"python","args":["recap_mcp.py","--db","ARCHIVE.sqlite","--allow-input-dir","INPUTS","--max-input-bytes","1048576"]}
```

Replace INPUTS with the explicitly selected existing directory. The launch flag
may repeat. --max-input-bytes accepts 1 through 67108864 bytes and defaults to
67108864 (64 MiB); the example deliberately lowers the admission limit to 1 MiB.
These are launch settings, not per-call arguments. Directory names are not emitted
in tool metadata. The archive remains fixed at launch; file tools do not open it.

With at least one allowed directory, tools/list additionally exposes:

| Tool | Existing read operation | Boundary |
|---|---|---|
| inspect | Export extraction coverage | Not permission to import or repair |
| list-export | Export identities/titles and selection coverage | Private IDs/titles, not an import |
| inspect-web-zip | ZIP member metadata and eligibility | No member extraction; eligibility is not source validation |
| web-branch | Explicit web conversation branch | No inference of alternate branch approval |
| replay-local | Existing retained-turn projection | supported=false is an error result, not partial success |

Tool calls select an input path, not a directory scan or arbitrary command. Paths
are resolved strictly before the check and must name a regular file under at least
one canonical allowed directory. Outside traversal, sibling-prefix paths, and
links resolving outside are refused. An inside-resolving link may be accepted.
Files exceeding the configured size are refused before invoking the reader.
Directories, missing files and special files are not accepted as tool inputs.
Protocol/schema failures and file-admission errors do not echo supplied paths.
Successful reader output can contain private text, titles, identifiers and source
metadata; fixed error handling is not a general privacy filter.

This is a preflight check, not a filesystem sandbox, path-ownership proof, immutable
snapshot or consent guarantee. A concurrent process can replace/grow a file or
change a directory/link after resolution/stat and before an existing reader opens
it. The original whole-file readers are unchanged and may materialize the file
after preflight, so the admission limit is not a strict memory bound under races.
Use only trusted, stable local input directories; do not expose this interface to
untrusted shared writers. There is no source rewriting, staging copy, file upload
or backup in this path.

ZIP inspection retains its own 64 MiB byte cap, directory-entry preflight and
existing lower-only member-size controls. It does not decompress candidate members
or bypass CRC/extraction validation for later operations. Other file tools do not
auto-detect or decompress ZIPs. The existing 1 MiB response cap still applies to
all tool results, including supported=false replay documents. Smaller selections
can reduce output but do not guarantee bounded parsing time. No checkpoint-file reader or write tool is added by directory authorization.
Explicit supplied proposals are a separate opt-in argument of review-titles as
described below.

## Review explicitly supplied proposal files

When input directories have been explicitly allowed, review-titles additionally
accepts a proposal array of 1..1000 exact file paths and optional supplied_only.
Without allowed input directories these properties are absent and rejected; the
default six-tool schemas and responses are unchanged. This reuses the existing
[CLI supplied-proposal queue](SUPPLIED_TITLE_REVIEW.md), not a new approval or
application path. A request has this generic shape after initialization:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"review-titles","arguments":{"source":"SOURCE","proposal":["PROPOSAL.json"],"supplied_only":true}}}
```

Replace SOURCE with the explicitly selected archive source and PROPOSAL.json with
an authorized existing file under an allowed directory. The example is not an
instruction to search folders or load personal proposals. Each file must contain
one ordinary proposal, not a whole queue or reviewed preview. Provider labels and
context are untrusted; they do not establish generation, consent or ownership.

Every path must pass the same canonical containment, regular-file and configured
byte preflight. Combined proposal bytes must pass a preflight budget equal to the
smaller of --max-input-bytes and the existing combined 1 MiB loader limit. The
existing loader additionally performs bounded reads and enforces its 1 MiB total
after reading, including BOM bytes. As with other file access, path and reduced
configuration-budget preflight are not atomic against concurrent replacement or
growth. Keep inputs stable. No file is rewritten or staged by this workflow.

Exact source, one candidate per conversation, valid finite JSON and the existing
content/revision/evidence checks remain in force. Wrong-source or duplicate
identities reject the queue. Stale or invalid selected candidates retain their
existing unavailable status, never silently fall back to raw excerpts. Only the
selected page receives full candidate-content validation; read unused counts and
page coverage, and retain whole-source collision checks. supplied_only selects
supplied identities before pagination and requires proposal inputs; it does not
approve them. Without supplied inputs the normal raw-excerpt queue remains intact.

The returned queue can expose private proposal wording, context and identifiers to
the selected client. Fixed read errors do not echo paths, but successful content
is not anonymized. A READY queue item is not human approval. Open and review the
normal fresh preview through the existing separately authorized CLI workflow
before application. MCP still exposes no preview-file write, apply, title write,
review-state change or checkpoint-file read.
