from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class ConversationHistory:
    def __init__(self, raw_dir: Path, base_dir: Path) -> None:
        self.raw_dir = raw_dir
        self.base_dir = base_dir

    def _index_path(self, conversation_id: str) -> Path:
        return self.raw_dir / "_conversations" / f"{conversation_id}.jsonl"

    def append(self, conversation_id: str, raw_path: Path, status: str) -> None:
        path = self._index_path(conversation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "raw_path": raw_path.relative_to(self.base_dir).as_posix(),
            "status": status,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _paths(self, conversation_id: str, limit: int) -> list[Path]:
        index = self._index_path(conversation_id)
        if not index.exists():
            return []
        result: list[Path] = []
        for line in index.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                item = json.loads(line)
                if item.get("status", "answered") != "answered":
                    continue
                candidate = (self.base_dir / item["raw_path"]).resolve()
                if self.base_dir.resolve() not in candidate.parents:
                    continue
                if candidate.exists():
                    result.append(candidate)
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
        return result

    def codex(self, conversation_id: str, limit: int) -> str:
        return "\n\n---\n\n".join(
            path.read_text(encoding="utf-8")
            for path in self._paths(conversation_id, limit)
        )

    def direct(
        self, conversation_id: str, *, limit: int, char_limit: int
    ) -> list[dict[str, Any]]:
        exchanges: list[tuple[str, str]] = []
        for path in self._paths(conversation_id, limit):
            text = path.read_text(encoding="utf-8")
            try:
                question = text.split("# Question\n\n", 1)[1]
                question = question.split("\n# Attachments\n\n", 1)[0]
                question = question.split("\n# Answer\n\n", 1)[0].strip()
                answer = text.rsplit("# Answer\n\n", 1)[1].strip()
            except IndexError:
                continue
            if answer and answer != "(pending)":
                exchanges.append((question, answer))
        selected: list[tuple[str, str]] = []
        used = 0
        for question, answer in reversed(exchanges):
            size = len(question) + len(answer)
            if selected and used + size > char_limit:
                break
            selected.append((question, answer))
            used += size
        messages: list[dict[str, Any]] = []
        for question, answer in reversed(selected):
            messages.extend(
                [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": question}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": answer}],
                    },
                ]
            )
        return messages
