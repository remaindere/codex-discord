from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import bot.discord_bot as discord_bot
from bot.discord_bot import (
    CodexDiscordBot,
    _strip_route_prefix,
    session_key,
)
from bot.routing import Route, RouteContext, RouteDecision
from bot.storage.sessions import SessionInfo


class FakeTyping:
    async def __aenter__(self) -> FakeTyping:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeChannel:
    def __init__(self, *, channel_id: int = 200, channel_type: str = "text") -> None:
        self.id = channel_id
        self.type = channel_type
        self.sent: list[str] = []

    def typing(self) -> FakeTyping:
        return FakeTyping()

    async def send(self, content: str) -> None:
        self.sent.append(content)


def make_message(
    *,
    content: str = "",
    author_id: int = 100,
    channel_id: int = 200,
    channel_type: str = "text",
    guild: object | None = object(),
    attachments: list[object] | None = None,
) -> SimpleNamespace:
    channel = FakeChannel(
        channel_id=channel_id,
        channel_type=channel_type,
    )
    return SimpleNamespace(
        id=123456,
        content=content,
        author=SimpleNamespace(id=author_id),
        channel=channel,
        guild=guild,
        attachments=attachments or [],
    )


def set_bot_user(bot: CodexDiscordBot, *, user_id: int = 999) -> None:
    # discord.Client.user is a read-only property backed by _connection.user.
    bot._connection = SimpleNamespace(
        user=SimpleNamespace(id=user_id),
    )


def make_settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        chat_model="chat-model",
        codex_model="codex-default",
        codex_supports_vision=False,
        direct_history_limit=10,
        direct_history_char_limit=10_000,
        conversation_history_limit=10,
        raw_dir=tmp_path / "raw",
        attachment_limits=SimpleNamespace(),
    )


@dataclass(frozen=True)
class FakeAudit:
    updated: tuple[str, ...] = ()
    reverted: tuple[str, ...] = ()
    protected_reverted: tuple[str, ...] = ()


class FakeRawRecord:
    def __init__(self) -> None:
        self.path = Path("/tmp/fake-raw.md")
        self.attachments: list[str] = []
        self.answer: str | None = None
        self.failed: dict[str, object] | None = None

    @classmethod
    def create_pending(cls, *args, **kwargs) -> FakeRawRecord:
        return cls()

    def update_attachments(self, items) -> None:
        self.attachments = list(items)

    def finish_answered(self, answer: str, finished_at) -> None:
        self.answer = answer

    def finish_failed(self, **kwargs) -> None:
        self.failed = kwargs


def make_bot(
    tmp_path: Path,
    *,
    session: SessionInfo,
    route: Route = Route.CHAT,
    reason: str = "fallback:chat",
) -> tuple[CodexDiscordBot, dict[str, Mock | AsyncMock]]:
    bot = CodexDiscordBot.__new__(CodexDiscordBot)
    bot.settings = make_settings(tmp_path)

    sessions = Mock()
    sessions.get = AsyncMock(return_value=session)
    sessions.set_last_route = AsyncMock()
    sessions.set_model = AsyncMock(return_value=session)
    sessions.reset = AsyncMock(return_value=session)

    costs = Mock()
    costs.record = AsyncMock(
        return_value=(0.001, 0.001, None),
    )

    history = Mock()
    history.direct.return_value = []
    history.codex.return_value = []
    history.append = Mock()

    guard = Mock()
    guard.begin_request.return_value = object()
    guard.audit.return_value = FakeAudit()
    guard.commit = Mock()

    codex = Mock()
    codex.run.return_value = (
        "codex answer",
        {"input_tokens": 10, "output_tokens": 5},
    )

    direct = Mock()
    direct.call = AsyncMock(
        return_value=(
            "chat answer",
            {"input_tokens": 10, "output_tokens": 5},
        ),
    )

    bot.sessions = sessions
    bot.costs = costs
    bot.history = history
    bot.guard = guard
    bot.codex = codex
    bot.direct = direct

    mocks: dict[str, Mock | AsyncMock] = {
        "sessions": sessions,
        "costs": costs,
        "history": history,
        "guard": guard,
        "codex": codex,
        "direct": direct,
        "decision": RouteDecision(route, reason),
    }

    return bot, mocks


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_strip_route_prefix_chat() -> None:
    assert _strip_route_prefix("!chat hello") == "hello"


