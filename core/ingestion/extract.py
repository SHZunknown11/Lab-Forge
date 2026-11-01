"""Turn an uploaded experiment sheet into compact plain text for the model.

Everything removed here is input tokens we never pay for. Typical sheets carry
pages of copied tutorial text ("Reading Material"), hardware boilerplate,
image links and Moodle chrome; none of it changes the report.
"""
from __future__ import annotations

import html
import io
import re
from pathlib import Path

CODE_SUFFIXES = {".java", ".py", ".c", ".cpp", ".h", ".hpp", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
                 ".css", ".html", ".htm", ".m", ".sql", ".r", ".sh", ".json"}
ACCEPTED_SUFFIXES = {".txt", ".md", ".markdown", ".docx", ".pdf", ".pptx", ".zip"} | CODE_SUFFIXES
_ZIP_SKIP = re.compile(r"(^|/)(node_modules|dist|build|\.git|\.next|__pycache__|\.venv|venv|target|out)/")
_ZIP_SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}

# Hard ceiling on what we send. ~4 chars per token, so this is roughly 4.5k tokens.
MAX_PROMPT_CHARS = 18_000

# Sections that never change the report. Removed from their heading up to the
# next heading that does matter.
_DROP_HEADINGS = (
    r"reading\s+material", r"references?", r"resources", r"further\s+reading",
    r"input\s*/\s*apparatus(?:\s+used)?", r"apparatus(?:\s+used)?", r"hardware\s+requirements?",
    r"software\s+requirements?", r"viva(?:\s+voce)?\s+questions?", r"sample\s+viva", r"faqs?",
    r"evaluation\s+(?:grid|criteria)", r"marking\s+scheme", r"completion\s+requirements",
)
_KEEP_HEADINGS = (
    r"sample\s+code", r"code", r"program", r"solution", r"easy(?:\s+level)?", r"medium(?:\s+level)?",
    r"hard(?:\s+level)?", r"problem(?:\s+statement)?", r"task", r"question", r"part", r"exercise",
    r"experiment", r"aim", r"objectives?", r"outcomes?", r"output", r"procedure", r"algorithm",
    r"steps", r"theory", r"conclusion",
)
_HEADING_LINE = r"^\W{0,6}(%s)\b[^\n]{0,40}$"
_DROP_RE = re.compile(_HEADING_LINE % "|".join(_DROP_HEADINGS), re.IGNORECASE | re.MULTILINE)
_KEEP_RE = re.compile(_HEADING_LINE % "|".join(_KEEP_HEADINGS), re.IGNORECASE | re.MULTILINE)


class UnsupportedFile(ValueError):
    pass


def extract_text(data: bytes, filename: str) -> str:
    suffix = Path(filename or "sheet.txt").suffix.lower()
    if suffix in {".ppt", ".doc"}:
        raise UnsupportedFile(f"Old {suffix} files can't be read. Save it as {suffix}x (or PDF) and upload again.")
    if suffix and suffix not in ACCEPTED_SUFFIXES:
        raise UnsupportedFile(
            f"{suffix} files aren't supported. Upload a PDF, Word, PowerPoint, text file or a .zip of your project."
        )
    if suffix == ".docx":
        return _docx_text(data)
    if suffix == ".pdf":
        return _pdf_text(data)
    if suffix == ".pptx":
        return _pptx_text(data)
    if suffix == ".zip":
        return _zip_text(data)
    text = _decode(data)
    if suffix in {".html", ".htm"}:
        text = _html_text(text)
    return text


