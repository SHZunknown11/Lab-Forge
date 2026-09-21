import fitz

from core.validation.pdf_renderer import PdfPreviewRenderer


def test_pdf_preview_renderer_creates_a_png_for_each_page(tmp_path):
    pdf_path = tmp_path / "report.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Page one")
    document.new_page().insert_text((72, 72), "Page two")
    document.save(pdf_path)
    document.close()

    previews = PdfPreviewRenderer().render(str(pdf_path), str(tmp_path / "previews"))

    assert len(previews) == 2
    assert all(path.endswith(".png") for path in previews)
    assert all((tmp_path / "previews" / f"page_{index:03d}.png").exists() for index in (1, 2))