def test_strip_route_prefix_codex() -> None:
    assert _strip_route_prefix("!codex fix this") == "fix this"


def test_strip_route_prefix_without_prefix() -> None:
    assert _strip_route_prefix("hello") == "hello"


def test_strip_route_prefix_only_command_returns_empty() -> None:
    assert _strip_route_prefix("!chat") == ""
    assert _strip_route_prefix("!codex") == ""


def test_strip_route_prefix_is_case_insensitive() -> None:
    assert _strip_route_prefix("!CoDeX hello") == "hello"


def test_strip_route_prefix_does_not_strip_similar_command() -> None:
    assert _strip_route_prefix("!codexx hello") == "!codexx hello"


# ---------------------------------------------------------------------------
# Session key
# ---------------------------------------------------------------------------


def test_session_key_for_dm() -> None:
    message = make_message(
        author_id=456,
        guild=None,
    )

    assert session_key(message) == "dm-456"


def test_session_key_for_guild_channel() -> None:
    message = make_message(
        author_id=456,
        channel_id=123,
        guild=object(),
    )

    assert session_key(message) == "chan-123-456"


def test_session_key_for_thread() -> None:
    message = make_message(
        author_id=456,
        channel_id=789,
        channel_type="public_thread",
        guild=object(),
    )

    assert session_key(message) == "thread-789"


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


def test_allowed_without_restrictions() -> None:
    bot = CodexDiscordBot.__new__(CodexDiscordBot)
    bot.settings = SimpleNamespace(
        allowed_user_ids=set(),
        allowed_channel_ids=set(),
    )

    message = make_message()

    assert bot.allowed(message) is True


def test_allowed_rejects_unknown_user() -> None:
    bot = CodexDiscordBot.__new__(CodexDiscordBot)
    bot.settings = SimpleNamespace(
        allowed_user_ids={1, 2, 3},
        allowed_channel_ids=set(),
    )

    message = make_message(author_id=999)

    assert bot.allowed(message) is False


def test_allowed_rejects_unknown_channel() -> None:
    bot = CodexDiscordBot.__new__(CodexDiscordBot)
    bot.settings = SimpleNamespace(
        allowed_user_ids=set(),
        allowed_channel_ids={1, 2, 3},
    )

    message = make_message(channel_id=999)

    assert bot.allowed(message) is False


def test_allowed_requires_both_user_and_channel_when_restricted() -> None:
    bot = CodexDiscordBot.__new__(CodexDiscordBot)
    bot.settings = SimpleNamespace(
        allowed_user_ids={100},
        allowed_channel_ids={200},
    )

    valid = make_message(author_id=100, channel_id=200)
    invalid_user = make_message(author_id=999, channel_id=200)
    invalid_channel = make_message(author_id=100, channel_id=999)

    assert bot.allowed(valid) is True
    assert bot.allowed(invalid_user) is False
    assert bot.allowed(invalid_channel) is False


# ---------------------------------------------------------------------------
# on_message dispatch
# ---------------------------------------------------------------------------


def test_on_message_ignores_own_message() -> None:
    async def scenario() -> None:
        bot = CodexDiscordBot.__new__(CodexDiscordBot)
        set_bot_user(bot, user_id=999)
        bot.settings = SimpleNamespace(
            allowed_user_ids=set(),
            allowed_channel_ids=set(),
        )
        bot._handle_request = AsyncMock()

        message = make_message(author_id=999)

        await bot.on_message(message)

        bot._handle_request.assert_not_awaited()

    asyncio.run(scenario())


