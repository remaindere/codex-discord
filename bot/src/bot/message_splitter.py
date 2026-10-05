from __future__ import annotations


def split_discord_message(text: str, limit: int = 1900) -> list[str]:
    if limit < 100:
        raise ValueError("limit is too small")
    if not text:
        return []

    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        window = remaining[: limit + 1]
        cut = max(
            window.rfind("\n\n"),
            window.rfind("\n"),
            window.rfind(" "),
        )
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
