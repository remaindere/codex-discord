# Codex Discord

Discord를 대화 인터페이스로 사용해 일반 대화와 로컬 작업형 AI 요청을 하나의 봇에서 처리하는 개인용 어시스턴트 프로젝트입니다.

사용자가 Discord에 메시지를 보내면 봇이 요청의 성격을 판별해 다음 실행 경로 중 하나로 자동 라우팅합니다.

- **Chat 경로**: 일상 대화와 간단한 질의응답을 Direct API 및 가벼운 LLM 모델을 통하여 빠르게 처리합니다.
- **Codex 경로**: 파일·코드·프로젝트 작업, 첨부파일 분석, 실시간 검색이 필요한 요청 등을 Codex CLI로 처리합니다.

모든 대화는 원문 보존용 `raw/` 기록과 장기적으로 찾아보기 쉬운 `memory/` 지식으로 분리해 관리합니다. 세션, 사용량, 비용 상태는 `data/`에 저장하며, Codex가 작업 중 허용되지 않은 파일을 변경하지 못하도록 별도의 상태 .state.git을 활용하여 `MemoryGuard`가 변경 범위를 검사합니다.

## 주요 기능

- Discord DM, 채널, 스레드에서 대화
- 요청 내용과 이전 라우트에 따른 Chat/Codex 자동 선택
- `!chat`, `!codex` 명령으로 실행 경로 수동 지정
- `!luna`, `!sol`, `!terra` 명령으로 Codex 모델 변경
- `!reset` 또는 `!초기화`로 현재 대화 세션 초기화
- 이미지, PDF, 텍스트 첨부파일 저장 및 전처리
- Discord 대화 원문과 처리 상태를 Markdown으로 보존
- 대화별 최근 기록을 모델 문맥으로 재사용
- 장기 기억을 `facts/`와 `records/` 중심으로 관리
- 모델별 토큰 사용량과 예상 비용 누적
- 요청 단위 파일 변경 감사, 허용 경로 커밋, 보호 경로 복원
- Tavily 우선, DuckDuckGo 보조 방식의 웹 검색 도구

## 처리 흐름

```text
Discord 메시지
    ↓
사용자·채널 접근 검사
    ↓
세션 및 이전 라우트 불러오기
    ↓
Chat / Codex 자동 라우팅
    ↓
원문 기록 생성 + 첨부파일 저장·전처리
    ↓
Direct API 또는 Codex CLI 실행
    ↓
MemoryGuard 변경 감사
    ↓
답변·사용량·비용·대화 인덱스 저장
    ↓
Discord로 답변 전송
```

## 저장소 구조

```text
codex-discord/
├── bot/                 Discord 봇 애플리케이션, 설정, 테스트
├── memory/              장기 기억과 작업 기록
│   ├── facts/           오래 유지할 사용자 정보와 사실
│   ├── records/         작업 결과와 시간순 기록
│   ├── wiki_pages/      사람이 읽는 위키 페이지
│   ├── wiki_records/    구조화된 출처·관계 기록
│   └── raw -> ../raw    원문 저장소를 가리키는 읽기용 링크
├── raw/                 Discord 원문과 첨부파일의 실제 저장 위치
├── data/                세션, 사용량, 누적 비용 등 런타임 상태
├── provisioning/        AWS Bedrock/Mantle 인증 준비 스크립트
└── .state.git/          MemoryGuard가 사용하는 런타임 상태 전용 Git
```

`memory/AGENTS.md`와 `memory/WIKI_SCHEMA.md`는 메모리 구조와 쓰기 정책의 기준 문서입니다. 장기 기억을 수정하는 작업은 이 규칙을 따라야 합니다.

## 요구 사항

- Python 3.11 이상
- Discord 봇 토큰
- 로컬에서 실행 가능한 `codex` CLI
- AWS Bedrock Mantle 프로젝트 및 Secrets Manager 인증 정보
- 선택 사항: Tavily API 키

## 설치

```bash
cd ~/codex-discord
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ./bot
cp bot/src/bot/.env.example bot/src/bot/.env
```

그다음 `bot/src/bot/.env`에 Discord, 모델, AWS/Mantle, 가격표 등의 런타임 설정을 입력합니다. 실제 비밀값이 들어 있는 `.env`는 저장소에 커밋하지 마세요.

## 실행

```bash
cd ~/codex-discord
source .venv/bin/activate
python -m bot.discord_bot
```

패키지를 editable 모드로 설치하지 않았다면 다음처럼 실행할 수도 있습니다.

```bash
PYTHONPATH=bot/src python -m bot.discord_bot
```

## Discord 명령

| 명령 | 설명 |
|---|---|
| `!chat 질문` | 자동 판정을 건너뛰고 일반 대화 경로 사용 |
| `!codex 질문` | 자동 판정을 건너뛰고 Codex 경로 사용 |
| `!luna` | 현재 세션의 Codex 모델을 Luna로 변경 |
| `!sol` | 현재 세션의 Codex 모델을 Sol로 변경 |
| `!terra` | 현재 세션의 Codex 모델을 Terra로 변경 |
| `!reset`, `!초기화` | 대화 epoch를 올리고 이전 라우트 문맥 초기화 |

Chat 경로의 모델은 `CHAT_MODEL` 설정을 사용하며, 모델 변경 명령은 Codex 경로의 모델에만 적용됩니다.

## 테스트

```bash
cd ~/codex-discord/bot
python -m pytest -q
```

단위 테스트는 라우팅, 설정, 첨부파일 안전성, Discord 처리 흐름, 메모리 보호, 메시지 분할, 저장소 동작을 검사합니다. 통합 테스트는 임시 Git 저장소와 PDF를 이용하며 실제 외부 모델 API를 호출하지 않습니다. 현재(26/10/06) pytest-cov를 이용한 커버리지 측정 결과, 전체 라인 기준 85% 커버리지를 지니고 있습니다.

## 데이터와 안전 정책

- `raw/`는 원문 보존 영역이며 어시스턴트가 임의로 수정하는 장기 기억 영역이 아닙니다.
- Codex가 직접 수정할 수 있는 기본 범위는 `memory/facts/`와 `memory/records/`입니다.
- `MemoryGuard`는 요청 전후 상태를 비교해 허용된 변경만 남기고 커밋합니다.
- `bot/`, `provisioning/`, 메모리 스키마 문서 등 보호 대상이 요청 중 바뀌면 원래 내용으로 복원합니다.
- 일반 프로젝트 이력은 `.git/`, 런타임 상태 보호는 `.state.git/`이 담당합니다.

## 세부 문서

봇 내부 모듈과 파일별 역할은 `bot/README.md`에서 확인할 수 있습니다.
