# Bot

`bot/`은 Discord 메시지 수신부터 라우팅, 모델 호출, 첨부파일 처리, 기록 저장, 비용 집계, Codex Agent 실행 중 보호 영역에 대한 파일 변경 감지 및 복구를 지원하는 Python 애플리케이션입니다.

## 디렉터리 구조

```text
bot/
├── pyproject.toml
├── requirements.txt
├── src/
│   └── bot/
│       ├── .env.example
│       ├── __init__.py
│       ├── attachments.py
│       ├── config.py
│       ├── discord_bot.py
│       ├── memory_guard.py
│       ├── message_splitter.py
│       ├── prompts.py
│       ├── routing.py
│       ├── routing.toml
│       ├── web_search.py
│       ├── models/
│       └── storage/
└── tests/
    ├── unit/
    └── integration/
```

## 핵심 모듈

### `src/bot/discord_bot.py`

애플리케이션의 진입점이자 전체 요청 처리 파이프라인입니다.

- `.env` 로드와 Discord 클라이언트 시작
- 허용 사용자·채널 검사
- DM, 채널, 스레드별 세션 키 생성
- 모델 변경 및 세션 초기화 명령 처리
- routing 결과에 따라 Direct API 또는 Codex CLI 호출
- 원문 기록, 첨부파일, 대화 이력, 비용 정보 저장
- `MemoryGuard` 감시 결과 처리
- 긴 답변을 여러 Discord 메시지로 나눠 전송
- 단계별 오류 기록과 사용자용 오류 ID 생성

### `src/bot/config.py`

환경변수를 타입이 있는 `Settings` 객체로 변환하고 런타임 설정을 검증합니다.

- 프로젝트, 메모리, 원문, 데이터 경로
- Discord 토큰과 접근 허용 목록
- Codex/Chat 모델과 제한값
- 첨부파일 개수·용량·PDF 페이지 제한
- 대화 이력 길이와 Direct API 출력 제한
- AWS/Mantle 인증 설정
- 모델별 토큰 가격표

### `src/bot/routing.py`

사용자 요청을 `chat` 또는 `codex`로 분류합니다.

판정 우선순위는 대략 다음과 같습니다.

1. `!chat`, `!codex` 명시적 지정
2. 첨부파일과 파일시스템 경로
3. 날씨·뉴스·환율·검색 등 실시간 요청
4. 직전 Codex 요청의 후속 작업
5. 기술 용어
6. 작업 대상과 작업 동사의 조합
7. 설정된 weight score
8. 일반 대화 기본값

### `src/bot/routing.toml`

라우터가 사용하는 임계값, 분류별 weight, 한국어·영어 어휘 목록을 보관합니다.

만약 라우팅 행동을 조정한다면, Python 로직과 함께 검토 및 수정해 주세요.

### `src/bot/prompts.py`

Codex에 전달할 시스템 문맥을 구성합니다.

- 최근 대화 기록 삽입
- 첨부파일에서 추출한 텍스트와 오류 정보 정리
- 비전 기능이 켜진 경우 이미지 경로 수집
- 장기 메모리의 쓰기 범위와 schema 확인 규칙 전달

### `src/bot/attachments.py`

Discord 첨부파일의 안전한 저장과 전처리를 담당합니다.

- 파일명에서 경로 요소와 위험 문자를 제거
- 첨부 개수, 파일별 크기, 전체 크기 제한
- 이미지 파일을 비전 입력 대상으로 표시
- 텍스트 파일의 제한된 미리보기 추출
- 텍스트 추출이 가능한 PDF는 텍스트 추출, 불가할 시에는 이미지로 처리
- 스캔형 PDF를 제한된 수의 페이지 이미지로 렌더링
- 개별 첨부 처리 실패를 전체 요청 실패와 분리하여 처리

### `src/bot/memory_guard.py`

Codex 요청 전후의 파일 상태를 비교하여 허용된 영역 이외의 파일 변경을 막습니다.

- `.state.git`을 이용한 상태 경로 추적
- 요청 전에 존재하던 수정 사항 보존
- 허용된 메모리·상태 경로만 변경으로 인정
- `bot/`과 `provisioning/` 보호
- 메모리 정책·스키마 문서 등 고정 경로 보호
- 요청 중 생성된 비허용 파일 제거 또는 기존 파일 복원
- 이번 요청에서 허용된 파일만 선택적으로 커밋

일반 프로젝트 Git과 런타임 상태 Git의 역할이 다름에 유의하세요.

이 모듈은 가급적 변경을 권장하지 않으며, 변경할 시 반드시 동작 방식을 완전히 이해하고 하시길 바랍니다.

### `src/bot/message_splitter.py`

Discord 메시지 길이 제한을 넘는 답변을 문단, 줄바꿈, 공백 순으로 가능한 자연스럽게 분할합니다.

### `src/bot/web_search.py`

명령행에서 사용할 수 있는 웹 검색 도구입니다.

- Tavily를 우선 사용
- Tavily 실패 시 DuckDuckGo 검색으로 대체(보통 무료요금제 털린 경우)
- 제목, URL, 검색 요약 출력
- 모든 검색이 실패하면 오류 코드 반환

### `src/bot/__init__.py`

`bot` Python 패키지를 선언합니다.

## 모델 어댑터

### `src/bot/models/codex_cli.py`

