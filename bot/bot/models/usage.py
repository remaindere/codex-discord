from __future__ import annotations

from typing import Any, Mapping


def normalize_usage(value: Mapping[str, Any] | None) -> dict[str, int]:
    data = dict(value or {})
    input_details = data.get("input_tokens_details") or {}
    output_details = data.get("output_tokens_details") or {}
    return {
        "input_tokens": int(data.get("input_tokens", 0) or 0),
        "cached_input_tokens": int(
            data.get("cached_input_tokens", input_details.get("cached_tokens", 0))
            or 0
        ),
        "cache_write_input_tokens": int(
            data.get("cache_write_input_tokens", 0) or 0
        ),
        "output_tokens": int(data.get("output_tokens", 0) or 0),
        "reasoning_output_tokens": int(
            data.get(
                "reasoning_output_tokens",
                output_details.get("reasoning_tokens", 0),
            )
            or 0
        ),
    }
