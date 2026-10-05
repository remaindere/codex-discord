from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bot.memory_guard import MemoryGuard


def run_git(
    cwd: Path,
    *args: str,
    git_dir: Path | None = None,
) -> subprocess.CompletedProcess:
    command = ["git"]

    if git_dir is not None:
        command.append(f"--git-dir={git_dir}")

    command.extend(args)

    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path]:
    """
    실제 프로젝트 + 별도의 .state.git을 만든다.

    구조:
        project/
        ├── .git/          실제 프로젝트 Git
        └── .state.git/   MemoryGuard가 사용하는 Git
    """
    base = tmp_path / "project"
    base.mkdir()

    # 일반 프로젝트 Git
    run_git(base, "init")
    run_git(
        base,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "config",
        "user.email",
        "test@example.com",
    )
    run_git(
        base,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "config",
        "user.name",
        "test",
    )

    # MemoryGuard 전용 state Git
    state_git = base / ".state.git"
    run_git(base, "init", "--bare", str(state_git))

    # state Git의 work-tree에서 사용할 파일 생성
    allowed_files = {
        "memory/facts/existing.json": '{"value": "original"}',
        "memory/records/existing.json": '{"record": "original"}',
        "memory/wiki_pages/existing.md": "# Original",
        "memory/wiki_records/existing.json": '{"wiki": "original"}',
        "data/existing.json": '{"data": "original"}',
        "raw/existing.txt": "original raw",
        "memory/AGENTS.md": "AGENTS ORIGINAL\n",
        "memory/CLAUDE.md": "CLAUDE ORIGINAL\n",
        "memory/WIKI_SCHEMA.md": "SCHEMA ORIGINAL\n",
        "memory/WIKI_SCHEMA_PROPOSALS.md": "PROPOSALS ORIGINAL\n",
        "memory/raw/frozen.txt": "FROZEN RAW ORIGINAL\n",
        "bot/main.py": "print('bot original')\n",
        "provisioning/setup.py": "print('provisioning original')\n",
    }

    for relative, content in allowed_files.items():
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    # state Git에 필요한 state/frozen 파일을 commit한다.
    state_paths = [
        "memory/facts/existing.json",
        "memory/records/existing.json",
        "memory/wiki_pages/existing.md",
        "memory/wiki_records/existing.json",
        "data/existing.json",
        "raw/existing.txt",
        "memory/AGENTS.md",
        "memory/CLAUDE.md",
        "memory/WIKI_SCHEMA.md",
        "memory/WIKI_SCHEMA_PROPOSALS.md",
        "memory/raw/frozen.txt",
    ]

    run_git(
        base,
        f"--git-dir={state_git}",
        f"--work-tree={base}",
        "add",
        "--",
        *state_paths,
    )

    run_git(
        base,
        f"--git-dir={state_git}",
        f"--work-tree={base}",
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-m",
        "initial state",
    )

    return base, state_git


@pytest.fixture
def guard(repo: tuple[Path, Path]) -> MemoryGuard:
    base, state_git = repo
    return MemoryGuard(base, state_git)


def write(base: Path, relative: str, content: str) -> None:
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read(base: Path, relative: str) -> str:
    return (base / relative).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# allowed state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative, content",
    [
        ("memory/facts/new.json", '{"new": true}'),
        ("memory/records/new.json", '{"new": true}'),
        ("memory/wiki_pages/new.md", "# New"),
        ("memory/wiki_records/new.json", '{"new": true}'),
        ("data/new.json", '{"new": true}'),
        ("raw/new.txt", "new raw"),
    ],
)
def test_allowed_new_files_are_kept(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
    relative: str,
    content: str,
) -> None:
    base, _ = repo

    before = guard.begin_request()

    write(base, relative, content)

    result = guard.audit(before)

    assert relative in result.updated
    assert relative not in result.reverted
    assert (base / relative).exists()
    assert read(base, relative) == content


@pytest.mark.parametrize(
    "relative",
    [
        "memory/facts/existing.json",
        "memory/records/existing.json",
        "memory/wiki_pages/existing.md",
        "memory/wiki_records/existing.json",
        "data/existing.json",
        "raw/existing.txt",
    ],
)
def test_allowed_existing_files_can_be_modified(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
    relative: str,
) -> None:
    base, _ = repo

    before = guard.begin_request()

    write(base, relative, "modified")

    result = guard.audit(before)

    assert relative in result.updated
    assert relative not in result.reverted
    assert read(base, relative) == "modified"