def test_on_message_ignores_disallowed_message() -> None:
    async def scenario() -> None:
        bot = CodexDiscordBot.__new__(CodexDiscordBot)
        set_bot_user(bot, user_id=999)
        bot.settings = SimpleNamespace(
            allowed_user_ids={1},
            allowed_channel_ids=set(),
        )
        bot._handle_request = AsyncMock()

        message = make_message(author_id=9999)

        await bot.on_message(message)

        bot._handle_request.assert_not_awaited()

    asyncio.run(scenario())


def test_on_message_ignores_empty_message_without_attachments() -> None:
    async def scenario() -> None:
        bot = CodexDiscordBot.__new__(CodexDiscordBot)
        set_bot_user(bot, user_id=999)
        bot.settings = SimpleNamespace(
            allowed_user_ids=set(),
            allowed_channel_ids=set(),
        )
        bot._handle_request = AsyncMock()

        message = make_message(content="")

        await bot.on_message(message)

        bot._handle_request.assert_not_awaited()

    asyncio.run(scenario())


def test_on_message_dispatches_normal_request() -> None:
    async def scenario() -> None:
        bot = CodexDiscordBot.__new__(CodexDiscordBot)
        set_bot_user(bot, user_id=999)
        bot.settings = SimpleNamespace(
            allowed_user_ids=set(),
            allowed_channel_ids=set(),
        )
        bot._handle_request = AsyncMock()

        message = make_message(content="hello")

        await bot.on_message(message)

        bot._handle_request.assert_awaited_once_with(
            message,
            "hello",
            "chan-200-100",
        )

    asyncio.run(scenario())


def test_on_message_model_alias_updates_session() -> None:
    async def scenario() -> None:
        bot = CodexDiscordBot.__new__(CodexDiscordBot)
        set_bot_user(bot, user_id=999)
        bot.settings = SimpleNamespace(
            allowed_user_ids=set(),
            allowed_channel_ids=set(),
        )

        info = SessionInfo(
            conversation_id="chan-200-100-ep1",
            model="openai.gpt-5.6-luna",
            epoch=1,
            last_route=None,
        )

        sessions = Mock()
        sessions.set_model = AsyncMock(return_value=info)
        bot.sessions = sessions
        bot._handle_request = AsyncMock()

        message = make_message(content="!luna")

        await bot.on_message(message)

        sessions.set_model.assert_awaited_once_with(
            "chan-200-100",
            "openai.gpt-5.6-luna",
        )
        bot._handle_request.assert_not_awaited()
        assert message.channel.sent
        assert "openai.gpt-5.6-luna" in message.channel.sent[0]

    asyncio.run(scenario())


@pytest.mark.parametrize("command", ["!reset", "!초기화"])
def test_on_message_reset_updates_session(command: str) -> None:
    async def scenario() -> None:
        bot = CodexDiscordBot.__new__(CodexDiscordBot)
        set_bot_user(bot, user_id=999)
        bot.settings = SimpleNamespace(
            allowed_user_ids=set(),
            allowed_channel_ids=set(),
        )

        info = SessionInfo(
            conversation_id="chan-200-100-ep2",
            model="codex-model",
            epoch=2,
            last_route=None,
        )

        sessions = Mock()
        sessions.reset = AsyncMock(return_value=info)
        bot.sessions = sessions
        bot._handle_request = AsyncMock()

        message = make_message(content=command)

        await bot.on_message(message)

        sessions.reset.assert_awaited_once_with("chan-200-100")
        bot._handle_request.assert_not_awaited()
        assert "초기화" in message.channel.sent[0]

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# _handle_request: routing boundary and model dispatch
# ---------------------------------------------------------------------------


