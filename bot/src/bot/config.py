from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _positive_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True)
class AttachmentLimits:
    max_count: int = 8
    max_file_bytes: int = 20 * 1024 * 1024
    max_total_bytes: int = 40 * 1024 * 1024
    max_pdf_pages: int = 80
    max_render_pages: int = 12
    max_text_chars: int = 20_000


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    memory_dir: Path
    raw_dir: Path
    data_dir: Path
    state_git_dir: Path
    codex_model: str
    chat_model: str
    codex_timeout_seconds: int
    cost_alert_step: float
    attachment_limits: AttachmentLimits
    discord_token: str
    allowed_user_ids: frozenset[int]
    allowed_channel_ids: frozenset[int]
    conversation_history_limit: int
    direct_history_limit: int
    direct_history_char_limit: int
    direct_max_output_tokens: int
    codex_supports_vision: bool
    mantle_project: str
    mantle_secret_name: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    model_prices: dict[str, dict[str, float]]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        base_dir = Path(
            values.get("BASE_DIR", "/home/remaindere/codex-discord")
        ).expanduser().resolve()
        data_dir = Path(values.get("DATA_DIR", str(base_dir / "data"))).expanduser()
        raw_dir = Path(
            values.get("RAW_DIR", str(base_dir / "raw" / "discord"))
        ).expanduser()

        codex_model = values.get("CODEX_MODEL", "").strip()
        chat_model = values.get("CHAT_MODEL", "").strip()
        missing = [
            name
            for name, value in (
                ("CODEX_MODEL", codex_model),
                ("CHAT_MODEL", chat_model),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"missing required settings: {', '.join(missing)}")

        limits = AttachmentLimits(
            max_count=_positive_int(values, "ATTACHMENT_MAX_COUNT", 8),
            max_file_bytes=_positive_int(
                values, "ATTACHMENT_MAX_FILE_BYTES", 20 * 1024 * 1024
            ),
            max_total_bytes=_positive_int(
                values, "ATTACHMENT_MAX_TOTAL_BYTES", 40 * 1024 * 1024
            ),
            max_pdf_pages=_positive_int(values, "PDF_MAX_PAGES", 80),
            max_render_pages=_positive_int(values, "PDF_MAX_RENDER_PAGES", 12),
            max_text_chars=_positive_int(
                values, "ATTACHMENT_MAX_TEXT_CHARS", 20_000
            ),
        )
        def ids(name: str) -> frozenset[int]:
            try:
                return frozenset(
                    int(item.strip())
                    for item in values.get(name, "").split(",")
                    if item.strip()
                )
            except ValueError as exc:
                raise ValueError(f"{name} must contain comma-separated integers") from exc

        def truthy(name: str, default: str = "false") -> bool:
            raw = values.get(name, default).strip().casefold()
            if raw not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError(f"{name} must be true or false")
            return raw in {"true", "1", "yes"}

        price_prefixes = {
            "openai.gpt-5.6-sol": "SOL",
            "openai.gpt-5.6-terra": "TERRA",
            "openai.gpt-5.6-luna": "LUNA",
        }
        prices: dict[str, dict[str, float]] = {}
        for model, prefix in price_prefixes.items():
            names = {
                "input": f"{prefix}_INPUT_PRICE_PER_MILLION",
                "cached_input": f"{prefix}_CACHED_INPUT_PRICE_PER_MILLION",
                "output": f"{prefix}_OUTPUT_PRICE_PER_MILLION",
            }
            if all(values.get(name, "").strip() for name in names.values()):
                prices[model] = {
                    key: float(values[name])
                    for key, name in names.items()
                }
                prices[model]["cache_write"] = float(
                    values.get(f"{prefix}_CACHE_WRITE_PRICE_PER_MILLION", "0")
                )

        return cls(
            base_dir=base_dir,
            memory_dir=base_dir / "memory",
            raw_dir=raw_dir.resolve(),
            data_dir=data_dir.resolve(),
            state_git_dir=base_dir / ".state.git",
            codex_model=codex_model,
            chat_model=chat_model,
            codex_timeout_seconds=_positive_int(
                values, "CODEX_TIMEOUT_SECONDS", 900
            ),
            cost_alert_step=_positive_float(values, "COST_ALERT_STEP", 100.0),
            attachment_limits=limits,
            discord_token=values.get("DISCORD_TOKEN", "").strip(),
            allowed_user_ids=ids("ALLOWED_USER_IDS"),
            allowed_channel_ids=ids("ALLOWED_CHANNEL_IDS"),
            conversation_history_limit=_positive_int(
                values, "CONVERSATION_HISTORY_LIMIT", 10
            ),
            direct_history_limit=_positive_int(values, "DIRECT_HISTORY_LIMIT", 5),
            direct_history_char_limit=_positive_int(
                values, "DIRECT_HISTORY_CHAR_LIMIT", 12_000
            ),
            direct_max_output_tokens=_positive_int(
                values, "DIRECT_MAX_OUTPUT_TOKENS", 1200
            ),
            codex_supports_vision=truthy("CODEX_SUPPORTS_VISION"),
            mantle_project=values.get("MANTLE_PROJECT", "").strip(),
            mantle_secret_name=values.get("MANTLE_SECRET_NAME", "").strip(),
            aws_access_key_id=values.get("AWS_ACCESS_KEY_ID", "").strip(),
            aws_secret_access_key=values.get("AWS_SECRET_ACCESS_KEY", "").strip(),
            aws_region=values.get("AWS_DEFAULT_REGION", "us-east-1").strip(),
            model_prices=prices,
        )

    def validate_runtime(self) -> None:
        required = {
            "DISCORD_TOKEN": self.discord_token,
            "MANTLE_PROJECT": self.mantle_project,
            "MANTLE_SECRET_NAME": self.mantle_secret_name,
            "AWS_ACCESS_KEY_ID": self.aws_access_key_id,
            "AWS_SECRET_ACCESS_KEY": self.aws_secret_access_key,
            "AWS_DEFAULT_REGION": self.aws_region,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"missing required runtime settings: {', '.join(missing)}")
        unpriced = {
            self.codex_model,
            self.chat_model,
        } - self.model_prices.keys()
        if unpriced:
            raise ValueError(
                "missing price settings for models: " + ", ".join(sorted(unpriced))
            )
