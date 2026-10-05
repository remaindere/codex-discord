from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic import atomic_write_json, load_json_object


@dataclass(frozen=True)
class SessionInfo:
    conversation_id: str
    model: str
    epoch: int


class SessionStore:
    def __init__(self, path: Path, default_model: str) -> None:
        self.path = path
        self.default_model = default_model
        self._lock = asyncio.Lock()

    def _entry(self, sessions: dict[str, Any], key: str) -> tuple[int, str]:
        value = sessions.get(key)
        if isinstance(value, int):
            return value, self.default_model
        if isinstance(value, dict):
            return (
                int(value.get("epoch", 1)),
                str(value.get("model", self.default_model)),
            )
        return 1, self.default_model

    async def get(self, key: str) -> SessionInfo:
        async with self._lock:
            sessions = load_json_object(self.path)
            epoch, model = self._entry(sessions, key)
            return SessionInfo(f"{key}-ep{epoch}", model, epoch)

    async def set_model(self, key: str, model: str) -> SessionInfo:
        async with self._lock:
            sessions = load_json_object(self.path)
            epoch, _ = self._entry(sessions, key)
            sessions[key] = {"epoch": epoch, "model": model}
            atomic_write_json(self.path, sessions)
            return SessionInfo(f"{key}-ep{epoch}", model, epoch)

    async def reset(self, key: str) -> SessionInfo:
        async with self._lock:
            sessions = load_json_object(self.path)
            epoch, model = self._entry(sessions, key)
            epoch += 1
            sessions[key] = {"epoch": epoch, "model": model}
            atomic_write_json(self.path, sessions)
            return SessionInfo(f"{key}-ep{epoch}", model, epoch)
