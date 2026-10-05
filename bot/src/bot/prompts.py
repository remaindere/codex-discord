from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def attachment_context(
    metadata: list[dict[str, Any]], *, vision_enabled: bool
) -> tuple[str, list[Path]]:
    if not metadata:
        return "(no attachments)", []
    parts: list[str] = []
    images: list[Path] = []
    for item in metadata:
        parts.append(f"[Attachment: {item.get('filename', 'unknown')}]")
        if item.get("type") == "error":
            parts.append(f"Attachment processing failed: {item.get('error_type')}")
        elif item.get("type") == "image":
            parts.append(
                "Image is available for visual inspection."
                if vision_enabled
                else "Image was saved, but vision input is disabled."
            )
        else:
            preview = item.get("text_preview", "")
            if preview:
                parts.append(
                    "Extracted content (JSON encoded):\n"
                    + json.dumps(preview, ensure_ascii=False)
                )
            if item.get("needs_vision") and not vision_enabled:
                parts.append(
                    "This PDF appears scanned, but vision input is disabled; "
                    "its rendered pages were not sent to the model."
                )
        if vision_enabled:
            for value in item.get("vision_images", []):
                path = Path(value)
                if path.exists():
                    images.append(path)
        parts.append("")
    return "\n".join(parts).strip(), images


def codex_prompt(question: str, history: str, attachments: str) -> str:
    return f"""You are a personal assistant for a single user on Discord.
The working directory is long-term memory.
Search facts/ for relevant prior context when useful.
Do not modify anything outside facts/ and records/.
Before modifying facts/ or records/, read AGENTS.md and WIKI_SCHEMA.md.
If only answering without memory changes, do not read those files merely as a ritual.
Output only the final response.
If new information is genuinely useful long-term, update facts/ and write a record.

# Recent Conversation History
{history}

# Attachments Context
{attachments}

# Current User Message
{question}
""".strip()
