from pathlib import Path

from pypdf import PdfWriter

from bot.attachments import process_attachment
from bot.config import AttachmentLimits


def make_pdf(path: Path, pages: int, payload_size: int) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/IntegrationPayload": "x" * payload_size})
    with path.open("wb") as handle:
        writer.write(handle)


def test_representative_pdf_obeys_page_and_render_limits(tmp_path: Path) -> None:
    path = tmp_path / "representative.pdf"
    make_pdf(path, pages=6, payload_size=1_000_000)
    assert path.stat().st_size > 1_000_000

    result = process_attachment(
        path,
        AttachmentLimits(
            max_pdf_pages=10,
            max_render_pages=2,
            max_text_chars=20_000,
        ),
    )
    assert result["type"] == "pdf"
    assert result["page_count"] == 6
    assert result["needs_vision"] is True
    assert len(result["vision_images"]) <= 2


def test_pdf_over_page_limit_is_isolated_as_attachment_error(tmp_path: Path) -> None:
    path = tmp_path / "too-many-pages.pdf"
    make_pdf(path, pages=3, payload_size=0)
    result = process_attachment(path, AttachmentLimits(max_pdf_pages=2))
    assert result["type"] == "error"
    assert result["error_type"] == "AttachmentLimitError"
