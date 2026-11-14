# recap-for-everyone 한국어 안내

이 문서는 [README](../README.md)의 한국어 안내입니다. 명령, 파일 이름, 식별자는 원문
그대로 두었고, 상세 동작은 영어 안내서에 있습니다. 두 문서가 다르면 영어 안내서와
실제 `--help` 출력이 기준입니다.

## 목적

recap-for-everyone은 ChatGPT 웹 내보내기와 Codex 같은 로컬 에이전트 세션 기록을
**내 컴퓨터 안에서** 보존하고 검색하는 도구입니다. 원본 파일의 바이트 해시와 줄
위치를 함께 저장해 어떤 메시지가 어느 파일의 어느 줄에서 왔는지 추적할 수 있고,
읽기 전용으로 검색합니다. 대화에 붙이는 제목은 **로컬 표시 제목**이며, 제안 →
미리보기 → 검토 → 적용의 순서로만 바뀌고 이력이 남습니다. 백업 전에 보관 상태를
선언하고 복원 뒤에 그 복원본을 검증하는 명령도 포함합니다.

## 공개 범위

이 첫 공개본은 개인용 Recap의 개념과 독립 실행 가능한 공통 핵심을 분리한
출발점입니다. 개인용 시스템 전체의 배포본이나 모든 수집기의 이식판은 아닙니다.

| 포함 | 제외 |
|---|---|
| 정규화 JSONL 가져오기, SQLite FTS 검색, 원본 해시·줄 위치 대장 | 실제 대화, 보관소, 데이터베이스, 로그, 사용자·기기 설정 |
| 범용 로컬 세션 파서와 합성 데이터 테스트 | 인증 번들, 브라우저 프로필, 쿠키, 자격 증명 |
| 검토를 거친 로컬 표시 제목 제안, 미리보기·적용, 제목 이력 | 원격·일괄 이름 변경, 이 저장소 안의 모델 호출과 의미 요약 |
| 수집·색인·공개의 분리와 복구 설계, `declare-recovery` 매니페스트와 복원본 `rehearse-recovery` 영수증 | 비공개 서비스 엔드포인트, 계정 자동화, SSH·스케줄러 설정, 원격 백업 가져오기와 복호화 |

예제는 모두 합성 데이터입니다. 실제 대화, 계정, 백업 시스템으로 검증했다는 주장은
하지 않습니다.

## 설치와 빠른 시작

`pip install`, 모델, 계정, API 키가 필요하지 않습니다. 표준 라이브러리만 사용하며
Python 3.10 이상과 SQLite FTS5가 필요합니다. CI는 Ubuntu와 Windows에서 Python 3.10과
3.12로 실행됩니다. 자세한 절차는 [설치와 런타임 점검](INSTALL.md)에 있습니다.

1. 기본 브랜치 `main`을 받습니다. 여기서 설명하는 작업 흐름은 2026-11-08부터 `main`에
   있습니다. 그 이전에 받은 사본에는 일부 명령이 없습니다.
2. 사용할 Python 실행기를 하나 정합니다. 아래의 `python`은 환경에 따라 `python3`나
   `py -3`로 바꿔 쓰되, 스크립트 경로와 나머지 인자는 그대로 둡니다.
3. 저장소 루트에서 런타임을 점검합니다.

```sh
python runtime_check.py
python recap.py --help
python verify_manifest.py
```

`runtime_check.py`는 `status: "READY"`를 보고해야 합니다. 이 점검은 메모리 안에서
FTS5 표를 하나 만들어 보는 것이며, 내보내기 파일이나 보관소를 열지 않습니다.

이미 정규화된 JSONL을 가져와 검색하는 가장 짧은 예는 다음과 같습니다. 데이터베이스는
저장소 바깥의 새 디렉터리에 둡니다.

```sh
mkdir ../recap-normalized-demo
python recap.py --db ../recap-normalized-demo/archive.sqlite ingest examples/conversations.jsonl --source demo
python recap.py --db ../recap-normalized-demo/archive.sqlite search orchard
python recap.py --db ../recap-normalized-demo/archive.sqlite stats
python -m unittest discover -v
```

