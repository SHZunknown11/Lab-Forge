"""Document validation — structural and metadata checking."""
from __future__ import annotations

from pathlib import Path
from docx import Document
from core.schemas import ValidationResult


class DocumentValidator:
    """Validate a generated DOCX report for completeness."""

    REQUIRED_METADATA_KEYWORDS = [
        "Student Name",
        "UID",
        "Branch",
        "Section/Group",
        "Semester",
        "Date",
        "Subject Name",
        "Subject Code",
    ]

    REQUIRED_SECTIONS = ["Aim", "Code:", "Output:"]

    def validate(self, docx_path: str) -> ValidationResult:
        """Validate a DOCX file and return the result."""
        errors: list[str] = []
        warnings: list[str] = []

        path = Path(docx_path)
        if not path.exists():
            return ValidationResult(
                is_valid=False,
                errors=[f"File not found: {docx_path}"],
            )

        try:
            doc = Document(str(path))
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Cannot open DOCX: {e}"],
            )

        # Extract all text
        full_text = "\n".join(p.text for p in doc.paragraphs)

        # Check metadata
        for keyword in self.REQUIRED_METADATA_KEYWORDS:
            if keyword not in full_text:
                errors.append(f"Missing metadata field: {keyword}")

        # Check sections
        for section in self.REQUIRED_SECTIONS:
            if section.lower() not in full_text.lower():
                warnings.append(f"Missing section: {section}")

        # Check for images
        image_count = 0
        for rel in doc.part.rels.values():
            if "image" in rel.reltype:
                image_count += 1
        if image_count == 0:
            warnings.append("No images found in the document")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
