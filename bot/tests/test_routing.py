from bot.routing import Route, RouteContext, route_request


def test_attachment_routes_to_codex() -> None:
    decision = route_request(
        "설명해줘",
        RouteContext(has_attachments=True),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "attachment"


def test_work_target_and_action_routes_to_codex() -> None:
    decision = route_request(
        "이 파일을 수정해줘",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "work_intent"


def test_path_without_action_routes_to_codex() -> None:
    decision = route_request(
        "~/codex-discord/bot",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "filesystem:path"


def test_previous_codex_followup_routes_to_codex() -> None:
    decision = route_request(
        "왜 제공되지 않는지 찾아내",
        RouteContext(previous_route=Route.CODEX),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "followup:codex"


def test_unknown_input_falls_back_to_codex() -> None:
    decision = route_request(
        "그냥 해봐",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "fallback:codex"


def test_explicit_chat_override() -> None:
    decision = route_request(
        "!chat 파일 수정해줘",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "explicit:chat"


def test_explicit_codex_override() -> None:
    decision = route_request(
        "!codex 안녕",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "explicit:codex"
    
def test_weather_routes_to_codex() -> None:
    decision = route_request(
        "오늘 용인 날씨 머임",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "realtime"