로컬 `codex exec`를 JSON 이벤트 모드로 실행합니다.

- 지정 모델과 작업 디렉터리 사용
- 설정에 따라 이미지 입력 전달
- 실행 시간 제한
- 에이전트 최종 메시지와 사용량 이벤트 추출
- CLI 오류와 빈 응답을 explicit exception 으로 변환

### `src/bot/models/direct_chat.py`

일반 대화 경로를 AWS Bedrock Mantle의 OpenAI 호환 Responses API에 연결합니다.

- Secrets Manager에서 bearer token 조회 및 캐시
- 최근 일반 대화 이력을 Responses 입력 형식으로 전달
- 인증 실패 시 토큰과 클라이언트 캐시를 갱신한 뒤 한 번 재시도
- 응답 상태와 출력 길이를 로그에 기록
- 빈 텍스트 응답을 오류로 처리

### `src/bot/models/usage.py`

Codex CLI와 Direct API가 서로 다르게 반환하는 토큰 사용량을 공통 형식으로 정규화합니다.

### `src/bot/models/__init__.py`

모델 어댑터 하위 패키지를 선언합니다.

## 저장소 모듈

### `src/bot/storage/atomic.py`

텍스트와 JSON을 임시 파일에 쓴 뒤 atomic 하게 교체합니다. 중간 실패로 상태 파일이 부분 기록되는 위험을 줄입니다.

### `src/bot/storage/sessions.py`

Discord 대화 단위의 상태를 `sessions.json`에 관리합니다.

- 대화 epoch
- 현재 Codex 모델
- 마지막 route
- async lock을 통한 동시 수정 방지

### `src/bot/storage/history.py`

대화별 raw 기록 인덱스를 JSONL로 유지하고 모델별 문맥 형식으로 최근 기록을 불러옵니다.

- Codex에는 원문 Markdown 기록 묶음 제공
- Direct API에는 user/assistant 메시지 배열 제공
- 실패한 요청 제외
- 기록 개수와 문자 수 제한 적용

### `src/bot/storage/raw_records.py`

Discord 요청 하나를 Markdown 원문 기록으로 생성하고 상태를 갱신합니다.

- `pending`, `answered`, `failed` 상태
- Discord 메시지·채널·사용자·대화 ID
- 선택된 route와 model
- 질문, 첨부파일, 답변
- 실패 단계, 오류 ID, 오류 종류, 완료 시각

### `src/bot/storage/costs.py`

정규화된 토큰 사용량과 모델 가격표로 요청별 예상 비용을 계산합니다.

- 요청별 사용량을 JSONL에 추가
- 누적 예상 비용 상태 저장
- 설정된 비용 구간을 넘을 때 알림 임계값 반환
- async lock을 이용하여 동시 비용 기록을 순차 처리

### `src/bot/storage/__init__.py`

저장소 하위 패키지를 선언합니다.

## 설정 파일

### `src/bot/.env.example`

실행에 필요한 환경변수 예시입니다. 실제 값은 같은 위치의 `.env`를 생성하여 넣어주세요.

#### `.env`은 원격 저장소에 올라가지 않도록 각별히 주의하세요.

### `pyproject.toml`

패키지 이름, 빌드 백엔드, `src/` 패키지 검색 경로, `routing.toml` 패키지 데이터, pytest 기본 경로를 정의합니다.

### `requirements.txt`

Discord, OpenAI 호환 API, AWS SDK, PDF 처리, 환경변수 로드, 웹 검색에 필요한 Python dependency 목록입니다.

## 테스트

### 단위 테스트

| 파일 | 검사 대상 |
|---|---|
| `tests/unit/test_discord_bot.py` | 명령 처리, 세션 키, 접근 통제, 라우트별 요청 흐름, 실패 처리 |
| `tests/unit/test_routing.py` | 명시적 라우트, 경로·기술·실시간·후속 요청 판정 |
| `tests/unit/test_config.py` | 환경변수 파싱, 필수 모델, 양수 제한값 |
| `tests/unit/test_attachments.py` | 파일명 정리, 경로 탈출 방지, 용량 제한 |
| `tests/unit/test_memory_guard.py` | 허용·고정·보호 경로의 보존과 복원 |
| `tests/unit/test_message_splitter.py` | 답변 분할 경계와 빈 입력 |
| `tests/unit/storage/test_storage.py` | 세션 호환성, 모델·라우트 유지, 초기화 |

### 통합 테스트

| 파일 | 검사 대상 |
|---|---|
| `tests/integration/test_git.py` | 실제 임시 Git에서 기존 dirty 상태 보존과 요청 변경만 커밋 |
| `tests/integration/test_pdf.py` | 큰 PDF, 페이지 제한, 렌더링 제한, 오류 격리 |

## 설치와 실행

```bash
cd ~/codex-discord
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ./bot
cp bot/src/bot/.env.example bot/src/bot/.env
python -m bot.discord_bot
```

## 검증

```bash
cd ~/codex-discord/bot
python -m pytest -q
```

환경변수와 외부 서비스 연결 없이도 대부분의 단위·통합 테스트를 실행할 수 있습니다. (올바른 설치 검증 용)

실제 Discord 봇 실행에는 `.env` 파일이 필요하며, 값 설정이 필요합니다. `.env.example` 파일을 참고하여 .env 파일을 생성 및 bot 폴더 내부에 위치시켜 주세요.