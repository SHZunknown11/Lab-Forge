"""Render PDF pages to PNG so the final document can be checked by eye."""
from __future__ import annotations

from pathlib import Path

import pymupdf


class PdfPreviewRenderer:
    def __init__(self, dpi: int = 144):
        self.dpi = dpi

    def render(self, pdf_path: str, output_dir: str, max_pages: int | None = None) -> list[str]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        with pymupdf.open(pdf_path) as doc:
            for index, page in enumerate(doc, start=1):
                if max_pages and index > max_pages:
                    break
                target = out / f"page_{index:03d}.png"
                page.get_pixmap(dpi=self.dpi).save(str(target))
                paths.append(str(target))
        return paths
