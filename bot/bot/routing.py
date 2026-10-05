from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Sized


class Route(str, Enum):
    CHAT = "chat"
    CODEX = "codex"


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    reason: str
    
@dataclass(frozen=True)
class RouteContext:
    has_attachments: bool = False
    previous_route: Route | None = None
    
_PATH_PATTERNS = (
    # Unix / POSIX absolute and relative paths
    re.compile(r"(?:^|\s)/(?:[^/\s]+/)*[^/\s]*"),
    re.compile(r"(?:^|\s)~/(?:[^/\s]+/)*[^/\s]*"),
    re.compile(r"(?:^|\s)\.{1,2}/(?:[^/\s]+/)*[^/\s]*"),

    # Windows paths
    re.compile(r"(?:^|\s)[a-z]:[\\/][^\s]+", re.IGNORECASE),
    re.compile(r"(?:^|\s)\\\\[^\s]+"),

    # Common source/config filenames
    re.compile(
        r"(?:^|\s)[^\s/\\]+\."
        r"(?:py|js|ts|tsx|jsx|java|kt|go|rs|c|cc|cpp|h|hpp|"
        r"cs|rb|php|swift|sh|bash|zsh|"
        r"json|yaml|yml|toml|ini|cfg|conf|"
        r"xml|html|css|scss|sql|md|txt|env)"
        r"(?:\s|$)",
        re.IGNORECASE,
    ),
)

WORK_TARGETS = (
    "파일",
    "폴더",
    "디렉터리",
    "경로",
    "코드",
    "프로젝트",
    "저장소",
    "repo",
    "repository",
    "로그",
    "설정",
    "테스트",
    "github",
    "git",
    "메모리",
    "링크",
    "프로세스",
    "서버",
    "데이터베이스",
    "api",
)

WORK_ACTIONS = (
    "확인",
    "찾아",
    "분석",
    "조사",
    "열어",
    "읽어",
    "실행",
    "수정",
    "고쳐",
    "만들어",
    "추가",
    "삭제",
    "옮겨",
    "올려",
    "비교",
    "검증",
    "더블체크",
    "디버그",
    "구현",
)

STRONG_WORK_TERMS = (
    "리팩터링",
    "리팩토링",
    "수정",
    "컴파일",
    "빌드",
    "스택트레이스",
    "에러 로그",
    "traceback",
    "commit",
    "branch",
    "merge",
    "pull request",
    "pr",
    "git diff",
    "테스트 코드",
    "unit test",
)

REALTIME_TERMS = (
    "날씨",
    "현재 가격",
    "최신",
    "실시간",
    "검색해",
    "찾아봐",
    "뉴스",
    "환율",
    "주가",
)

FOLLOWUP_PHRASES = (
    "그거",
    "이거",
    "저거",
    "그 파일",
    "이 파일",
    "그 코드",
    "이 코드",
    "그것",
    "이것",
    "아까",
    "방금",
    "계속",
    "이어서",
    "다시 해",
    "다시 확인",
    "수정해",
    "고쳐",
    "추가해",
    "삭제해",
    "실행해",
    "해줘",
)

def _contains_path(normalized: str) -> bool:
    return any(
        pattern.search(normalized)
        for pattern in _PATH_PATTERNS
    )

def _matches_work_intent(normalized: str) -> bool:
    has_target = any(
        target in normalized
        for target in WORK_TARGETS
    )
    has_action = any(
        action in normalized
        for action in WORK_ACTIONS
    )

    return has_target and has_action

def _matches_strong_work_term(normalized: str) -> bool:
    return any(
        term in normalized
        for term in STRONG_WORK_TERMS
    )
    
def _matches_realtime_intent(normalized: str) -> bool:
    return any(
        term in normalized
        for term in REALTIME_TERMS
    )

def _get_route_override(normalized: str) -> RouteDecision | None:
    if normalized.startswith("!chat"):
        return RouteDecision(Route.CHAT, "explicit:chat")

    if normalized.startswith("!codex"):
        return RouteDecision(Route.CODEX, "explicit:codex")

    return None

def _looks_like_followup(normalized: str) -> bool:
    return any(
        phrase in normalized
        for phrase in FOLLOWUP_PHRASES
    )

def route_request(question: str, context: RouteContext) -> RouteDecision:
    normalized = " ".join(question.casefold().split())

    # 1. Explicit route override
    override = _get_route_override(normalized)
    if override is not None:
        return override

    # 2. Attachment
    if context.has_attachments:
        return RouteDecision(Route.CODEX, "attachment")

    # 3. Path or filename
    if _contains_path(normalized):
        return RouteDecision(Route.CODEX, "filesystem:path")

    # 4. Work target + work action
    if _matches_work_intent(normalized):
        return RouteDecision(Route.CODEX, "work_intent")

    # 5. Strong technical/work term
    if _matches_strong_work_term(normalized):
        return RouteDecision(Route.CODEX, "technical_term")

    # 6. Real-time / search
    if _matches_realtime_intent(normalized):
        return RouteDecision(Route.CODEX, "realtime")

    # 7. Follow-up to an existing Codex conversation
    if (context.previous_route is Route.CODEX and _looks_like_followup(normalized)):
        return RouteDecision(Route.CODEX, "followup:codex")

    # 8. Conservative default
    return RouteDecision(Route.CODEX, "fallback:codex")