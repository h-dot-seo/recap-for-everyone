# Explicit read-only MCP stdio access

This optional local entry point gives an operator-selected MCP client six archive
read tools without exposing Recap's write commands. It does not install, configure
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

## Supported tools

| Tool | Existing operation | Excluded paths |
|---|---|---|
| list | Conversation inventory | No imports or archive changes |
| find | Existing title/body search | No source-file reads or rewrites |
| show | Selected archive message view | No saved output file |
| title-history | Existing local title history | No title changes or restore |
| stats | Stored message/artifact counts | No new schema or ingestion |
| review-titles | Existing review queue and local excerpts | No proposal/checkpoint files, output save or review-state write |

Use tools/list for the exact input schemas, required identities and numeric
bounds. The archive is fixed by the launch argument; calls cannot select another
database. Unknown properties are rejected. No title, review-state, import, ingest,
apply-title, rebuild, recovery declaration or file-input tool is exposed, even
through a flag. There is no generic CLI, SQL, file or shell execution tool.

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
