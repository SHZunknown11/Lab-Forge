import httpx
import pytest

from core.documents.pdf_converter import PdfConversionError, PdfConverter


def test_gotenberg_converter_posts_docx_and_writes_pdf(tmp_path):
    source = tmp_path / "report.docx"
    target = tmp_path / "report.pdf"
    source.write_bytes(b"placeholder docx")
    requests = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "http://gotenberg.test/forms/libreoffice/convert"
        assert request.headers["Gotenberg-Output-Filename"] == "report"
        assert b"report.docx" in request.content
        return httpx.Response(200, content=b"%PDF-1.7\nmock pdf")

    client = httpx.Client(transport=httpx.MockTransport(handle_request))
    converter = PdfConverter(
        backend="gotenberg",
        gotenberg_url="http://gotenberg.test",
        client=client,
    )

    result = converter.convert(str(source), str(target))

    assert result.backend == "gotenberg"
    assert target.read_bytes().startswith(b"%PDF-")
    assert len(requests) == 1


def test_gotenberg_backend_requires_a_service_url(tmp_path):
    source = tmp_path / "report.docx"
    source.write_bytes(b"placeholder docx")
    converter = PdfConverter(backend="gotenberg")

    with pytest.raises(PdfConversionError, match="GOTENBERG_URL"):
        converter.convert(str(source), str(tmp_path / "report.pdf"))
