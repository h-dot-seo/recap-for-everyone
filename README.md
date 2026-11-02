# recap-for-everyone

대화·에이전트 세션을 출처와 함께 보존하고 검색하는 로컬 도구와 설계입니다.
Portable, local-first conversation archives with provenance and read-only search.

## 공개 범위 / Scope

이 첫 공개본은 개인용 Recap의 **개념과 독립 실행 가능한 공통 핵심**을 분리한 출발점입니다.
개인용 시스템 전체의 배포본이나 모든 수집기의 이식판은 아닙니다.

| Included | Excluded |
|---|---|
| Normalized JSONL import, SQLite FTS search, source hash/line ledger | Real conversations, archives, databases, logs, user/device configuration |
| Existing generic local session parser and synthetic tests | Authentication bundles, browser profiles, cookies, credentials |
| Collection/index/publication separation and recovery design | Private service endpoints, account automation, SSH and scheduler setup |

## Quick start

Python 3.10+ with SQLite FTS5. No external Python dependencies, account or API key.
Run from the repository root:

```sh
python3 recap.py --db /tmp/recap-demo.sqlite ingest examples/conversations.jsonl --source demo
python3 recap.py --db /tmp/recap-demo.sqlite search orchard
python3 recap.py --db /tmp/recap-demo.sqlite stats
python3 -m unittest discover -v
```

Use a writable database path outside this public repository for your own data.
Input is UTF-8 JSONL: one message per line with `conversation_id`, `message_id`,
`role`, `timestamp`, `text` and optional `title`. Timestamps are retained as supplied;
the importer does not normalize, validate or filter dates. Search uses literal
AND-connected FTS5 terms rather than raw SQL or a user-supplied FTS expression.

`recap.py` imports only a file explicitly supplied by the operator. It does not crawl
home directories, access online accounts, collect credentials or push data anywhere.
The JSONL file is hashed from its original bytes; message rows retain the hash and
line locator. Repeated identical messages are idempotent; conflicting message
identities roll back the import batch instead of overwriting evidence.

`local_parser.py` retains the generic normalized agent-session parser and manifest
utilities. It is a library module, not an automatic collector. Its original local
snapshot schema is separate from the simplified `recap.py` schema; an adapter is
required to connect them. These are not interchangeable database formats.

## Design

See [architecture](docs/ARCHITECTURE.md), [agent workflow](SKILL.md),
[publication boundary](PUBLICATION.md), and [security](SECURITY.md).
Only synthetic examples are distributed. Do not commit your resulting database.

## Rights

No third-party code, book text, article corpus or private database was deliberately
bundled in this extraction. No license has been selected by the owner yet;
public visibility is not an open-source license. See [rights](RIGHTS.md).
