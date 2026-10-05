from bot.routing import Route, RouteContext, route_request


# ---------------------------------------------------------------------------
# Explicit overrides
# ---------------------------------------------------------------------------


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


def test_explicit_chat_override_requires_command_boundary() -> None:
    decision = route_request(
        "!chatty 파일 수정해줘",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "work_intent"


def test_explicit_codex_override_requires_command_boundary() -> None:
    decision = route_request(
        "!codexx 안녕",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


# ---------------------------------------------------------------------------
# Hard Codex signals
# ---------------------------------------------------------------------------


def test_attachment_routes_to_codex() -> None:
    decision = route_request(
        "설명해줘",
        RouteContext(has_attachments=True),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "attachment"


def test_path_without_action_routes_to_codex() -> None:
    decision = route_request(
        "~/codex-discord/bot",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "filesystem:path"


def test_relative_path_routes_to_codex() -> None:
    decision = route_request(
        "./bot/routing.py",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "filesystem:path"


def test_parent_relative_path_routes_to_codex() -> None:
    decision = route_request(
        "../bot/routing.py",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "filesystem:path"


def test_windows_path_routes_to_codex() -> None:
    decision = route_request(
        r"C:\Users\test\project\main.py",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "filesystem:path"


def test_filename_routes_to_codex() -> None:
    decision = route_request(
        "bot/routing.py 확인해줘",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "filesystem:path"


def test_strong_technical_term_routes_to_codex() -> None:
    decision = route_request(
        "pytest에서 assertion error가 발생해",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "technical_term"


def test_english_strong_technical_term_routes_to_codex() -> None:
    decision = route_request(
        "There is a merge conflict in the repository.",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "technical_term"


# ---------------------------------------------------------------------------
# Work intent
# ---------------------------------------------------------------------------


def test_work_target_and_action_routes_to_codex() -> None:
    decision = route_request(
        "이 파일을 수정해줘",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "work_intent"


def test_korean_work_intent_routes_to_codex() -> None:
    decision = route_request(
        "프로젝트 로그 분석해줘",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "work_intent"


def test_english_work_intent_routes_to_codex() -> None:
    decision = route_request(
        "Please inspect this file.",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "work_intent"


def test_english_repository_work_intent_routes_to_codex() -> None:
    decision = route_request(
        "Check the repository and fix the issue.",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "work_intent"


def test_target_without_action_does_not_trigger_work_intent() -> None:
    decision = route_request(
        "이 파일이 뭐야?",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


def test_action_without_target_does_not_trigger_work_intent() -> None:
    decision = route_request(
        "분석해줘",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


# ---------------------------------------------------------------------------
# Realtime
# ---------------------------------------------------------------------------


def test_weather_routes_to_codex() -> None:
    decision = route_request(
        "오늘 용인 날씨 머임",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "realtime"


def test_english_weather_routes_to_codex() -> None:
    decision = route_request(
        "What's the weather today?",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "realtime"


def test_exchange_rate_routes_to_codex() -> None:
    decision = route_request(
        "현재 환율 알려줘",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "realtime"


def test_english_latest_news_routes_to_codex() -> None:
    decision = route_request(
        "Find the latest news about Python.",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "realtime"


# ---------------------------------------------------------------------------
# Follow-up / previous Codex context
# ---------------------------------------------------------------------------


def test_previous_codex_followup_routes_to_codex() -> None:
    decision = route_request(
        "왜 제공되지 않는지 찾아내",
        RouteContext(previous_route=Route.CODEX),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "followup:codex"


def test_previous_codex_reference_followup_routes_to_codex() -> None:
    decision = route_request(
        "그 코드 다시 확인해줘",
        RouteContext(previous_route=Route.CODEX),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "followup:codex"


def test_previous_codex_continuation_action_routes_to_codex() -> None:
    decision = route_request(
        "이어서 수정해줘",
        RouteContext(previous_route=Route.CODEX),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "followup:codex"


def test_previous_codex_debug_context_routes_to_codex() -> None:
    decision = route_request(
        "왜 이게 동작하지 않는지 확인해줘",
        RouteContext(previous_route=Route.CODEX),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "followup:codex"


def test_previous_codex_does_not_force_unrelated_chat() -> None:
    decision = route_request(
        "오늘 기분이 좀 이상하네",
        RouteContext(previous_route=Route.CODEX),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


def test_previous_codex_does_not_override_new_realtime_intent() -> None:
    decision = route_request(
        "오늘 환율 알려줘",
        RouteContext(previous_route=Route.CODEX),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "realtime"


def test_followup_language_without_previous_codex_does_not_become_followup() -> None:
    decision = route_request(
        "그거 다시 해줘",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


# ---------------------------------------------------------------------------
# Explanation / question phrasing
# ---------------------------------------------------------------------------


def test_explanatory_question_falls_back_to_chat() -> None:
    decision = route_request(
        "이거 어떻게 하는지 자세히 알려줄 수 있어?",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


def test_simple_meaning_question_falls_back_to_chat() -> None:
    decision = route_request(
        "이게 무슨 뜻이야?",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


def test_how_to_question_does_not_route_to_codex_without_work_target() -> None:
    decision = route_request(
        "이거 어떻게 하는지 알려줘",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


def test_question_mark_does_not_determine_route() -> None:
    decision = route_request(
        "이 파일 수정해줄 수 있어?",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "work_intent"


# ---------------------------------------------------------------------------
# Conservative fallback
# ---------------------------------------------------------------------------


def test_unknown_input_falls_back_to_chat() -> None:
    decision = route_request(
        "그냥 해봐",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


def test_casual_conversation_falls_back_to_chat() -> None:
    decision = route_request(
        "오늘 진짜 피곤하다",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


def test_empty_input_falls_back_to_chat() -> None:
    decision = route_request(
        "   ",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


# ---------------------------------------------------------------------------
# Scoring behavior
# ---------------------------------------------------------------------------


def test_weak_action_alone_does_not_force_codex() -> None:
    decision = route_request(
        "확인해줘",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


def test_weak_action_with_previous_codex_becomes_followup() -> None:
    decision = route_request(
        "확인해줘",
        RouteContext(previous_route=Route.CODEX),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "followup:codex"


def test_explanation_penalty_does_not_override_hard_technical_signal() -> None:
    decision = route_request(
        "pytest 어떻게 사용하는지 설명해줘",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "technical_term"


def test_explanation_penalty_does_not_override_work_intent() -> None:
    decision = route_request(
        "이 파일을 어떻게 수정하는지 알려줘",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "work_intent"


def test_english_explanation_without_work_target_falls_back_to_chat() -> None:
    decision = route_request(
        "Can you explain how this works?",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


# ---------------------------------------------------------------------------
# ASCII term boundary / false-positive protection
# ---------------------------------------------------------------------------


def test_short_ascii_term_does_not_match_inside_unrelated_word() -> None:
    decision = route_request(
        "This is just a proper sentence.",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"


def test_repository_keyword_is_detected_as_work_target() -> None:
    decision = route_request(
        "Please inspect the repo.",
        RouteContext(),
    )

    assert decision.route is Route.CODEX
    assert decision.reason == "work_intent"


def test_casual_english_sentence_does_not_force_codex() -> None:
    decision = route_request(
        "I had a long day today.",
        RouteContext(),
    )

    assert decision.route is Route.CHAT
    assert decision.reason == "fallback:chat"