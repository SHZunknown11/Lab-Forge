"""Deterministic DOCX writer. The model never touches layout; this code does."""
from __future__ import annotations

import copy
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image

from core.documents.templates import get_template
from core.schemas import MetaField, ReportDraft

MAX_IMAGE_WIDTH_IN = 6.0
MAX_IMAGE_HEIGHT_IN = 8.0  # one page, below the header
CODE_CHAR_PT = 6.0  # Courier New at 10 pt is 0.6 em wide
CODE_WRAP_INDENT = 4  # extra characters of indent for the wrapped part of a long line
_BRACE_LANGS = {"java", "c", "cpp", "javascript", "react"}


class ReportWriter:
    def write(
        self,
        template_id: str,
        output_path: str | Path,
        fields: list[MetaField],
        draft: ReportDraft,
        task_images: list[list[tuple[Path, float]]],
        signature: str = "",
    ) -> Path:
        """task_images[i] lists (image path, pixels per inch) for task i, in display order.

        One task uses the single-program layout (1. Aim, 2. Objective,
        3. Implementation/Code, 4. Output, 5. Learning Outcome); several tasks
        get a section each, with the aim before and the outcomes after.
        """
        tpl = get_template(template_id)
        doc = Document(str(tpl.path))
        body = doc.element.body
        paras = doc.paragraphs
        if len(paras) < 6:
            raise ValueError(f"Template {tpl.id} needs a title and four metadata lines.")

        _carry_header_to_last_section(body)
        # Drop everything after the metadata block except the final section properties.
        keep = {p._p for p in paras[:6]}
        for child in list(body):
            if child.tag == qn("w:sectPr") or child in keep:
                continue
            body.remove(child)

        if tpl.header_png and tpl.header_png.exists():
            _picture_header(doc, tpl.header_png, tpl.header_at_in)
        self._title(paras[0], draft)
        self._metadata(paras[1], paras[2:6], fields, tpl.meta_size)
        outcomes = [o.strip() for o in draft.learning_outcomes if o.strip()]

        if len(draft.tasks) == 1:
            task = draft.tasks[0]
            images = task_images[0] if task_images else []
            n = 1
            if draft.aim.strip():
                self._item(doc, n, "Aim", draft.aim.strip(), top=True)
                n += 1
            if task.problem.strip() and _distinct(task.problem, draft.aim):
                self._item(doc, n, "Problem Statement", task.problem.strip(), top=True)
                n += 1
            n = self._task_body(doc, task, images, n, signature, top=True, code_label="Implementation/Code")
            if outcomes:
                self._item(doc, n, "Learning Outcome", top=True)
                for o in outcomes:
                    self._bullet(doc, o)
        else:
            if draft.aim.strip():
                p = doc.add_paragraph(style=_style(doc, "Body Text"))
                p.paragraph_format.space_before = Pt(14)
                p.paragraph_format.line_spacing = 1.5
                p.add_run("Aim: ").bold = True
                p.add_run(draft.aim.strip())
            for index, task in enumerate(draft.tasks):
                heading = task.title.strip() or f"Task {index + 1}"
                h = doc.add_paragraph(style=_style(doc, "Heading 1"))
                h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                h.paragraph_format.keep_with_next = True
                h.paragraph_format.space_before = Pt(20)
                h.paragraph_format.space_after = Pt(6)
                h.add_run(heading.upper() if tpl.upper_headings else heading).bold = True
                n = 1
                if task.problem.strip():
                    self._item(doc, n, "Problem Statement", task.problem.strip())
                    n += 1
                images = task_images[index] if index < len(task_images) else []
                self._task_body(doc, task, images, n, signature, top=False, code_label="Code")
            if outcomes:
                p = doc.add_paragraph(style=_style(doc, "Body Text"))
                p.paragraph_format.space_before = Pt(18)
                p.paragraph_format.keep_with_next = True
                p.add_run("Learning Outcomes:").bold = True
                for o in outcomes:
                    self._bullet(doc, o)

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))
        return out

    # ── pieces ─────────────────────────────────────────────────────
    def _title(self, p, draft: ReportDraft) -> None:
        no = draft.experiment_no.strip()
        text = draft.title.strip() or (f"Experiment {no}" if no else "Experiment")
        runs = p.runs
        if not runs:
            p.add_run(text).bold = True
            return
        runs[0].text = text
        for r in runs[1:]:
            r._r.getparent().remove(r._r)

    def _metadata(self, anchor, lines, fields: list[MetaField], size: int) -> None:
        # The second line carries the template's line spacing; the first has none.
        model = lines[1] if len(lines) > 1 else lines[0]
        proto = copy.deepcopy(model._p)
        tab_pos = None
        stops = model.paragraph_format.tab_stops
        if len(stops):
            tab_pos = stops[0].position
        for p in lines:
            p._p.getparent().remove(p._p)

        usable = [f for f in fields if f.label.strip()]
        # Two per line, unless the first is too long to reach the tab stop:
        # then each gets its own line instead of wrapping mid-value.
        fits = 30 if size >= 14 else 38
        pairs: list[list[MetaField]] = []
        i = 0
        while i < len(usable):
            first = usable[i]
            if i + 1 < len(usable) and len(f"{first.label}: {first.value}") <= fits:
                pairs.append([first, usable[i + 1]])
                i += 2
            else:
                pairs.append([first])
                i += 1
        prev = anchor._p
        for pair in pairs:
            el = copy.deepcopy(proto)
            for child in list(el):
                if child.tag != qn("w:pPr"):
                    el.remove(child)
            prev.addnext(el)
            prev = el
            from docx.text.paragraph import Paragraph

            para = Paragraph(el, anchor._parent)
            if tab_pos is not None and not len(para.paragraph_format.tab_stops):
                para.paragraph_format.tab_stops.add_tab_stop(tab_pos)
            for i, f in enumerate(pair):
                if i:
                    self._meta_run(para, "\t", size)
                label = f.label.strip().rstrip(":")
                self._meta_run(para, f"{label}: {f.value.strip()}", size)

    @staticmethod
    def _meta_run(para, text: str, size: int) -> None:
        r = para.add_run(text)
        r.bold = True
        r.font.size = Pt(size)

    def _task_body(self, doc, task, images, n: int, signature: str, top: bool, code_label: str) -> int:
        objectives = [o.strip() for o in task.objectives if o.strip()]
        if objectives:
            self._item(doc, n, "Objective", top=top)
            for obj in objectives:
                self._bullet(doc, obj)
            n += 1
        files = [f for f in task.files if f.code.strip()]
        if files:
            self._item(doc, n, code_label, top=top)
            for f in files:
                if len(files) > 1:
                    label = doc.add_paragraph()
                    label.paragraph_format.left_indent = Inches(0.5)
                    label.paragraph_format.space_before = Pt(8)
                    label.paragraph_format.keep_with_next = True
                    label.add_run(f"{f.name}:").bold = True
                self._code(doc, f.code, task.language, f.name, signature)
            n += 1
        self._item(doc, n, "Output", top=top)
        if images:
            for path, ppi in images:
                self._image(doc, path, ppi)
        else:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.5)
            r = p.add_run("[Attach output screenshot]")
            r.italic = True
            r.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
        return n + 1

    def _item(self, doc, n: int, label: str, text: str | None = None, top: bool = False) -> None:
        p = doc.add_paragraph(style=_style(doc, "List Paragraph"))
        fmt = p.paragraph_format
        fmt.left_indent = Inches(0.3 if top else 0.5)
        fmt.first_line_indent = Inches(-0.3)
        fmt.space_before = Pt(14 if top else 10)
        fmt.space_after = Pt(4)
        fmt.line_spacing = 1.5 if text else None
        if not text:
            fmt.keep_with_next = True
        r = p.add_run(f"{n}.  {label}:")
        r.bold = True
        r.font.size = Pt(13)
        if text:
            p.add_run(" " + text)

    def _bullet(self, doc, text: str) -> None:
        p = doc.add_paragraph()
        fmt = p.paragraph_format
        fmt.left_indent = Inches(0.85)
        fmt.first_line_indent = Inches(-0.2)
        fmt.space_after = Pt(2)
        p.add_run("•  " + text)

    def _code(self, doc, code: str, language: str, name: str = "", signature: str = "") -> None:
        code = tidy_code(code, language)
        line = comment_line(signature, language, name) if signature else ""
        if line:
            code = line + "\n" + code
        lines = code.split("\n")
        for line in lines:
            p = doc.add_paragraph()
            fmt = p.paragraph_format
            # Hanging indent: the line starts at its own indentation and a wrapped remainder
            # continues 4 characters further in, instead of at the left margin.
            lead = len(line) - len(line.lstrip(" "))
            fmt.left_indent = Inches(0.5) + Pt(CODE_CHAR_PT * (lead + CODE_WRAP_INDENT))
            fmt.first_line_indent = -Pt(CODE_CHAR_PT * CODE_WRAP_INDENT)
            fmt.space_before = Pt(0)
            fmt.space_after = Pt(0)
            fmt.line_spacing = Pt(12)
            r = p.add_run(line.lstrip(" "))
            r.font.name = "Courier New"
            r._r.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Courier New")
            r.font.size = Pt(10)

    def _image(self, doc, path: Path, ppi: float) -> None:
        try:
            with Image.open(path) as img:
                width_px, height_px = img.size
        except OSError:
            return
        width_in = min(MAX_IMAGE_WIDTH_IN, width_px / max(ppi, 1))
        width_in = min(width_in, MAX_IMAGE_HEIGHT_IN * width_px / max(height_px, 1))  # never taller than a page
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(6)
        p.add_run().add_picture(str(path), width=Inches(width_in))


