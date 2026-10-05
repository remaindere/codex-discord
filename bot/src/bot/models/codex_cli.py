from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .usage import normalize_usage


class CodexCli:
    def __init__(
        self, *, working_directory: Path, timeout_seconds: int, supports_vision: bool
    ) -> None:
        self.working_directory = working_directory
        self.timeout_seconds = timeout_seconds
        self.supports_vision = supports_vision

    def run(
        self, prompt: str, *, model: str, image_paths: list[Path] | None = None
    ) -> tuple[str, dict[str, int]]:
        executable = shutil.which("codex")
        if not executable:
            raise RuntimeError("codex 실행 파일을 PATH에서 찾을 수 없습니다.")
        command = [
            executable,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--model",
            model,
        ]
        if self.supports_vision:
            for path in image_paths or []:
                command.extend(["--image", str(path)])
        try:
            process = subprocess.run(
                command,
                input=prompt,
                cwd=self.working_directory,
                capture_output=True,
                text=True,
                check=False,
                env=os.environ.copy(),
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"codex exec가 {self.timeout_seconds}초 안에 완료되지 않았습니다."
            ) from exc
        if process.returncode:
            raise RuntimeError(
                f"codex exec failed (exit={process.returncode}): "
                f"{process.stderr.strip() or 'unknown error'}"
            )

        answers: list[str] = []
        usage: dict[str, Any] = {}
        errors: list[str] = []
        for raw_line in process.stdout.splitlines():
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            if event_type == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message" and item.get("text"):
                    answers.append(item["text"])
                elif item.get("type") == "error":
                    errors.append(item.get("message") or str(item))
            elif event_type == "turn.completed":
                usage = event.get("usage") or {}
            elif event_type in {"turn.failed", "error"}:
                error = event.get("error") or event.get("message") or event
                if isinstance(error, dict):
                    error = error.get("message") or str(error)
                raise RuntimeError(f"Codex error: {error}")
        answer = "\n".join(answers).strip()
        if not answer:
            detail = f" ({'; '.join(errors)})" if errors else ""
            raise RuntimeError(f"Codex가 최종 답변을 반환하지 않았습니다.{detail}")
        return answer, normalize_usage(usage)
