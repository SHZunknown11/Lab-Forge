"""Report formats. Each template is a DOCX whose first six paragraphs are:
title, spacer, then four metadata lines (two fields per line, tab separated).
Everything after them is replaced with the generated report body.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_FIELDS = [
    "Student Name", "UID", "Branch", "Section/Group", "Semester", "Date", "Subject Name", "Subject Code",
]


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    description: str
    path: Path
    meta_size: int
    upper_headings: bool
    header_image: str | None  # served by the frontend for the live preview
    # The same header as a picture, placed on the page in the DOCX/PDF. The template's own header is
    # text in Impact inside text boxes, which LibreOffice draws in another font and clips.
    header_png: Path | None = None
    header_at_in: tuple[float, float] = (0.0, 0.0)  # where its top-left corner sits on the page


TEMPLATES: dict[str, Template] = {
    "cu-cse": Template(
        id="cu-cse",
        name="Chandigarh University, CSE",
        description="Department header and layout from the official sample report.",
        path=ROOT / "templates/chandigarh-university/pblj/template.docx",
        meta_size=14,
        upper_headings=True,
        header_image="/template-cu-header.png",
        header_png=ROOT / "templates/chandigarh-university/pblj/header.png",
        header_at_in=(0.27, 0.27),
    ),
    "plain": Template(
        id="plain",
        name="Plain",
        description="No college branding. Times New Roman, A4.",
        path=ROOT / "templates/plain/template.docx",
        meta_size=12,
        upper_headings=False,
        header_image=None,
    ),
}


def get_template(template_id: str) -> Template:
    tpl = TEMPLATES.get(template_id) or TEMPLATES["cu-cse"]
    if not tpl.path.exists() and tpl.id == "plain":
        build_plain_template(tpl.path)
    return tpl


def build_plain_template(path: Path) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.27), Inches(11.69)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(1))

    for name in ("Normal", "Body Text", "List Paragraph"):
        style = doc.styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(12)
        style.element.rPr.rFonts.set(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "Times New Roman")
    h1 = doc.styles["Heading 1"]
    h1.font.name = "Times New Roman"
    fonts = h1.element.rPr.rFonts
    for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        fonts.attrib.pop(f"{{http://schemas.openxmlformats.org/wordprocessingml/2006/main}}{attr}", None)
    h1.font.size = Pt(14)
    h1.font.bold = True
    h1.font.color.rgb = RGBColor(0, 0, 0)
    h1.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h1.paragraph_format.space_before = Pt(18)
    h1.paragraph_format.space_after = Pt(6)

    title = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("Experiment")
    run.bold, run.underline, run.font.size = True, True, Pt(16)
    doc.add_paragraph(style="Body Text")
    for _ in range(4):
        p = doc.add_paragraph()
        p.paragraph_format.tab_stops.add_tab_stop(Inches(3.6))
        p.paragraph_format.space_after = Pt(4)
        r = p.add_run("Label: value")
        r.bold, r.font.size = True, Pt(12)

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
