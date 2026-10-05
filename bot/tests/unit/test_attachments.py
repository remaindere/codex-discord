from dataclasses import dataclass
from pathlib import Path

import pytest

from bot.attachments import (
    AttachmentLimitError,
    safe_destination,
    sanitize_filename,
    validate_attachments,
)
from bot.config import AttachmentLimits


@dataclass
class FakeAttachment:
    filename: str
    size: int
    id: int = 1


def test_filename_removes_path_components() -> None:
    assert sanitize_filename("../../secret.txt") == "secret.txt"
    assert sanitize_filename(r"..\..\secret.txt") == "secret.txt"


def test_destination_stays_inside_root(tmp_path: Path) -> None:
    destination = safe_destination(
        tmp_path,
        message_id=10,
        attachment_id=20,
        filename="../../secret.txt",
    )
    assert destination.parent == tmp_path.resolve()
    assert destination.name == "10-20-secret.txt"


def test_empty_name_gets_fallback() -> None:
    assert sanitize_filename("../..") == "attachment"


def test_negative_attachment_size_is_rejected() -> None:
    with pytest.raises(AttachmentLimitError, match="cannot be negative"):
        validate_attachments(
            [FakeAttachment("bad.bin", -1)],
            AttachmentLimits(),
        )


def test_total_attachment_limit_is_enforced() -> None:
    limits = AttachmentLimits(
        max_count=2,
        max_file_bytes=10,
        max_total_bytes=15,
    )
    with pytest.raises(AttachmentLimitError, match="total attachment size"):
        validate_attachments(
            [FakeAttachment("one", 8), FakeAttachment("two", 8)],
            limits,
        )