def tidy_code(code: str, language: str) -> str:
    code = code.replace("\r\n", "\n").expandtabs(4).strip("\n")
    lines = [line.rstrip() for line in code.split("\n")]
    if language in _BRACE_LANGS:
        lines = [line for line in lines if line.strip()]
    else:
        out: list[str] = []
        for line in lines:
            if not line.strip() and out and not out[-1].strip():
                continue
            out.append(line)
        lines = out
    return "\n".join(lines)


def _picture_header(doc, png: Path, at_in: tuple[float, float], dpi: float = 200) -> None:
    """Replace each section's header with `png`, floating at `at_in` inches from the page's top-left.

    Behind the text and anchored to the page, so it never moves the body, and it looks the same
    in Word and in LibreOffice's PDF whatever fonts the machine has.
    """
    from docx.oxml import parse_xml
    from docx.shared import Emu

    with Image.open(png) as img:
        width_in, height_in = img.width / dpi, img.height / dpi
    for section in doc.sections:
        for header in (section.header, section.first_page_header, section.even_page_header):
            if header.is_linked_to_previous:
                continue
            for el in list(header._element):
                header._element.remove(el)
            run = header.add_paragraph().add_run()
            inline = run.add_picture(str(png), width=Inches(width_in), height=Inches(height_in))._inline
            x, y = Inches(at_in[0]), Inches(at_in[1])
            anchor = parse_xml(
                '<wp:anchor xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
                'distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="1" behindDoc="1" '
                'locked="0" layoutInCell="1" allowOverlap="1">'
                '<wp:simplePos x="0" y="0"/>'
                f'<wp:positionH relativeFrom="page"><wp:posOffset>{int(x)}</wp:posOffset></wp:positionH>'
                f'<wp:positionV relativeFrom="page"><wp:posOffset>{int(y)}</wp:posOffset></wp:positionV>'
                f'<wp:extent cx="{int(Emu(Inches(width_in)))}" cy="{int(Emu(Inches(height_in)))}"/>'
                '<wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/></wp:anchor>')
            for tag in ("docPr", "cNvGraphicFramePr", "graphic"):
                anchor.append(inline.find(qn(f"wp:{tag}")) if tag != "graphic" else inline.find(qn("a:graphic")))
            inline.getparent().replace(inline, anchor)