def condense(text: str) -> str:
    """Normalise and strip a sheet down to what the report needs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = text.replace("\u00ad", "").replace("\ufeff", "")
    # Images, data URIs and bare links carry no usable text.
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[(?:\*{0,2})image[^\]]*\]\[[^\]]*\]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\[image\d*\]:.*$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"data:[a-z/+.-]+;base64,[A-Za-z0-9+/=]+", "", text)
    text = re.sub(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    # Markdown escapes and emphasis noise.
    text = re.sub(r"\\([_<>*#\[\]().!-])", r"\1", text)
    text = text.replace("**", "").replace("__", "")  # bold markers cost tokens and say nothing

    if "Project files (" not in text:  # never cut sections out of source code
        text = _drop_sections(text)

    raw_lines = [line.rstrip() for line in text.split("\n")]
    filled = sum(1 for line in raw_lines if line.strip())
    # Word-to-text exports put a blank line after every line, code included.
    # When that is the pattern, blank lines carry no structure: drop them all.
    drop_blanks = filled > 0 and (len(raw_lines) - filled) >= 0.6 * filled
    lines: list[str] = []
    for line in raw_lines:
        if not line.strip():
            if not drop_blanks and lines and lines[-1] != "":
                lines.append("")
            continue
        lines.append(line)
    text = "\n".join(lines).strip()

    if len(text) > MAX_PROMPT_CHARS:
        text = text[:MAX_PROMPT_CHARS].rsplit("\n", 1)[0] + "\n[sheet truncated]"
    return text


def _drop_sections(text: str) -> str:
    out: list[str] = []
    pos = 0
    while True:
        m = _DROP_RE.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        out.append(text[pos:m.start()])
        nxt = _KEEP_RE.search(text, m.end())
        if not nxt:
            break
        pos = nxt.start()
    return "".join(out)


def _decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _docx_text(data: bytes) -> str:
    from docx import Document

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - surface as a user-facing message
        raise UnsupportedFile("This Word file couldn't be opened. Save it again as .docx and retry.") from exc
    parts: list[str] = []
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            parts.append("".join(t.text or "" for t in child.iter() if t.tag.endswith("}t")))
        elif tag == "tbl":
            for row in child.iter():
                if row.tag.endswith("}tr"):
                    cells = []
                    for cell in row.iterchildren():
                        if cell.tag.endswith("}tc"):
                            cells.append(" ".join(
                                (t.text or "") for t in cell.iter() if t.tag.endswith("}t")
                            ).strip())
                    parts.append(" | ".join(c for c in cells if c))
    return "\n".join(parts)


def _pdf_text(data: bytes) -> str:
    import pymupdf

    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if doc.page_count > 40:
                raise UnsupportedFile("This PDF has more than 40 pages. Upload only the experiment sheet.")
            text = "\n".join(page.get_text("text") for page in doc)
    except UnsupportedFile:
        raise
    except Exception as exc:  # noqa: BLE001
        raise UnsupportedFile("This PDF couldn't be read. Try exporting it again.") from exc
    if len(text.strip()) < 40:
        raise UnsupportedFile(
            "This PDF has no selectable text (it's probably a scan). Paste the text instead."
        )
    return text


def _pptx_text(data: bytes) -> str:
    """Slide text in slide order, read straight from the PPTX XML (no extra dependency)."""
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedFile("This PowerPoint file couldn't be opened. Save it again as .pptx.") from exc
    slides = sorted(
        (n for n in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[-1]).group(1)),
    )
    parts = []
    for name in slides:
        xml = zf.read(name).decode("utf-8", errors="replace")
        paragraphs = re.findall(r"<a:p>(.*?)</a:p>", xml, re.DOTALL)
        lines = ["".join(re.findall(r"<a:t>([^<]*)</a:t>", p)) for p in paragraphs]
        parts.append("\n".join(html.unescape(line) for line in lines if line.strip()))
    text = "\n\n".join(p for p in parts if p)
    if len(text.strip()) < 20:
        raise UnsupportedFile("This presentation has no readable text. Paste the experiment text instead.")
    return text


def _zip_text(data: bytes) -> str:
    """A project archive becomes "file: path" headers followed by each source file."""
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedFile("This .zip file couldn't be opened.") from exc
    parts: list[str] = []
    budget = MAX_PROMPT_CHARS
    sheets: list[str] = []
    for info in sorted(zf.infolist(), key=lambda i: i.filename):
        name = info.filename.replace("\\", "/")
        if info.is_dir() or _ZIP_SKIP.search("/" + name) or name.rsplit("/", 1)[-1] in _ZIP_SKIP_FILES:
            continue
        suffix = Path(name).suffix.lower()
        if info.file_size > 200_000:
            continue
        if suffix in {".pdf", ".docx", ".pptx", ".txt", ".md"} and len(sheets) < 2:
            try:
                sheets.append(extract_text(zf.read(info), name))
            except UnsupportedFile:
                pass
            continue
        if suffix not in CODE_SUFFIXES:
            continue
        body = _decode(zf.read(info))
        if len(body) > budget:
            break
        budget -= len(body)
        parts.append(f"file: {name}\n{body}")
    if not parts and not sheets:
        raise UnsupportedFile("The .zip has no source files or experiment sheet in it.")
    head = "\n\n".join(sheets)
    code = "\n\n".join(parts)
    return (head + "\n\nProject files (reuse this code):\n" + code) if head else (
        "Project files (write the report for this code, reuse it as is):\n" + code)


def _html_text(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", "", text)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr|pre)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)