웹 내보내기 하나를 가져와 제목까지 확인하는 공통 흐름은 다음과 같습니다.

```sh
python recap.py inspect examples/web-export.json --format web
python recap.py --db ../demo.sqlite import examples/web-export.json --format web --source demo
python recap.py --db ../demo.sqlite list --source demo
python recap.py --db ../demo.sqlite find orchard --source demo
python recap.py --db ../demo.sqlite show --source demo --conversation synthetic-chat
python recap.py --db ../demo.sqlite suggest-title --source demo --conversation synthetic-chat
python recap.py --db ../demo.sqlite title --source demo --conversation synthetic-chat
```

처음이라면 [Start here](START_HERE.md)를 따라가면 됩니다. 합성 대화 24개로 ZIP
선택, 가져오기, 검토 대기열, 보류와 재방문, 로컬 제목 변경 한 번, 검색까지 한 번에
연습할 수 있고, 그 명령들은 테스트가 그대로 실행합니다. 웹 분기와 Codex 유지 턴에서
제목을 뽑는 예는 [두 형식 제목 안내](TITLE_WALKTHROUGH.md)에 있습니다.

## 주요 명령

`--db DB`는 하위 명령 앞에 씁니다. `inspect`, `list-export`, `inspect-web-zip`,
`prepare-web-export`, `replay-local`, `web-branch`, `rehearse-recovery`는 데이터베이스
없이 실행됩니다. 모든 명령의 정확한 usage 줄은 [명령 참조](COMMANDS.md)에, 기능별
설명은 [작업 흐름](WORKFLOWS.md)에 있습니다.