def _carry_header_to_last_section(body) -> None:
    """Templates often attach the header to an earlier section and let later
    sections inherit it. Earlier sections are removed, so move the references."""
    final = body.find(qn("w:sectPr"))
    if final is None:
        return
    refs = (qn("w:headerReference"), qn("w:footerReference"))
    if any(child.tag in refs for child in final):
        return
    for sect in body.iter(qn("w:sectPr")):
        if sect is final:
            continue
        found = [copy.deepcopy(c) for c in sect if c.tag in refs]
        if found:
            for ref in reversed(found):
                final.insert(0, ref)
            return


_COMMENT = {"python": "# {}", "r": "# {}", "shell": "# {}", "sql": "-- {}", "matlab": "% {}", "html": "<!-- {} -->"}
_COMMENT_BY_EXT = {".py": "# {}", ".r": "# {}", ".sh": "# {}", ".sql": "-- {}", ".m": "% {}",
                   ".html": "<!-- {} -->", ".htm": "<!-- {} -->", ".css": "/* {} */", ".json": None}


def comment_line(text: str, language: str, name: str = "") -> str:
    ext = Path(name).suffix.lower()
    pattern = _COMMENT_BY_EXT.get(ext, _COMMENT.get(language, "// {}")) if ext else _COMMENT.get(language, "// {}")
    return pattern.format(text) if pattern else ""


def _distinct(a: str, b: str) -> bool:
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()  # noqa: E731
    return norm(a) != norm(b) and norm(a) not in norm(b)


def safe_filename(*parts: str) -> str:
    text = "_".join(p for p in parts if p)
    text = re.sub(r"[^\w\s.-]", "", text).strip()
    return re.sub(r"[\s]+", "_", text)[:80] or "Lab_Report"


def _style(doc, name: str):
    try:
        return doc.styles[name]
    except KeyError:
        return doc.styles["Normal"]
