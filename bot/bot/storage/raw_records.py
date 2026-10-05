from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .atomic import atomic_write_text

_STATUS = re.compile(r"(?m)^status: .+$")


@dataclass(frozen=True)
class RawRecord:
    path: Path

    @classmethod
    def create_pending(
        cls,
        path: Path,
        *,
        created_at: datetime,
        message_id: int,
        channel_id: int,
        user_id: int,
        conversation_id: str,
        route: str,
        model: str,
        question: str,
        attachments: Iterable[str] = (),
    ) -> "RawRecord":
        attachment_lines = "\n".join(f"- {name}" for name in attachments)
        attachment_block = (
            f"\n# Attachments\n\n{attachment_lines}\n"
            if attachment_lines
            else ""
        )
        text = (
            "---\n"
            "source_type: discord_question\n"
            "status: pending\n"
            f"created_at: {created_at.isoformat()}\n"
            f'discord_message_id: "{message_id}"\n'
            f'discord_channel_id: "{channel_id}"\n'
            f'discord_user_id: "{user_id}"\n'
            f'conversation_id: "{conversation_id}"\n'
            f"route: {route}\n"
            f"model: {model}\n"
            "---\n\n"
            f"# Question\n\n{question}\n"
            f"{attachment_block}\n"
            "# Answer\n\n(pending)\n"
        )
        atomic_write_text(path, text)
        return cls(path)

    def update_attachments(self, attachments: Iterable[str]) -> None:
        names = tuple(attachments)
        if not names:
            return
        text = self.path.read_text(encoding="utf-8")
        block = "# Attachments\n\n" + "\n".join(f"- {name}" for name in names)
        head = text.split("\n# Answer\n\n", 1)[0].rstrip()
        if "\n# Attachments\n\n" in head:
            head = head.split("\n# Attachments\n\n", 1)[0].rstrip()
        atomic_write_text(self.path, f"{head}\n\n{block}\n\n# Answer\n\n(pending)\n")

    def finish_answered(self, answer: str, finished_at: datetime) -> None:
        text = self.path.read_text(encoding="utf-8")
        text = _STATUS.sub("status: answered", text, count=1)
        text = text.replace(
            "---\n\n# Question",
            f"finished_at: {finished_at.isoformat()}\n---\n\n# Question",
            1,
        )
        head = text.rsplit("# Answer\n\n", 1)[0]
        atomic_write_text(self.path, f"{head}# Answer\n\n{answer.rstrip()}\n")

    def finish_failed(
        self,
        *,
        stage: str,
        error_id: str,
        error_type: str,
        finished_at: datetime,
    ) -> None:
        text = self.path.read_text(encoding="utf-8")
        text = _STATUS.sub("status: failed", text, count=1)
        details = (
            f"failed_stage: {stage}\n"
            f"error_id: {error_id}\n"
            f"error_type: {error_type}\n"
            f"finished_at: {finished_at.isoformat()}\n"
        )
        text = text.replace(
            "---\n\n# Question", f"{details}---\n\n# Question", 1
        )
        head = text.rsplit("# Answer\n\n", 1)[0]
        atomic_write_text(
            self.path,
            f"{head}# Answer\n\nRequest failed. Error ID: {error_id}\n",
        )