| 할 일 | 명령 | 안내서 |
|---|---|---|
| 런타임 점검 | `python runtime_check.py`, `python recap.py --help`, `python verify_manifest.py` | [INSTALL.md](INSTALL.md) |
| 내려받은 ZIP에서 대화 파일 고르기 | `recap.py inspect-web-zip ZIP`, `recap.py prepare-web-export ZIP --member NAME --output NEW_FILE` | [WEB_ZIP_INVENTORY.md](WEB_ZIP_INVENTORY.md), [PREPARE_WEB_EXPORT.md](PREPARE_WEB_EXPORT.md) |
| 가져오기 전에 ID와 범위 확인 | `recap.py list-export INPUT --format FORMAT`, `recap.py inspect INPUT --format FORMAT` | [EXPORT_INVENTORY.md](EXPORT_INVENTORY.md), [INPUT_SCOPE.md](INPUT_SCOPE.md) |
| 내보내기 또는 정규화 JSONL 가져오기 | `recap.py --db DB import INPUT --format FORMAT --source SOURCE`, `ingest`, `check-import` | [IMPORT_CONFLICTS.md](IMPORT_CONFLICTS.md) |
| 정규화 메시지 내보내기 | `recap.py --db DB export-normalized --source SOURCE --output NEW_JSONL` | [EXPORT_NORMALIZED.md](EXPORT_NORMALIZED.md) |
| 현재 보관소 구조 확인 | `recap.py --db DB describe-schema` | [SCHEMA.md](SCHEMA.md) |
| 검색과 읽기 | `recap.py --db DB find QUERY`, `list`, `show --source SOURCE --conversation ID`, `search`, `stats` | [SEARCH_EXCERPTS.md](SEARCH_EXCERPTS.md), [MESSAGE_SELECTION.md](MESSAGE_SELECTION.md) |
| 로컬 제목 제안 | `recap.py --db DB suggest-title`, `suggest-branch-title`, `suggest-replay-title`, `suggest-attributed-title` | [TITLE_WALKTHROUGH.md](TITLE_WALKTHROUGH.md) |
| 제안 페이지 검토와 결정 기록 | `recap.py --db DB review-titles --source SOURCE`, `review-state` | [TITLE_REVIEW_QUEUE.md](TITLE_REVIEW_QUEUE.md), [TITLE_REVIEW_STATE.md](TITLE_REVIEW_STATE.md) |
| 미리보기, 적용, 이력 확인 | `recap.py --db DB preview-title PROPOSAL`, `apply-title REVIEWED`, `title`, `title-history` | [TITLE_REVIEW_HINTS.md](TITLE_REVIEW_HINTS.md), [TITLE_HISTORY_VIEW.md](TITLE_HISTORY_VIEW.md) |
| 웹 분기 읽기, 완료 턴 투영 | `recap.py web-branch INPUT --conversation ID`, `recap.py replay-local INPUT` | [WORKFLOWS.md](WORKFLOWS.md#titles-from-a-verified-branch-retained-turns-or-source-labels) |
| 제공자 중립 제목 요청 준비(오프라인) | `python title_adapter.py --db DB --source SOURCE --conversation ID prepare`, `complete-response` | [TITLE_ADAPTER.md](TITLE_ADAPTER.md), [SAVED_TITLE_RESPONSE.md](SAVED_TITLE_RESPONSE.md) |
| 수동 제목 이전 계획 | `recap.py --db DB export-title-plan`, `check-title-plan`, `title-adapter-dry-run`, `title-adapter-simulate` | [TITLE_TRANSFER.md](TITLE_TRANSFER.md) |
| 백업 전 선언, 복원 후 리허설 | `recap.py --db DB declare-recovery --output MANIFEST`, `recap.py rehearse-recovery MANIFEST --restored-db COPY --output RECEIPT` | [RECOVERY_REHEARSAL.md](RECOVERY_REHEARSAL.md) |

제목 흐름의 핵심 규칙은 하나입니다. `suggest-*`와 `review-titles`는 제안만 만들고,
`preview-title`은 보관소를 읽기 전용으로 확인해 예상 리비전을 돌려주며, 저장된
미리보기 문서를 직접 열어 본 뒤에만 `apply-title`로 로컬 표시 제목 하나를 바꿉니다.
제안·대기열·미리보기는 `--output NEW_JSON`으로 저장할 수 있고, 이미 있는 경로는
덮어쓰지 않고 거부합니다. 적용된 변경은 제목 이력에 남고, 원문 메시지와 원본
해시는 바뀌지 않습니다.

저장소 루트에는 진입점만 있습니다: `recap.py`, 위 표와 [명령 참조](COMMANDS.md)의
독립 스크립트, `runtime_check.py`, `verify_manifest.py`, `audit_publication.py`. 루트의
독립 스크립트는 같은 이름의 `recaplib/` 모듈을 불러오는 호환 진입점이므로 문서의 명령은
그대로 동작합니다. 구현 모듈은 `recaplib/` 패키지에, 테스트는 `tests/` 패키지에 있고,
테스트는 루트에서 `python -m unittest discover -v`로 실행합니다.

## 경계와 하지 않는 것

- **원본 앱의 이름을 바꾸지 않습니다.** 제목은 로컬 표시 제목입니다. ChatGPT나 Codex
  세션의 실제 제목은 바뀌지 않으며, `export-title-plan`은 사람이 직접 옮길 때 쓰는
  점검표를 `NOT_EXECUTED` 상태로 내보낼 뿐입니다. `title-adapter-simulate`는 메모리
  안의 모의 계약 리허설이고 어떤 서비스에도 연결되지 않습니다.
- **모델을 호출하지 않습니다.** 기본 제목 제안은 사용자 메시지에서 뽑은 결정적
  발췌(최대 80 코드 포인트)이며 의미 요약이 아닙니다. `title_adapter.py`의 외부
  경로는 설정과 동의가 모두 있어도 `EXTERNAL_NOT_CONFIGURED`를 돌려주고 아무것도
  보내지 않습니다.
- **계정이나 폴더를 뒤지지 않습니다.** 운영자가 명시한 파일만 읽습니다. 홈 디렉터리
  탐색, 온라인 계정 접근, 자격 증명 수집, 외부 전송은 없습니다.
- **증거를 고쳐 쓰지 않습니다.** 가져오기는 원본 바이트를 해시하고 모든 텍스트
  분기와 롤백된 기록을 그대로 보존합니다. 같은 식별자에 다른 내용이 들어오면
  덮어쓰지 않고 그 가져오기를 거부합니다. 검색과 보기는 `mode=ro`와
  `PRAGMA query_only=ON`으로 열립니다.
- **복구를 증명하지 않습니다.** `rehearse-recovery`가 통과해도 그 복원본이 매니페스트와
  일치한다는 뜻일 뿐입니다. 원격 백업의 완전성, 키의 안전, 다음 복원의 성공은
  확인되지 않으며, Git 참조나 push 메시지로 복구를 검증했다고 말해서는 안 됩니다.
  원격 가져오기, 복호화, 키 보관, 스케줄링은 이 저장소 바깥에 있습니다.
- **출력은 비공개 자료입니다.** JSON 출력과 저장 문서에는 메시지 본문, 제목, ID,
  해시가 들어갈 수 있습니다. 데이터베이스와 함께 저장소 바깥의 비공개 디렉터리에
  두고 공개 저장소나 공유 폴더에 올리지 않습니다.
- **라이선스는 아직 없습니다.** 공개 저장소라는 사실이 오픈소스 라이선스는 아닙니다.
  [RIGHTS.md](../RIGHTS.md)를 보십시오.

## 문서 색인

- [시간 기준 조회](BROWSE_BY_TIME.md): `list --order recent|oldest`, UTC `--from/--until`. 원본 시간은 바꾸지 않으며 명시적 해석 규칙과 미해석 개수를 표시합니다.

- [합성 adapter 실행 예제](ADAPTER_GUIDE.md): 가상의 입력 변환, 원본·변환본 해시 영수증, 실행 검증 안내와 유지관리자 체크리스트. 실제 서비스 호환이나 코드 재사용 권한을 뜻하지 않습니다.

- [정규화 JSONL 입력 계약](NORMALIZED_JSONL.md): 필드, 허용·거부 규칙, 변환 파일 기준 출처. `inspect --format normalized`와 `check-import --format normalized`는 읽기 전용으로 충돌 개수를 보여 줍니다. 이후 `ingest --expected-sha256 HASH`로 같은 바이트인지 확인할 수 있습니다. 대화 선택은 지원하지 않습니다. 실제 서비스와 무관한 [합성 adapter 실행 예제](ADAPTER_GUIDE.md)는 별도 가이드에서 확인할 수 있습니다.

- [현재 보관소 구조와 SQL](SCHEMA.md): 테이블·열·지연 원장과 읽기 전용 metadata 검사.

- [START_HERE.md](START_HERE.md): ZIP 또는 로컬 파일에서 검색 가능한 로컬 제목까지, 테스트되는 첫 실행.
- [INSTALL.md](INSTALL.md): 코드 받기, Python 실행기 선택, SQLite FTS5 점검.
- [TITLE_WALKTHROUGH.md](TITLE_WALKTHROUGH.md): 웹 분기와 Codex 유지 턴 제목을 한 CLI로 다루는 두 형식 안내.
- [COMMANDS.md](COMMANDS.md): 모든 스크립트와 하위 명령의 정확한 usage 줄.
- [WORKFLOWS.md](WORKFLOWS.md): 기능별 설명을 작업 흐름 단위로 묶은 안내.
- [ARCHITECTURE.md](ARCHITECTURE.md): 권위 계층, 식별자, 가져오기 트랜잭션, 읽기 전용 경계, 복구 수용 기준.
- [WEB_ZIP_INVENTORY.md](WEB_ZIP_INVENTORY.md): 압축을 풀지 않고 내려받은 ZIP의 대화 JSON 부분 고르기.
- [PREPARE_WEB_EXPORT.md](PREPARE_WEB_EXPORT.md): ZIP 멤버 하나를 검증해 새 로컬 파일로 만들기.
- [EXPORT_INVENTORY.md](EXPORT_INVENTORY.md): 가져오기 전 ID·제목·범위 목록, 기억나는 문구로 세션 찾기.
- [INPUT_SCOPE.md](INPUT_SCOPE.md): 지원 형식, 대화 하나만 가져오기, 해시 고정, 실패 경계.
- [IMPORT_CONFLICTS.md](IMPORT_CONFLICTS.md): 보관소를 바꾸지 않고 재가져오기 충돌 진단.
- [SOURCE_TEXT_COMPATIBILITY.md](SOURCE_TEXT_COMPATIBILITY.md): UTF-8 서명과 물리적 줄 처리.
- [SEARCH_EXCERPTS.md](SEARCH_EXCERPTS.md): 일치 위치 중심 발췌, 오프셋, 범위 필드.
- [SEARCH_PAGINATION.md](SEARCH_PAGINATION.md): 커서로 대화 검색 이어가기.
- [CANONICAL_UNICODE_SEARCH.md](CANONICAL_UNICODE_SEARCH.md): 정규형이 다른 유니코드 텍스트의 선택적 일치.
- [EXPORT_SCOPED_SEARCH.md](EXPORT_SCOPED_SEARCH.md): 원본 내보내기 해시 하나로 본문 검색 범위 제한.
- [TITLE_HISTORY_SEARCH.md](TITLE_HISTORY_SEARCH.md): 이전 로컬 제목으로 대화 찾기.
- [OMITTED_SEARCH_MESSAGES.md](OMITTED_SEARCH_MESSAGES.md): 검색 샘플에서 빠진 일치 메시지 훑어보기.
- [MESSAGE_SELECTION.md](MESSAGE_SELECTION.md): 메시지 하나, 제한된 페이지, 주변 메시지 읽기.
- [TITLE_DOCUMENT_FILES.md](TITLE_DOCUMENT_FILES.md): `--output`으로 제안·대기열·미리보기를 덮어쓰기 없이 저장.
- [TITLE_REVIEW_QUEUE.md](TITLE_REVIEW_QUEUE.md): 로컬 제목 제안 페이지 검토.
- [TITLE_REVIEW_HINTS.md](TITLE_REVIEW_HINTS.md): 참고용 힌트, 직접 쓴 제목, 범위 안의 메시지 선택, 유니코드 발췌 한계.
- [TITLE_REVIEW_EVIDENCE.md](TITLE_REVIEW_EVIDENCE.md): 미리보기 단계에서 인용 증거를 선택적으로 보기.
- [TITLE_REVIEW_STATE.md](TITLE_REVIEW_STATE.md): open·skipped·deferred 결정의 명시적 기록.
- [TITLE_HISTORY_VIEW.md](TITLE_HISTORY_VIEW.md): 메시지 본문을 열지 않고 이전 로컬 제목 보기.
- [SUPPLIED_TITLE_REVIEW.md](SUPPLIED_TITLE_REVIEW.md): 웹·로컬·외부 제안 파일을 함께 검토.
- [SOURCE_ATTRIBUTED_TITLES.md](SOURCE_ATTRIBUTED_TITLES.md): 사용자 출처로 표시된 부분에서 제목 만들기.
- [ATTRIBUTED_MESSAGE_SELECTION.md](ATTRIBUTED_MESSAGE_SELECTION.md): 출처 표시가 있는 특정 요청이나 반복 위치 선택.
- [ADAPTER_MESSAGE_SELECTION.md](ADAPTER_MESSAGE_SELECTION.md): 선택한 요청을 저장 응답 어댑터 흐름에서 사용.
- [TITLE_ADAPTER.md](TITLE_ADAPTER.md): 제공자 중립 제목 생성 계약, 로컬·모의 실행만 포함.
- [SAVED_TITLE_RESPONSE.md](SAVED_TITLE_RESPONSE.md): 별도로 얻은 응답을 검토 가능한 제안으로 바꾸기.
- [TITLE_TRANSFER.md](TITLE_TRANSFER.md): 모의 전용 플랫폼 제목 이전 계약.
- [RECOVERY_REHEARSAL.md](RECOVERY_REHEARSAL.md): 백업 전 선언, 복원본 리허설, 매니페스트와 영수증.
- [VALIDATION_HISTORY.md](VALIDATION_HISTORY.md): 첫 공개 이후의 날짜별 검증 기록 전체.

설계와 경계 문서: [SKILL.md](../SKILL.md)(에이전트 작업 지침), [PUBLICATION.md](../PUBLICATION.md)
(공개 범위 기록), [SECURITY.md](../SECURITY.md), [RIGHTS.md](../RIGHTS.md),
[VALIDATION.md](../VALIDATION.md)(현재 검증 상태).

## 읽기 전용 HTML·Markdown 보기

`recap.py --db DB render --source SOURCE --conversation ID --format html --output NEW_FILE`로 한글과 이모지가 읽히는 로컬 HTML을 저장합니다. `show`와 같은 메시지 선택자를 사용하며 기존 파일을 덮어쓰지 않습니다. stdout에는 본문 없는 ASCII 영수증만 표시됩니다. HTML은 제목 적용이나 검토 승인이 아닙니다. [표시 규칙과 경계](RENDER_VIEWS.md)를 확인하고 비공개 출력은 공개 저장소 밖에 보관하세요.

같은 명령에 `--format markdown`을 지정하면 제목·식별자·타임스탬프·선택 범위·출처를
포함한 모든 공급값과 본문을 코드 펜스 안에 넣은 Markdown을 저장합니다. 펜스 길이는
각 블록의 가장 긴 연속 백틱보다 길며 정보 문자열은 `text`로 고정됩니다. HTML과
같은 제어·형식 문자 표시 규칙, 16 MiB 출력 제한과 배타적 생성 규칙을 사용합니다.
모든 Markdown 뷰어의 안전성이나 동일한 표시를 보장하지 않으며, 대화나 응답의
완료 여부를 추정하지 않습니다. 정확한 공급 근거는 기존 `show` JSON으로 확인하세요.
실행 가능한 예제와 경계는 [Markdown 안내](RENDER_MARKDOWN.md)에 있습니다.

## 읽기 전용 구조 검사

직접 SQL을 읽기 전 [현재 SQLite 구조](SCHEMA.md)를 확인하세요. 읽기 전용
`describe-schema`는 지연 테이블을 생성하지 않으며, 개수와 스키마 이름은
비공개 정보일 수 있습니다. 무결성 검사나 구조 안정성 보장은 아닙니다.

## 저장한 제목 검토 대기열 보기

`recap.py render-queue QUEUE.json --output NEW_FILE`은 저장한 대기열 JSON을
읽기 전용 HTML로 표시합니다. `--db`는 받지 않으며 원본 파일의 SHA-256, 항목 순서,
제목 경고, 충돌 수, UNAVAILABLE 사유를 유지합니다. 입력과 출력은 각각 16 MiB
한도이며 기존 출력 경로를 덮어쓰지 않습니다. 브라우저 편집은 검토 산출물이 아니며
적용이나 최신성 확인을 대신하지 않습니다. 원본 JSON으로 새 preview-title을 검토한
뒤 별도로 적용하세요. 개인정보가 들어갈 수 있으므로 공개·공유 폴더 밖에 보관하세요.
[실행 검증한 합성 예제와 경계](RENDER_QUEUE.md)를 참고하세요.

## 정규화 JSONL 내보내기

`recap.py --db DB export-normalized --source SOURCE --output NEW_JSONL`은
한 소스 전체를 단일 읽기 전용 스냅숏에서 전역 삽입 순서로 내보냅니다.
`--conversation ID`로 대화 하나를 지정할 수 있습니다. 원제목과 메시지 본문을
포함하는 개인 파일이며 기존 경로를 덮어쓰지 않습니다. 출처 대장, 부모 트리,
로컬 제목 이력과 검토 상태는 제외됩니다. 원본 내보내기나 백업을 대체하지
않습니다. [실행 가능한 안내](EXPORT_NORMALIZED.md)를 참고하세요.

Read-only SQLite connections now apply and read back defense-in-depth settings;
see [security](../SECURITY.md). Write connections are unchanged.

Use [automated declared-object rebuild](AUTOMATED_REBUILD.md)
with `python recap.py rebuild-archive MANIFEST --plan PLAN --objects DIR
--new-db NEW.sqlite --output NEW.json [--text]`. It never opens the original DB;
it exclusively publishes a checked new DB from explicit replay steps. Declared
title history is not rebuilt, and review state remains undeclared/unrestored.