def test_handle_request_chat_uses_direct_chat_and_persists_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        session = SessionInfo(
            conversation_id="chan-200-100-ep1",
            model="codex-model",
            epoch=1,
            last_route="chat",
        )
        bot, mocks = make_bot(
            tmp_path,
            session=session,
            route=Route.CHAT,
            reason="fallback:chat",
        )

        decision = mocks["decision"]
        assert isinstance(decision, RouteDecision)

        route_mock = Mock(return_value=decision)
        monkeypatch.setattr(discord_bot, "route_request", route_mock)

        monkeypatch.setattr(
            discord_bot,
            "download_attachments",
            AsyncMock(return_value=[]),
        )
        monkeypatch.setattr(
            discord_bot,
            "attachment_context",
            Mock(return_value=("", [])),
        )
        monkeypatch.setattr(
            discord_bot,
            "codex_prompt",
            Mock(return_value="unused"),
        )
        monkeypatch.setattr(
            discord_bot,
            "split_discord_message",
            Mock(return_value=["chat answer"]),
        )
        monkeypatch.setattr(
            discord_bot.RawRecord,
            "create_pending",
            FakeRawRecord.create_pending,
        )

        message = make_message(content="안녕")

        await bot._handle_request(
            message,
            "안녕",
            "chan-200-100",
        )

        route_mock.assert_called_once_with(
            "안녕",
            RouteContext(
                has_attachments=False,
                previous_route=Route.CHAT,
            ),
        )

        sessions = mocks["sessions"]
        assert isinstance(sessions, Mock)
        sessions.get.assert_awaited_once_with("chan-200-100")
        sessions.set_last_route.assert_awaited_once_with(
            "chan-200-100",
            "chat",
        )

        direct = mocks["direct"]
        assert isinstance(direct, Mock)
        direct.call.assert_awaited_once()
        codex = mocks["codex"]
        assert isinstance(codex, Mock)
        codex.run.assert_not_called()

        history = mocks["history"]
        assert isinstance(history, Mock)
        history.direct.assert_called_once_with(
            "chan-200-100-ep1",
            limit=10,
            char_limit=10_000,
        )
        history.codex.assert_not_called()

        assert message.channel.sent == ["chat answer"]

    asyncio.run(scenario())


def test_handle_request_codex_uses_codex_and_preserves_previous_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        session = SessionInfo(
            conversation_id="chan-200-100-ep4",
            model="custom-codex",
            epoch=4,
            last_route="codex",
        )
        bot, mocks = make_bot(
            tmp_path,
            session=session,
            route=Route.CODEX,
            reason="followup:codex",
        )

        decision = mocks["decision"]
        assert isinstance(decision, RouteDecision)

        route_mock = Mock(return_value=decision)
        monkeypatch.setattr(discord_bot, "route_request", route_mock)

        monkeypatch.setattr(
            discord_bot,
            "download_attachments",
            AsyncMock(return_value=[]),
        )
        monkeypatch.setattr(
            discord_bot,
            "attachment_context",
            Mock(return_value=("", [])),
        )
        prompt_mock = Mock(return_value="codex prompt")
        monkeypatch.setattr(
            discord_bot,
            "codex_prompt",
            prompt_mock,
        )
        monkeypatch.setattr(
            discord_bot,
            "split_discord_message",
            Mock(return_value=["codex answer"]),
        )
        monkeypatch.setattr(
            discord_bot.RawRecord,
            "create_pending",
            FakeRawRecord.create_pending,
        )

        message = make_message(
            content="왜 제공되지 않는지 찾아내",
        )

        await bot._handle_request(
            message,
            message.content,
            "chan-200-100",
        )

        route_mock.assert_called_once_with(
            message.content,
            RouteContext(
                has_attachments=False,
                previous_route=Route.CODEX,
            ),
        )

        sessions = mocks["sessions"]
        assert isinstance(sessions, Mock)
        sessions.set_last_route.assert_awaited_once_with(
            "chan-200-100",
            "codex",
        )

        codex = mocks["codex"]
        assert isinstance(codex, Mock)
        codex.run.assert_called_once_with(
            "codex prompt",
            model="custom-codex",
            image_paths=[],
        )

        direct = mocks["direct"]
        assert isinstance(direct, Mock)
        direct.call.assert_not_awaited()

        history = mocks["history"]
        assert isinstance(history, Mock)
        history.codex.assert_called_once_with(
            "chan-200-100-ep4",
            10,
        )
        history.direct.assert_not_called()

        prompt_mock.assert_called_once_with(
            message.content,
            [],
            "",
        )

        assert message.channel.sent == ["codex answer"]

    asyncio.run(scenario())


