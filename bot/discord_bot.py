from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

import discord

from bot.attachments import AttachmentLimitError, download_attachments, process_attachment
from bot.config import Settings
from bot.memory_guard import MemoryGuard
from bot.message_splitter import split_discord_message
from bot.models.codex_cli import CodexCli
from bot.models.direct_chat import DirectChat
from bot.prompts import attachment_context, codex_prompt
from bot.routing import Route, route_request
from bot.storage.costs import CostStore
from bot.storage.history import ConversationHistory
from bot.storage.raw_records import RawRecord
from bot.storage.sessions import SessionStore

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("codex-discord")

MODEL_ALIASES = {
    "!luna": "openai.gpt-5.6-luna",
    "!sol": "openai.gpt-5.6-sol",
    "!terra": "openai.gpt-5.6-terra",
}


def session_key(message: discord.Message) -> str:
    channel = message.channel
    if str(getattr(channel, "type", "")).endswith("thread"):
        return f"thread-{channel.id}"
    if message.guild is None:
        return f"dm-{message.author.id}"
    return f"chan-{channel.id}-{message.author.id}"


class CodexDiscordBot(discord.Client):
    def __init__(self, settings: Settings, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.settings = settings
        self.sessions = SessionStore(
            settings.data_dir / "sessions.json", settings.default_model
        )
        self.costs = CostStore(
            settings.data_dir / "usage.jsonl",
            settings.data_dir / "cost-state.json",
            settings.model_prices,
            settings.cost_alert_step,
        )
        self.history = ConversationHistory(settings.raw_dir, settings.base_dir)
        self.guard = MemoryGuard(settings.base_dir, settings.state_git_dir)
        self.codex = CodexCli(
            working_directory=settings.memory_dir,
            timeout_seconds=settings.codex_timeout_seconds,
            supports_vision=settings.codex_supports_vision,
        )
        self.direct = DirectChat(
            model=settings.chat_model,
            project=settings.mantle_project,
            secret_name=settings.mantle_secret_name,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_region=settings.aws_region,
            max_output_tokens=settings.direct_max_output_tokens,
        )

    async def on_ready(self) -> None:
        logger.info("logged_in user=%s id=%s", self.user, self.user.id)

    def allowed(self, message: discord.Message) -> bool:
        return (
            not self.settings.allowed_user_ids
            or message.author.id in self.settings.allowed_user_ids
        ) and (
            not self.settings.allowed_channel_ids
            or message.channel.id in self.settings.allowed_channel_ids
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or not self.allowed(message):
            return
        question = message.content.strip()
        if not question and not message.attachments:
            return
        key = session_key(message)
        if question in MODEL_ALIASES:
            info = await self.sessions.set_model(key, MODEL_ALIASES[question])
            await message.channel.send(
                f"🤖 Codex 모델이 **{info.model}**(으)로 변경되었습니다. "
                "일반 대화 Direct API 모델은 CHAT_MODEL 설정을 사용합니다."
            )
            return
        if question in {"!reset", "!초기화"}:
            info = await self.sessions.reset(key)
            await message.channel.send(
                f"🔄 대화 세션이 초기화되었습니다. "
                f"(Epoch {info.epoch}, Codex 모델: {info.model})"
            )
            return
        async with message.channel.typing():
            await self._handle_request(message, question, key)

    async def _handle_request(
        self, message: discord.Message, question: str, key: str
    ) -> None:
        raw: RawRecord | None = None
        conversation_id = ""
        stage = "initialize"
        error_id = uuid.uuid4().hex[:12]
        try:
            session = await self.sessions.get(key)
            conversation_id = session.conversation_id
            decision = route_request(question, message.attachments)
            used_model = (
                self.settings.chat_model
                if decision.route is Route.CHAT
                else session.model
            )
            logger.info(
                "request message=%s conversation=%s route=%s reason=%s model=%s",
                message.id,
                conversation_id,
                decision.route.value,
                decision.reason,
                used_model,
            )
            now = datetime.now(UTC)
            raw_path = (
                self.settings.raw_dir
                / now.strftime("%Y-%m-%d")
                / f"{now.strftime('%Y%m%d-%H%M%S')}-{message.id}.md"
            )
            raw = RawRecord.create_pending(
                raw_path,
                created_at=now,
                message_id=message.id,
                channel_id=message.channel.id,
                user_id=message.author.id,
                conversation_id=conversation_id,
                route=decision.route.value,
                model=used_model,
                question=question,
            )

            stage = "attachments"
            attachment_dir = raw_path.parent / f"{raw_path.stem}_attachments"
            saved = await download_attachments(
                message.attachments,
                attachment_dir,
                message_id=message.id,
                limits=self.settings.attachment_limits,
            )
            metadata = await asyncio.gather(
                *[
                    asyncio.to_thread(
                        process_attachment, path, self.settings.attachment_limits
                    )
                    for path in saved
                ]
            )
            raw.update_attachments(
                f"{item.get('filename')} ({item.get('type')})" for item in metadata
            )
            context, images = attachment_context(
                metadata, vision_enabled=self.settings.codex_supports_vision
            )

            stage = "model"
            before = self.guard.begin_request()
            try:
                if decision.route is Route.CHAT:
                    history = self.history.direct(
                        conversation_id,
                        limit=self.settings.direct_history_limit,
                        char_limit=self.settings.direct_history_char_limit,
                    )
                    answer, usage = await self.direct.call(question, history)
                else:
                    history = self.history.codex(
                        conversation_id, self.settings.conversation_history_limit
                    )
                    prompt = codex_prompt(question, history, context)
                    answer, usage = await asyncio.to_thread(
                        self.codex.run,
                        prompt,
                        model=session.model,
                        image_paths=images,
                    )
            except Exception:
                stage = "memory_audit_after_model_failure"
                self.guard.audit(before)
                raise

            stage = "memory_audit"
            audit = self.guard.audit(before)
            self.guard.commit(audit.updated, f"answer {message.id}")

            stage = "finalize_raw"
            raw.finish_answered(answer, datetime.now(UTC))
            self.history.append(conversation_id, raw.path, "answered")

            stage = "cost"
            cost, total, threshold = await self.costs.record(
                model=used_model,
                usage=usage,
                metadata={
                    "timestamp": datetime.now(UTC).isoformat(),
                    "discord_message_id": message.id,
                    "discord_user_id": message.author.id,
                    "discord_channel_id": message.channel.id,
                },
            )
            logger.info(
                "completed message=%s cost=%.6f total=%.6f", message.id, cost, total
            )

            stage = "discord_send"
            for chunk in split_discord_message(answer):
                await message.channel.send(chunk)
            if audit.updated:
                await message.channel.send(
                    "📝 변경된 메모리 파일: " + ", ".join(audit.updated)
                )
            reverted = audit.reverted + audit.protected_reverted
            if reverted:
                await message.channel.send(
                    "🚫 정책 위반 변경을 복원했습니다: " + ", ".join(reverted)
                )
            if threshold is not None:
                await message.channel.send(
                    f"⚠️ 누적 추정 사용료가 ${threshold:,.2f}를 넘었습니다.\n"
                    f"현재 누적 추정액: ${total:,.2f}"
                )
        except AttachmentLimitError as exc:
            await self._fail(raw, conversation_id, stage, error_id, exc)
            await message.channel.send(f"첨부파일 제한을 초과했습니다: {exc}")
        except Exception as exc:
            logger.exception(
                "request_failed message=%s stage=%s error_id=%s",
                message.id,
                stage,
                error_id,
            )
            await self._fail(raw, conversation_id, stage, error_id, exc)
            await message.channel.send(
                f"요청 처리 중 오류가 발생했습니다. 오류 ID: `{error_id}`"
            )

    async def _fail(
        self,
        raw: RawRecord | None,
        conversation_id: str,
        stage: str,
        error_id: str,
        exc: Exception,
    ) -> None:
        if raw is None:
            return
        try:
            raw.finish_failed(
                stage=stage,
                error_id=error_id,
                error_type=type(exc).__name__,
                finished_at=datetime.now(UTC),
            )
            self.history.append(conversation_id, raw.path, "failed")
        except Exception:
            logger.exception("failed_to_finalize_raw error_id=%s", error_id)


def main() -> None:
    settings = Settings.from_env()
    settings.validate_runtime()
    intents = discord.Intents.default()
    intents.message_content = True
    CodexDiscordBot(settings, intents=intents).run(settings.discord_token)


if __name__ == "__main__":
    main()