# ---------------------------------------------------------------------------
# frozen files
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative, original",
    [
        ("memory/AGENTS.md", "AGENTS ORIGINAL\n"),
        ("memory/CLAUDE.md", "CLAUDE ORIGINAL\n"),
        ("memory/WIKI_SCHEMA.md", "SCHEMA ORIGINAL\n"),
        (
            "memory/WIKI_SCHEMA_PROPOSALS.md",
            "PROPOSALS ORIGINAL\n",
        ),
    ],
)
def test_frozen_files_are_restored_after_modification(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
    relative: str,
    original: str,
) -> None:
    base, _ = repo

    before = guard.begin_request()

    write(base, relative, "ATTACKED\n")

    result = guard.audit(before)

    assert relative in result.protected_reverted
    assert read(base, relative) == original


def test_frozen_file_created_during_request_is_deleted(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    relative = "memory/CLAUDE_NEW.md"

    before = guard.begin_request()

    write(base, relative, "malicious")

    result = guard.audit(before)

    assert relative in result.reverted
    assert not (base / relative).exists()


def test_frozen_file_deleted_during_request_is_restored(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    relative = "memory/CLAUDE.md"

    before = guard.begin_request()

    (base / relative).unlink()

    result = guard.audit(before)

    assert relative in result.protected_reverted
    assert read(base, relative) == "CLAUDE ORIGINAL\n"


def test_frozen_directory_contents_are_restored(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    before = guard.begin_request()

    write(base, "memory/raw/frozen.txt", "ATTACKED\n")

    result = guard.audit(before)

    assert "memory/raw/frozen.txt" in result.protected_reverted
    assert read(base, "memory/raw/frozen.txt") == "FROZEN RAW ORIGINAL\n"


def test_new_file_inside_frozen_directory_is_removed(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    relative = "memory/raw/new.txt"

    before = guard.begin_request()

    write(base, relative, "malicious")

    result = guard.audit(before)

    assert relative in result.protected_reverted or relative in result.reverted
    assert not (base / relative).exists()


def test_deleted_file_inside_frozen_directory_is_restored(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    relative = "memory/raw/frozen.txt"

    before = guard.begin_request()

    (base / relative).unlink()

    result = guard.audit(before)

    assert relative in result.protected_reverted
    assert read(base, relative) == "FROZEN RAW ORIGINAL\n"


# ---------------------------------------------------------------------------
# bot / provisioning
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative, original",
    [
        ("bot/main.py", "print('bot original')\n"),
        (
            "provisioning/setup.py",
            "print('provisioning original')\n",
        ),
    ],
)
def test_protected_files_are_restored(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
    relative: str,
    original: str,
) -> None:
    base, _ = repo

    before = guard.begin_request()

    write(base, relative, "print('modified')\n")

    result = guard.audit(before)

    assert relative in result.protected_reverted
    assert read(base, relative) == original


@pytest.mark.parametrize(
    "relative",
    [
        "bot/new.py",
        "provisioning/new.py",
    ],
)
def test_new_protected_files_are_deleted(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
    relative: str,
) -> None:
    base, _ = repo

    before = guard.begin_request()

    write(base, relative, "print('new')\n")

    result = guard.audit(before)

    assert relative in result.protected_reverted
    assert not (base / relative).exists()


@pytest.mark.parametrize(
    "relative, original",
    [
        ("bot/main.py", "print('bot original')\n"),
        (
            "provisioning/setup.py",
            "print('provisioning original')\n",
        ),
    ],
)
def test_deleted_protected_files_are_restored(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
    relative: str,
    original: str,
) -> None:
    base, _ = repo

    before = guard.begin_request()

    (base / relative).unlink()

    result = guard.audit(before)

    assert relative in result.protected_reverted
    assert read(base, relative) == original


# ---------------------------------------------------------------------------
# pre-existing dirty state
# ---------------------------------------------------------------------------


def test_preexisting_dirty_state_is_not_reverted(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    relative = "memory/facts/existing.json"

    # Request 시작 전에 이미 변경되어 있음.
    write(base, relative, "preexisting\n")

    before = guard.begin_request()

    # 이번 요청에서 다시 변경.
    write(base, relative, "changed again\n")

    result = guard.audit(before)

    # 기존 dirty path이므로 request_paths에 포함되지 않는다.
    assert relative in result.preexisting_dirty
    assert relative not in result.reverted

    # 현재 구현의 정책상 변경을 건드리지 않는다.
    assert read(base, relative) == "changed again\n"


# ---------------------------------------------------------------------------
# disallowed state paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "memory/random.txt",
        "memory/config.json",
        "memory/unknown/foo.txt",
    ],
)
def test_disallowed_memory_paths_are_removed(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
    relative: str,
) -> None:
    base, _ = repo

    before = guard.begin_request()

    write(base, relative, "not allowed")

    result = guard.audit(before)

    assert relative in result.reverted
    assert not (base / relative).exists()


# ---------------------------------------------------------------------------
# path safety
# ---------------------------------------------------------------------------


def test_safe_path_rejects_escape(
    guard: MemoryGuard,
) -> None:
    with pytest.raises(ValueError, match="path escaped repository"):
        guard._safe_path("../../outside.txt")


def test_safe_path_accepts_repository_path(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    result = guard._safe_path("memory/facts/example.json")

    assert result == (base / "memory/facts/example.json").resolve()


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------


def test_commit_allowed_state_file(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, state_git = repo

    relative = "memory/facts/commit.json"

    before = guard.begin_request()
    write(base, relative, '{"commit": true}')

    audit = guard.audit(before)

    assert relative in audit.updated

    committed = guard.commit(
        audit.updated,
        "add committed fact",
    )

    assert committed is True

    result = run_git(
        base,
        f"--git-dir={state_git}",
        f"--work-tree={base}",
        "log",
        "-1",
        "--pretty=%s",
    )

    assert result.stdout.strip() == "add committed fact"


def test_commit_returns_false_when_nothing_selected(
    guard: MemoryGuard,
) -> None:
    assert guard.commit([], "nothing") is False


@pytest.mark.parametrize(
    "relative",
    [
        "memory/CLAUDE.md",
        "memory/AGENTS.md",
        "memory/WIKI_SCHEMA.md",
        "memory/raw/frozen.txt",
        "memory/random.txt",
        "bot/main.py",
        "provisioning/setup.py",
    ],
)
def test_commit_rejects_disallowed_paths(
    guard: MemoryGuard,
    relative: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="refusing to commit disallowed paths",
    ):
        guard.commit([relative], "should fail")


# ---------------------------------------------------------------------------
# rename / copy
# ---------------------------------------------------------------------------


def test_rename_is_detected(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    source = base / "memory/facts/existing.json"
    target = base / "memory/facts/renamed.json"

    before = guard.begin_request()

    source.rename(target)

    current = guard.changed_paths()

    assert "memory/facts/renamed.json" in current


def test_rename_into_disallowed_path_is_reverted(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    source = base / "memory/facts/existing.json"
    target = base / "memory/random.json"

    before = guard.begin_request()

    source.rename(target)

    result = guard.audit(before)

    assert "memory/random.json" in result.reverted

    # 기존 tracked 파일은 HEAD 상태로 복구되어야 한다.
    assert source.exists()
    assert not target.exists()


# ---------------------------------------------------------------------------
# symlink / filesystem edge cases
# ---------------------------------------------------------------------------


def test_symlink_escape_is_rejected_by_safe_path(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    outside = base.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    link = base / "memory/facts/link.txt"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)

    with pytest.raises(ValueError, match="path escaped repository"):
        guard._safe_path("memory/facts/link.txt")


# ---------------------------------------------------------------------------
# snapshot sanity
# ---------------------------------------------------------------------------


def test_begin_request_captures_frozen_and_protected_files(
    guard: MemoryGuard,
) -> None:
    snapshot = guard.begin_request()

    assert "memory/CLAUDE.md" in snapshot.frozen
    assert "memory/AGENTS.md" in snapshot.frozen
    assert "memory/WIKI_SCHEMA.md" in snapshot.frozen
    assert "memory/raw/frozen.txt" in snapshot.frozen

    assert "bot/main.py" in snapshot.protected
    assert "provisioning/setup.py" in snapshot.protected


def test_snapshot_digest_matches_content(
    guard: MemoryGuard,
) -> None:
    snapshot = guard.begin_request()

    protected = snapshot.protected["bot/main.py"]

    import hashlib

    expected = hashlib.sha256(
        protected.content
    ).hexdigest()

    assert protected.digest == expected


# ---------------------------------------------------------------------------
# multiple changes in one request
# ---------------------------------------------------------------------------


def test_multiple_changes_are_audited_together(
    guard: MemoryGuard,
    repo: tuple[Path, Path],
) -> None:
    base, _ = repo

    before = guard.begin_request()

    write(
        base,
        "memory/facts/allowed.json",
        '{"allowed": true}',
    )

    write(
        base,
        "memory/not_allowed.json",
        '{"bad": true}',
    )

    write(
        base,
        "memory/CLAUDE.md",
        "modified",
    )

    write(
        base,
        "bot/main.py",
        "modified bot",
    )

    result = guard.audit(before)

    assert "memory/facts/allowed.json" in result.updated

    assert "memory/not_allowed.json" in result.reverted

    assert "memory/CLAUDE.md" in result.protected_reverted

    assert "bot/main.py" in result.protected_reverted

    assert (
        read(base, "memory/facts/allowed.json")
        == '{"allowed": true}'
    )

    assert not (base / "memory/not_allowed.json").exists()

    assert (
        read(base, "memory/CLAUDE.md")
        == "CLAUDE ORIGINAL\n"
    )

    assert (
        read(base, "bot/main.py")
        == "print('bot original')\n"
    )