def test_handle_request_attachment_context_is_passed_to_codex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        session = SessionInfo(
            conversation_id="chan-200-100-ep1",
            model="codex-model",
            epoch=1,
            last_route=None,
        )
        bot, mocks = make_bot(
            tmp_path,
            session=session,
            route=Route.CODEX,
            reason="attachment",
        )

        monkeypatch.setattr(
            discord_bot,
            "route_request",
            Mock(return_value=mocks["decision"]),
        )

        saved = ["/tmp/file.png"]
        monkeypatch.setattr(
            discord_bot,
            "download_attachments",
            AsyncMock(return_value=saved),
        )

        processed = {
            "filename": "file.png",
            "type": "image/png",
        }
        monkeypatch.setattr(
            discord_bot,
            "process_attachment",
            Mock(return_value=processed),
        )

        monkeypatch.setattr(
            discord_bot,
            "attachment_context",
            Mock(return_value=("image context", ["/tmp/file.png"])),
        )

        monkeypatch.setattr(
            discord_bot,
            "codex_prompt",
            Mock(return_value="codex prompt"),
        )
        monkeypatch.setattr(
            discord_bot,
            "split_discord_message",
            Mock(return_value=["answer"]),
        )
        monkeypatch.setattr(
            discord_bot.RawRecord,
            "create_pending",
            FakeRawRecord.create_pending,
        )

        message = make_message(
            content="이 이미지 분석해줘",
            attachments=[object()],
        )

        await bot._handle_request(
            message,
            message.content,
            "chan-200-100",
        )

        download = discord_bot.download_attachments
        assert isinstance(download, AsyncMock)
        download.assert_awaited_once()

        attachment_context_mock = discord_bot.attachment_context
        assert isinstance(attachment_context_mock, Mock)
        attachment_context_mock.assert_called_once_with(
            [processed],
            vision_enabled=False,
        )

        codex = mocks["codex"]
        assert isinstance(codex, Mock)
        codex.run.assert_called_once_with(
            "codex prompt",
            model="codex-model",
            image_paths=["/tmp/file.png"],
        )

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# _handle_request: prefix stripping and validation
# ---------------------------------------------------------------------------


def test_handle_request_strips_route_prefix_before_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        session = SessionInfo(
            conversation_id="chan-200-100-ep1",
            model="codex-model",
            epoch=1,
            last_route="codex",
        )
        bot, mocks = make_bot(
            tmp_path,
            session=session,
            route=Route.CODEX,
            reason="explicit:codex",
        )

        monkeypatch.setattr(
            discord_bot,
            "route_request",
            Mock(return_value=mocks["decision"]),
        )
        monkeypatch.setattr(
            discord_bot,
            "download_attachments",
            AsyncMock(return_value=[]),
        )
        monkeypatch.setattr(
            discord_bot,
            "attachment_context",
            Mock(return_value=("", [])),
        )
        monkeypatch.setattr(
            discord_bot,
            "codex_prompt",
            Mock(return_value="prompt"),
        )
        monkeypatch.setattr(
            discord_bot,
            "split_discord_message",
            Mock(return_value=["answer"]),
        )
        monkeypatch.setattr(
            discord_bot.RawRecord,
            "create_pending",
            FakeRawRecord.create_pending,
        )

        message = make_message(content="!codex 실제 질문")

        await bot._handle_request(
            message,
            message.content,
            "chan-200-100",
        )

        prompt_mock = discord_bot.codex_prompt
        assert isinstance(prompt_mock, Mock)
        prompt_mock.assert_called_once_with(
            "실제 질문",
            [],
            "",
        )

    asyncio.run(scenario())


