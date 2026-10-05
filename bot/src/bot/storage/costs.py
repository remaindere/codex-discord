from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .atomic import atomic_write_json, load_json_object


def calculate_cost(
    model: str,
    usage: Mapping[str, Any],
    prices: Mapping[str, Mapping[str, float]],
) -> float:
    if model not in prices:
        raise ValueError(f"no price table for model: {model}")
    price = prices[model]
    input_tokens = int(usage.get("input_tokens", 0))
    cached = int(usage.get("cached_input_tokens", 0))
    cache_write = int(usage.get("cache_write_input_tokens", 0))
    output = int(usage.get("output_tokens", 0))
    normal_input = max(input_tokens - cached - cache_write, 0)
    return (
        normal_input * price["input"]
        + cached * price["cached_input"]
        + cache_write * price.get("cache_write", 0.0)
        + output * price["output"]
    ) / 1_000_000


class CostStore:
    def __init__(
        self,
        usage_path: Path,
        state_path: Path,
        prices: Mapping[str, Mapping[str, float]],
        alert_step: float,
    ) -> None:
        self.usage_path = usage_path
        self.state_path = state_path
        self.prices = prices
        self.alert_step = alert_step
        self._lock = asyncio.Lock()

    async def record(
        self, *, model: str, usage: Mapping[str, Any], metadata: Mapping[str, Any]
    ) -> tuple[float, float, float | None]:
        async with self._lock:
            cost = calculate_cost(model, usage, self.prices)
            record = {
                **metadata,
                "model": model,
                "usage": dict(usage),
                "estimated_cost_usd": cost,
            }
            self.usage_path.parent.mkdir(parents=True, exist_ok=True)
            with self.usage_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())

            state = load_json_object(
                self.state_path,
                {
                    "total_estimated_usd": 0.0,
                    "last_notified_threshold": 0,
                },
            )
            total = float(state["total_estimated_usd"]) + cost
            previous = int(state["last_notified_threshold"])
            crossed: float | None = None
            next_threshold = (previous + 1) * self.alert_step
            if total >= next_threshold:
                crossed = next_threshold
                previous = int(total // self.alert_step)
            state.update(
                total_estimated_usd=total,
                last_notified_threshold=previous,
            )
            atomic_write_json(self.state_path, state)
            return cost, total, crossed
