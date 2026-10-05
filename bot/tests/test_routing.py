from bot.routing import Route, route_request


def test_attachment_routes_to_codex() -> None:
    decision = route_request("설명해줘", [object()])
    assert decision.route is Route.CODEX
    assert decision.reason == "attachment"


def test_explicit_tool_phrase_routes_to_codex() -> None:
    decision = route_request("이 파일을 수정해줘", [])
    assert decision.route is Route.CODEX
    assert decision.reason.startswith("tool_phrase:")


def test_normal_conversation_routes_to_chat() -> None:
    decision = route_request("오늘 기분은 어때?", [])
    assert decision.route is Route.CHAT
    assert decision.reason == "conversation"
