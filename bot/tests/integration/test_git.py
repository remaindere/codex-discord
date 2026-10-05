import subprocess
from pathlib import Path

from bot.memory_guard import MemoryGuard


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_request_audit_preserves_existing_dirty_and_commits_only_request_paths(
    tmp_path: Path,
) -> None:
    base = tmp_path / "deployment"
    base.mkdir()
    git(base, "init", "-q")
    git(base, "config", "user.email", "test@example.invalid")
    git(base, "config", "user.name", "test")
    (base / "memory" / "facts").mkdir(parents=True)
    (base / "bot").mkdir()
    existing = base / "memory" / "facts" / "existing.md"
    existing.write_text("original\n", encoding="utf-8")
    protected = base / "bot" / "discord_bot.py"
    protected.write_text("safe\n", encoding="utf-8")
    git(base, "add", ".")
    git(base, "commit", "-qm", "initial")

    existing.write_text("user dirty change\n", encoding="utf-8")
    guard = MemoryGuard(base, base / ".git")
    before = guard.begin_request()
    created = base / "memory" / "records" / "request.md"
    created.parent.mkdir()
    created.write_text("request result\n", encoding="utf-8")
    protected.write_text("tampered\n", encoding="utf-8")

    result = guard.audit(before)
    assert result.updated == ("memory/records/request.md",)
    assert result.protected_reverted == ("bot/discord_bot.py",)
    assert protected.read_text(encoding="utf-8") == "safe\n"
    assert existing.read_text(encoding="utf-8") == "user dirty change\n"
    assert guard.commit(result.updated, "request commit")

    names = git(base, "show", "--pretty=format:", "--name-only", "HEAD").stdout
    assert names.strip() == "memory/records/request.md"
    assert "existing.md" in git(base, "status", "--short").stdout
