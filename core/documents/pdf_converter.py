"""DOCX to PDF via Gotenberg (servers) or a local LibreOffice (development)."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import httpx


class PdfConversionError(RuntimeError):
    pass


@dataclass
class ConversionResult:
    pdf_path: str
    backend: str


_LO_LOCK = threading.Lock()
_SOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/lib/libreoffice/program/soffice",
)


def find_soffice() -> str | None:
    env = os.environ.get("SOFFICE_PATH")
    if env and Path(env).exists():
        return env
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    return next((c for c in _SOFFICE_CANDIDATES if Path(c).exists()), None)


class PdfConverter:
    def __init__(self, backend: str | None = None, gotenberg_url: str | None = None,
                 client: httpx.Client | None = None, timeout: float | None = None):
        self.backend = (backend or os.environ.get("PDF_BACKEND", "auto")).lower()
        self.gotenberg_url = (gotenberg_url if gotenberg_url is not None
                              else os.environ.get("GOTENBERG_URL", "")).rstrip("/")
        self.client = client
        self.timeout = timeout or float(os.environ.get("PDF_CONVERSION_TIMEOUT_SECONDS", "120"))

    def available(self) -> bool:
        if self.backend == "gotenberg":
            return bool(self.gotenberg_url)
        if self.backend == "libreoffice":
            return find_soffice() is not None
        return bool(self.gotenberg_url) or find_soffice() is not None

    def convert(self, docx_path: str, pdf_path: str) -> ConversionResult:
        use_gotenberg = self.backend == "gotenberg" or (self.backend == "auto" and self.gotenberg_url)
        if use_gotenberg:
            return self._gotenberg(Path(docx_path), Path(pdf_path))
        return self._libreoffice(Path(docx_path), Path(pdf_path))

    def _gotenberg(self, src: Path, dst: Path) -> ConversionResult:
        if not self.gotenberg_url:
            raise PdfConversionError("PDF_BACKEND=gotenberg needs GOTENBERG_URL to be set.")
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            resp = client.post(
                f"{self.gotenberg_url}/forms/libreoffice/convert",
                files={"files": (src.name, src.read_bytes(),
                                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                headers={"Gotenberg-Output-Filename": src.stem},
            )
        except httpx.HTTPError as exc:
            raise PdfConversionError(f"Gotenberg request failed: {exc}") from exc
        finally:
            if self.client is None:
                client.close()
        if resp.status_code != 200 or not resp.content.startswith(b"%PDF-"):
            raise PdfConversionError(f"Gotenberg returned {resp.status_code}.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(resp.content)
        return ConversionResult(str(dst), "gotenberg")

    def _libreoffice(self, src: Path, dst: Path) -> ConversionResult:
        soffice = find_soffice()
        if not soffice:
            raise PdfConversionError("LibreOffice isn't installed, so PDFs can't be made on this server.")
        profile = Path(os.environ.get("LABFORGE_LO_PROFILE", Path(__file__).resolve().parents[2] / "artifacts" / ".lo_profile")).resolve()
        outdir = dst.parent.resolve()
        outdir.mkdir(parents=True, exist_ok=True)
        cmd = [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
               "--nolockcheck", "--convert-to", "pdf", "--outdir", str(outdir), str(src.resolve())]
        with _LO_LOCK:  # one profile, one conversion at a time
            try:
                subprocess.run(cmd, capture_output=True, timeout=self.timeout,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except subprocess.TimeoutExpired as exc:
                raise PdfConversionError("PDF conversion timed out.") from exc
        produced = outdir / f"{src.stem}.pdf"
        if not produced.exists():
            raise PdfConversionError("LibreOffice didn't produce a PDF.")
        if produced.resolve() != dst.resolve():
            produced.replace(dst)
        return ConversionResult(str(dst), "libreoffice")
