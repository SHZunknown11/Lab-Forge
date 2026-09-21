"""
One-time script: Replace hardcoded sample-report values in the working template
with {{TOKEN}} placeholders so the DOCX generator can do reliable replacements.

Run once from the repo root:
    python scripts/tokenize_template.py

The template file is modified in-place. Run only once — running twice will
double-replace tokens ({{{{TOKEN}}}}) which is harmless to detect but messy.
"""

from docx import Document
from pathlib import Path
import sys

TEMPLATE = Path("templates/chandigarh-university/pblj/template.docx")

# Map literal values → token strings.
# Order matters: longer / more specific strings first to avoid partial matches.
TOKENS = [
    ("Mohammad Taha",  "{{STUDENT_NAME}}"),
    ("24BCS12733",     "{{UID}}"),
    ("BE-CSE",         "{{BRANCH}}"),
    # Unicode left/right double-quote variants of the section "A"
    ("719\u2013\u201cA\u201d", "{{SECTION}}"),
    ("719-\u201cA\u201d",      "{{SECTION}}"),
    ("\u201cA\u201d",          "{{SECTION}}"),
    ("719-A",          "{{SECTION}}"),
    ("5th",            "{{SEMESTER}}"),
    ("01/09/2026",     "{{DATE}}"),
    # Subject code before subject name so "PBLJ" alone doesn't partial-match "24CSH-301"
    ("24CSH-301",      "{{SUBJECT_CODE}}"),
    ("PBLJ",           "{{SUBJECT_NAME}}"),
    ("Experiment 3",   "{{EXPERIMENT_TITLE}}"),
]


def replace_in_run(run, replacements):
    for old, new in replacements:
        if old in run.text:
            run.text = run.text.replace(old, new)


def process_paragraphs(paragraphs, replacements):
    count = 0
    for para in paragraphs:
        original = para.text
        for run in para.runs:
            replace_in_run(run, replacements)
        if para.text != original:
            count += 1
    return count


def main():
    if not TEMPLATE.exists():
        print(f"ERROR: Template not found at {TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    # Safety check: if already tokenized, warn and exit
    doc = Document(str(TEMPLATE))
    full_text = " ".join(p.text for p in doc.paragraphs)
    if "{{STUDENT_NAME}}" in full_text:
        print("Template appears already tokenized ({{STUDENT_NAME}} found). Skipping.")
        sys.exit(0)

    changed = process_paragraphs(doc.paragraphs, TOKENS)

    # Also process paragraphs inside tables (if any appear in header/footer)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                changed += process_paragraphs(cell.paragraphs, TOKENS)

    # Process header paragraphs in each section
    for section in doc.sections:
        if section.header:
            changed += process_paragraphs(section.header.paragraphs, TOKENS)
        if section.footer:
            changed += process_paragraphs(section.footer.paragraphs, TOKENS)

    doc.save(str(TEMPLATE))
    print(f"Tokenization complete. {changed} paragraph(s) modified. Template saved: {TEMPLATE}")


if __name__ == "__main__":
    main()