def test_handle_request_rejects_empty_command_after_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        session = SessionInfo(
            conversation_id="chan-200-100-ep1",
            model="codex-model",
            epoch=1,
            last_route="codex",
        )
        bot, mocks = make_bot(
            tmp_path,
            session=session,
            route=Route.CODEX,
            reason="explicit:codex",
        )

        monkeypatch.setattr(
            discord_bot,
            "route_request",
            Mock(return_value=mocks["decision"]),
        )

        raw_create = Mock(wraps=FakeRawRecord.create_pending)
        monkeypatch.setattr(
            discord_bot.RawRecord,
            "create_pending",
            raw_create,
        )

        message = make_message(content="!codex")

        await bot._handle_request(
            message,
            message.content,
            "chan-200-100",
        )

        assert message.channel.sent == [
            "사용법: `!codex 질문` 또는 `!chat 질문`"
        ]
        raw_create.assert_not_called()

        sessions = mocks["sessions"]
        assert isinstance(sessions, Mock)
        sessions.set_last_route.assert_awaited_once_with(
            "chan-200-100",
            "codex",
        )

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_handle_request_records_attachment_limit_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        session = SessionInfo(
            conversation_id="chan-200-100-ep1",
            model="codex-model",
            epoch=1,
            last_route=None,
        )
        bot, mocks = make_bot(
            tmp_path,
            session=session,
            route=Route.CODEX,
            reason="attachment",
        )

        monkeypatch.setattr(
            discord_bot,
            "route_request",
            Mock(return_value=mocks["decision"]),
        )
        monkeypatch.setattr(
            discord_bot,
            "RawRecord",
            FakeRawRecord,
        )

        from bot.attachments import AttachmentLimitError

        monkeypatch.setattr(
            discord_bot,
            "download_attachments",
            AsyncMock(
                side_effect=AttachmentLimitError("too large"),
            ),
        )

        message = make_message(
            content="첨부파일 확인해줘",
            attachments=[object()],
        )

        await bot._handle_request(
            message,
            message.content,
            "chan-200-100",
        )

        assert message.channel.sent == [
            "첨부파일 제한을 초과했습니다: too large"
        ]

    asyncio.run(scenario())


def test_handle_request_records_generic_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        session = SessionInfo(
            conversation_id="chan-200-100-ep1",
            model="codex-model",
            epoch=1,
            last_route=None,
        )
        bot, mocks = make_bot(
            tmp_path,
            session=session,
            route=Route.CHAT,
            reason="fallback:chat",
        )

        monkeypatch.setattr(
            discord_bot,
            "route_request",
            Mock(return_value=mocks["decision"]),
        )
        monkeypatch.setattr(
            discord_bot,
            "download_attachments",
            AsyncMock(
                side_effect=RuntimeError("boom"),
            ),
        )
        monkeypatch.setattr(
            discord_bot,
            "RawRecord",
            FakeRawRecord,
        )

        message = make_message(content="hello")

        await bot._handle_request(
            message,
            message.content,
            "chan-200-100",
        )

        assert len(message.channel.sent) == 1
        assert message.channel.sent[0].startswith(
            "요청 처리 중 오류가 발생했습니다. 오류 ID: `"
        )
        assert message.channel.sent[0].endswith("`")

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# Ready event
# ---------------------------------------------------------------------------


def test_on_ready_logs_current_user(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        bot = CodexDiscordBot.__new__(CodexDiscordBot)
        set_bot_user(bot, user_id=999)
        await bot.on_ready()

    with caplog.at_level("INFO", logger="codex-discord"):
        asyncio.run(scenario())

    assert "logged_in" in caplog.text
    assert "id=999" in caplog.text
