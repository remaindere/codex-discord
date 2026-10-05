from pathlib import Path

import pytest

from bot.config import Settings


def test_settings_resolve_paths_and_limits(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "BASE_DIR": str(tmp_path),
            "DEFAULT_MODEL": "codex-model",
            "CHAT_MODEL": "chat-model",
            "ATTACHMENT_MAX_COUNT": "3",
            "COST_ALERT_STEP": "0.5",
        }
    )

    assert settings.base_dir == tmp_path.resolve()
    assert settings.memory_dir == tmp_path.resolve() / "memory"
    assert settings.default_model == "codex-model"
    assert settings.chat_model == "chat-model"
    assert settings.attachment_limits.max_count == 3
    assert settings.cost_alert_step == 0.5


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ATTACHMENT_MAX_COUNT", "0"),
        ("CODEX_TIMEOUT_SECONDS", "nope"),
        ("COST_ALERT_STEP", "-1"),
    ],
)
def test_settings_reject_invalid_positive_values(
    tmp_path: Path, name: str, value: str
) -> None:
    env = {
        "BASE_DIR": str(tmp_path),
        "DEFAULT_MODEL": "codex-model",
        name: value,
    }
    with pytest.raises(ValueError):
        Settings.from_env(env)


def test_settings_require_default_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="DEFAULT_MODEL"):
        Settings.from_env({"BASE_DIR": str(tmp_path)})
