from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from .config import AttachmentLimits

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
PDF_EXTS = {".pdf"}
_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class DiscordAttachment(Protocol):
    id: int
    filename: str
    size: int

    async def save(self, path: Path) -> Any: ...


@dataclass(frozen=True)
class AttachmentPlan:
    attachment: DiscordAttachment
    destination: Path


class AttachmentLimitError(ValueError):
    pass


def sanitize_filename(filename: str) -> str:
    basename = Path(filename.replace("\\", "/")).name
    cleaned = _SAFE_CHARS.sub("_", basename).strip("._")
    return cleaned[:180] or "attachment"


def safe_destination(
    destination_dir: Path,
    *,
    message_id: int,
    attachment_id: int,
    filename: str,
) -> Path:
    root = destination_dir.resolve()
    safe_name = sanitize_filename(filename)
    destination = (root / f"{message_id}-{attachment_id}-{safe_name}").resolve()
    if destination.parent != root:
        raise ValueError("attachment destination escaped its directory")
    return destination


def validate_attachments(
    attachments: Sequence[DiscordAttachment],
    limits: AttachmentLimits,
) -> None:
    if len(attachments) > limits.max_count:
        raise AttachmentLimitError(
            f"attachment count exceeds {limits.max_count}"
        )
    total = 0
    for attachment in attachments:
        if attachment.size < 0:
            raise AttachmentLimitError(
                f"{attachment.filename}: file size cannot be negative"
            )
        if attachment.size > limits.max_file_bytes:
            raise AttachmentLimitError(
                f"{attachment.filename}: file size exceeds "
                f"{limits.max_file_bytes} bytes"
            )
        total += attachment.size
    if total > limits.max_total_bytes:
        raise AttachmentLimitError(
            f"total attachment size exceeds {limits.max_total_bytes} bytes"
        )


async def download_attachments(
    attachments: Sequence[DiscordAttachment],
    destination_dir: Path,
    *,
    message_id: int,
    limits: AttachmentLimits,
) -> list[Path]:
    validate_attachments(attachments, limits)
    destination_dir.mkdir(parents=True, exist_ok=True)
    plans = [
        AttachmentPlan(
            attachment=attachment,
            destination=safe_destination(
                destination_dir,
                message_id=message_id,
                attachment_id=attachment.id,
                filename=attachment.filename,
            ),
        )
        for attachment in attachments
    ]
    for plan in plans:
        await plan.attachment.save(plan.destination)
    return [plan.destination for plan in plans]


def process_attachment(path: Path, limits: AttachmentLimits) -> dict[str, Any]:
    try:
        suffix = path.suffix.casefold()
        if suffix in PDF_EXTS:
            return _process_pdf(path, limits)
        if suffix in IMAGE_EXTS:
            return {
                "type": "image",
                "filename": path.name,
                "path": str(path),
                "needs_vision": True,
                "vision_images": [str(path)],
            }
        text = path.read_text(encoding="utf-8")
        return {
            "type": "text",
            "filename": path.name,
            "path": str(path),
            "text_preview": text[: limits.max_text_chars],
        }
    except Exception as exc:
        return {
            "type": "error",
            "filename": path.name,
            "path": str(path),
            "error_type": type(exc).__name__,
        }


def _process_pdf(path: Path, limits: AttachmentLimits) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    page_count = len(reader.pages)
    if page_count > limits.max_pdf_pages:
        raise AttachmentLimitError(
            f"PDF has {page_count} pages; limit is {limits.max_pdf_pages}"
        )

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n\n".join(pages).strip()
    vision_images: list[str] = []

    if len(text) < 200:
        try:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(str(path))
            for index in range(min(len(document), limits.max_render_pages)):
                image = document[index].render(scale=2).to_pil()
                image_path = path.parent / f"{path.stem}_page_{index + 1}.png"
                image.save(image_path)
                vision_images.append(str(image_path))
        except Exception:
            vision_images = []

    return {
        "type": "pdf",
        "filename": path.name,
        "path": str(path),
        "text_preview": text[: limits.max_text_chars],
        "needs_vision": len(text) < 200,
        "vision_images": vision_images,
        "page_count": page_count,
    }
