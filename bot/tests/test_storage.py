import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bot.storage.atomic import load_json_object
from bot.storage.costs import CostStore, calculate_cost
from bot.storage.raw_records import RawRecord
from bot.storage.sessions import SessionStore


def test_load_json_object_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_json_object(path)


def test_session_reset_preserves_model(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = SessionStore(tmp_path / "sessions.json", "default")
        changed = await store.set_model("user-channel", "custom")
        reset = await store.reset("user-channel")

        assert changed.conversation_id == "user-channel-ep1"
        assert reset.conversation_id == "user-channel-ep2"
        assert reset.model == "custom"

    asyncio.run(scenario())


def test_calculate_cost_accounts_for_cached_input() -> None:
    cost = calculate_cost(
        "model",
        {
            "input_tokens": 1_000_000,
            "cached_input_tokens": 250_000,
            "output_tokens": 100_000,
        },
        {
            "model": {
                "input": 2.0,
                "cached_input": 0.5,
                "output": 10.0,
            }
        },
    )
    assert cost == pytest.approx(2.625)


def test_fractional_cost_alert_threshold_is_not_truncated(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        store = CostStore(
            tmp_path / "usage.jsonl",
            tmp_path / "cost-state.json",
            {"model": {"input": 1.0, "cached_input": 1.0, "output": 1.0}},
            alert_step=0.5,
        )
        _, total, crossed = await store.record(
            model="model",
            usage={"input_tokens": 500_000},
            metadata={"request_id": "one"},
        )

        assert total == pytest.approx(0.5)
        assert crossed == pytest.approx(0.5)

    asyncio.run(scenario())


def test_raw_record_can_finish_failed(tmp_path: Path) -> None:
    path = tmp_path / "request.md"
    created = datetime(2026, 9, 6, tzinfo=UTC)
    record = RawRecord.create_pending(
        path,
        created_at=created,
        message_id=10,
        channel_id=20,
        user_id=30,
        conversation_id="conversation-ep1",
        route="codex",
        model="model",
        question="question",
    )
    record.finish_failed(
        stage="model",
        error_id="err-123",
        error_type="RuntimeError",
        finished_at=created,
    )

    text = path.read_text(encoding="utf-8")
    assert "status: failed" in text
    assert "failed_stage: model" in text
    assert "error_id: err-123" in text
    assert text.endswith("Request failed. Error ID: err-123\n")
