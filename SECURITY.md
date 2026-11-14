# Security and publication boundary

Keep actual user/research data outside this public repository. The examples are
synthetic and contain no real conversations, participants or researcher corpus.
Do not commit credentials, cookies, profiles, authentication bundles, SSH keys,
private hosts, personal account configuration, logs, original documents or databases.
Encrypted private material is also excluded from this code-only release.

The repository has a new public history; it does not import a private repository's
commit graph, deleted files, branches, tags or Git LFS objects. The publication
manifest enumerates the reviewed files. Review future diffs and staged files, not
only the current working tree. A .gitignore is not a data-loss prevention system.

`audit_publication.py` detects a small set of prohibited file types and common secret
patterns. A pass is not proof of anonymity, copyright clearance or absence of all
secrets. Human review of the actual selected files remains required. It does not
redact source material or turn a private corpus into a safe public release.

Do not disclose a vulnerability containing private information in a public issue.
Use an owner-configured private security channel when available. No contact address
or account-specific reporting endpoint is bundled in this release.

## Read-only SQLite connection protections

Archive reads and metadata-only SQLite artifact inspection use connection-local
`query_only=ON`, `trusted_schema=OFF` and `cell_size_check=ON`. Python/SQLite
builds exposing `SQLITE_DBCONFIG_DEFENSIVE` also enable it. Settings are read back;
unavailable features are reported as `UNAVAILABLE`, not assumed enabled. A
supported protection that remains disabled fails the connection setup. Failed
archive connection setup closes the connection. No persistent DB setting changes.

Recovery rehearsal records these actual states inside the `integrity_check`
check's `sqlite_protections` detail (not a new top-level receipt field). If opening
fails before read-back, values remain `NOT_CHECKED`. A schema view that invokes
non-innocuous functions may now be rejected, even if a plain SQLite connection
would read it. Shipped tables and FTS queries remain supported.

This is defense in depth, **not a sandbox for hostile database files**. There is
no SQL CPU/memory budget or protection against hostile concurrent directory
changes. Write connections for ingest, title history and review state are unchanged
and assume an operator-created archive. These protections do not authenticate
content, validate all semantics or prove recovery completeness.

## Regular-file admission for existing bounded readers

ZIP archive input, recovery manifest input, supplied proposal files and adapter
request/response documents now check file type and the existing byte budget before
opening. Directories, FIFOs, sockets and device paths are rejected; this avoids
blocking on an ordinary FIFO path. Symlinks to regular files retain the existing
follow behavior. Recovery's separate restored-archive/object symlink refusal is
unchanged. Missing files retain their existing errors; adapter readers still map
failures to their existing AdapterError code. New type errors omit the input path.

No budget is enlarged or newly imposed: ZIP/manifests retain 64 MiB, supplied
proposals retain their combined 1 MiB, and adapter documents retain their existing
per-kind limits. Each reader still performs one bounded read and checks actual
length afterward, so growth after stat cannot silently exceed that read budget.
The stat/open pair is not an atomic lease. Hostile concurrent namespace changes,
symlink swaps, special-file replacement between stat/open and total process memory
are not defended or bounded by this preflight. File contents are never changed.

This change does not cover all export/title/plan readers and does not establish
universal input admission or a sandbox. It preserves their current behavior.
