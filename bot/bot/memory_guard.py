from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

STATE_ROOTS = (
    "memory/",
    "data/",
    "raw/",
)

PROTECTED_DIRS = (
    "bot",
    "provisioning",
)

ALLOWED_PREFIXES = (
    "memory/facts/",
    "memory/records/",
    "memory/wiki_pages/",
    "memory/wiki_records/",
    "data/",
    "raw/",
)

FROZEN_PATHS = {
    "memory/AGENTS.md",
    "memory/CLAUDE.md",
    "memory/WIKI_SCHEMA.md",
    "memory/WIKI_SCHEMA_PROPOSALS.md",
    "memory/raw",
}


@dataclass(frozen=True)
class ProtectedFile:
    digest: str
    content: bytes


@dataclass(frozen=True)
class RequestSnapshot:
    dirty_paths: frozenset[str]
    protected: dict[str, ProtectedFile]


@dataclass(frozen=True)
class AuditResult:
    updated: tuple[str, ...]
    reverted: tuple[str, ...]
    protected_reverted: tuple[str, ...]
    preexisting_dirty: tuple[str, ...]

"""
웬만하면 건드리지 마세요.
.git은 프로젝트 관리, .state.git은 runtime state 관리,
MemoryGuard snapshot은 bot/provisioning 보호.

Don't change this code unless you have completely mastered these codes.
.git for project managing, .state.git for runtime state protecting,
MemoryGuard snapshot for bot/provisioning protecting.
"""
class MemoryGuard:
    def __init__(self, base_dir: Path, git_dir: Path) -> None:
        self.base_dir = base_dir.resolve()
        self.git_dir = git_dir.resolve()

    def _git(
        self,
        *args: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "git",
                f"--git-dir={self.git_dir}",
                f"--work-tree={self.base_dir}",
                "-c",
                "user.email=bot@local",
                "-c",
                "user.name=codex-bot",
                *args,
            ],
            capture_output=True,
            check=check,
        )

    def _is_frozen_path(self, relative: str) -> bool:
        return any(
            relative == frozen
            or relative.startswith(f"{frozen}/")
            for frozen in FROZEN_PATHS
        )

    def _is_allowed_state_path(self, relative: str) -> bool:
        return any(
            relative.startswith(prefix)
            for prefix in ALLOWED_PREFIXES
        )

    def _is_state_path(self, relative: str) -> bool:
        return (
            relative in FROZEN_PATHS
            or any(relative.startswith(prefix) for prefix in STATE_ROOTS)
        )

    def changed_paths(self) -> set[str]:
        raw = self._git(
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ).stdout

        fields = raw.split(b"\0")
        paths: set[str] = set()
        index = 0

        while index < len(fields):
            field = fields[index]
            if not field:
                break

            status = field[:2].decode(
                "ascii",
                errors="replace",
            )
            path = field[3:].decode(
                "utf-8",
                errors="surrogateescape",
            )
            paths.add(path)

            if "R" in status or "C" in status:
                index += 1
                if index < len(fields) and fields[index]:
                    paths.add(
                        fields[index].decode(
                            "utf-8",
                            errors="surrogateescape",
                        )
                    )

            index += 1

        # .state.git may see the entire work tree because --work-tree
        # points at the project root. MemoryGuard only cares about
        # state paths; bot/ and provisioning/ are protected separately
        # through request snapshots.
        return {
            path
            for path in paths
            if self._is_state_path(path)
        }

    def _protected_snapshot(self) -> dict[str, ProtectedFile]:
        result: dict[str, ProtectedFile] = {}

        for directory in PROTECTED_DIRS:
            root = self.base_dir / directory
            if not root.exists():
                continue

            for path in root.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    content = path.read_bytes()
                    relative = path.relative_to(
                        self.base_dir
                    ).as_posix()

                    result[relative] = ProtectedFile(
                        digest=hashlib.sha256(content).hexdigest(),
                        content=content,
                    )

        return result

    def begin_request(self) -> RequestSnapshot:
        return RequestSnapshot(
            dirty_paths=frozenset(self.changed_paths()),
            protected=self._protected_snapshot(),
        )

    def audit(self, before: RequestSnapshot) -> AuditResult:
        current = self.changed_paths()

        # Only changes introduced during this request are considered.
        request_paths = current - before.dirty_paths

        protected_now = self._protected_snapshot()

        protected_changed = sorted(
            path
            for path in before.protected.keys() | protected_now.keys()
            if before.protected.get(path) != protected_now.get(path)
        )

        if protected_changed:
            print(
                "[MemoryGuard] protected files changed:",
                protected_changed,
            )

        # changed_paths() returns paths under the state roots.
        # audit() then separates allowed state changes from frozen
        # and otherwise disallowed state paths.
        bad = sorted(
            path
            for path in request_paths
            if self._is_frozen_path(path)
            or not self._is_allowed_state_path(path)
        )

        updated = sorted(
            request_paths
            - set(bad)
        )

        self._restore_request_paths(
            bad,
            before.dirty_paths,
        )
        self._restore_protected(
            protected_changed,
            before.protected,
        )

        return AuditResult(
            updated=tuple(updated),
            reverted=tuple(bad),
            protected_reverted=tuple(protected_changed),
            preexisting_dirty=tuple(
                sorted(before.dirty_paths)
            ),
        )

    def _safe_path(self, relative: str) -> Path:
        candidate = (
            self.base_dir / relative
        ).resolve()

        if (
            candidate != self.base_dir
            and self.base_dir not in candidate.parents
        ):
            raise ValueError(
                f"path escaped repository: {relative}"
            )

        return candidate

    def _is_tracked(self, relative: str) -> bool:
        return (
            self._git(
                "ls-files",
                "--error-unmatch",
                "--",
                relative,
                check=False,
            ).returncode
            == 0
        )

    def _restore_request_paths(
        self,
        paths: Iterable[str],
        preexisting_dirty: frozenset[str],
    ) -> None:
        for relative in paths:
            # Never touch a change that already existed before the request.
            if relative in preexisting_dirty:
                continue

            target = self._safe_path(relative)

            if self._is_tracked(relative):
                self._git(
                    "restore",
                    "--source=HEAD",
                    "--worktree",
                    "--",
                    relative,
                )
            elif target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()

    def _restore_protected(
        self,
        changed: Iterable[str],
        before: dict[str, ProtectedFile],
    ) -> None:
        for relative in changed:
            target = self._safe_path(relative)
            previous = before.get(relative)

            # File was created during the request.
            if previous is None:
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                elif target.exists() or target.is_symlink():
                    target.unlink()
                continue

            # File existed before the request; restore its exact contents.
            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            target.write_bytes(previous.content)

    def commit(
        self,
        paths: Iterable[str],
        message: str,
    ) -> bool:
        selected = sorted(set(paths))

        if not selected:
            return False

        invalid = [
            path
            for path in selected
            if self._is_frozen_path(path)
            or not self._is_allowed_state_path(path)
        ]

        if invalid:
            raise ValueError(
                f"refusing to commit disallowed paths: {invalid}"
            )

        self._git(
            "add",
            "--",
            *selected,
        )

        staged = self._git(
            "diff",
            "--cached",
            "--quiet",
            check=False,
        )

        if staged.returncode == 0:
            return False

        if staged.returncode != 1:
            raise subprocess.CalledProcessError(
                staged.returncode,
                staged.args,
                staged.stdout,
                staged.stderr,
            )

        self._git(
            "commit",
            "-m",
            message,
        )

        return True