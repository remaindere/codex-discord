from __future__ import annotations

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


TOOL_PHRASES = (
    "파일을 열어",
    "파일 열어",
    "파일을 수정",
    "파일 수정",
    "코드를 수정",
    "코드 수정",
    "폴더 확인",
    "폴더를 확인",
    "터미널에서",
    "명령어 실행",
    "웹에서 검색",
    "웹 검색",
    "검색해줘",
    "메모리에 저장",
    "기억해줘",
)


def route_request(question: str, attachments: Sized) -> RouteDecision:
    if len(attachments):
        return RouteDecision(Route.CODEX, "attachment")

    normalized = " ".join(question.casefold().split())
    for phrase in TOOL_PHRASES:
        if phrase.casefold() in normalized:
            return RouteDecision(Route.CODEX, f"tool_phrase:{phrase}")

    return RouteDecision(Route.CHAT, "conversation")
