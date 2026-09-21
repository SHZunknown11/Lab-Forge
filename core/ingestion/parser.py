"""Parse experiment source files (.txt and .md) into structured ExperimentDocument."""
from __future__ import annotations

import re
from pathlib import Path
from core.schemas import ExperimentDocument, ExperimentMetadata, ExperimentLevel


def parse_source_file(source_path: str) -> ExperimentDocument:
    """Parse a .txt or .md experiment source file into an ExperimentDocument."""
    text = Path(source_path).read_text(encoding="utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    metadata = _extract_metadata(text)
    objectives = _extract_objectives(text)
    apparatus = _extract_apparatus(text)
    reading_material = _extract_reading_material(text)

    # Parse levels from the problem-statement area (before Sample Code)
    easy_ps = _extract_problem_statement(text, "easy")
    medium_ps = _extract_problem_statement(text, "medium")
    hard_ps = _extract_problem_statement(text, "hard")

    # Parse code from the Sample Code area (or inline code)
    easy_code, medium_code, hard_code = _extract_all_level_codes(text)

    easy = ExperimentLevel(problem_statement=easy_ps, code=easy_code) if easy_ps or easy_code else None
    medium = ExperimentLevel(problem_statement=medium_ps, code=medium_code) if medium_ps or medium_code else None
    hard = ExperimentLevel(problem_statement=hard_ps, code=hard_code) if hard_ps or hard_code else None

    return ExperimentDocument(
        metadata=metadata,
        easy=easy,
        medium=medium,
        hard=hard,
        objectives=objectives,
        apparatus=apparatus,
        reading_material=reading_material,
    )


# ── Metadata ───────────────────────────────────────────────────────

def _extract_metadata(text: str) -> ExperimentMetadata:
    """Extract experiment number, title, CO mapping, and aim."""
    # Experiment number: "Experiment 6:" or "Experiment-1.3" or "**Experiment 3:**"
    standalone = re.search(
        r"\*{0,2}Experiment\s+(\d+)\s*:\s*\*{0,2}",
        text, re.IGNORECASE,
    )
    dotted = re.search(r"Experiment[\s\-]+\d+\.(\d+)", text, re.IGNORECASE)

    if standalone:
        exp_number = standalone.group(1)
    elif dotted:
        exp_number = dotted.group(1)
    else:
        m = re.search(r"Experiment[\s\-]*(\d+)", text, re.IGNORECASE)
        exp_number = m.group(1) if m else "0"

    title = f"Experiment {exp_number}"

    # CO mapping
    co_match = re.search(
        r"\*{0,2}\s*CO\s+mapped[\s\-:]*(.+?)\s*\*{0,2}\s*$",
        text, re.MULTILINE | re.IGNORECASE,
    )
    co_mapping = co_match.group(1).strip().rstrip("*").strip() if co_match else ""

    # Aim
    aim_match = re.search(
        r"\*{0,2}Aim\s*:?\s*\*{0,2}\s*(.+?)(?:\n\s*\n|\n\s*\*{0,2}(?:Easy|Medium|Hard|Objective|Input))",
        text, re.DOTALL | re.IGNORECASE,
    )
    aim = ""
    if aim_match:
        aim = aim_match.group(1).strip()
        aim = re.sub(r"\*{1,2}", "", aim).strip()
        aim = re.sub(r"\s+", " ", aim)
    else:
        aim_line = re.search(r"Aim\s*:?\s*\*{0,2}\s*(.+)", text, re.IGNORECASE)
        if aim_line:
            aim = re.sub(r"\*{1,2}", "", aim_line.group(1)).strip()
            aim = re.sub(r"\s+", " ", aim)

    return ExperimentMetadata(
        experiment_number=exp_number, title=title, aim=aim, co_mapping=co_mapping,
    )


# ── Problem Statements ────────────────────────────────────────────

def _extract_problem_statement(text: str, level: str) -> str:
    """Extract the problem statement for a given level from the header area."""
    # Only look BEFORE the "Sample Code:" section
    sample_pos = _ci_find(text, "Sample Code")
    search_text = text[:sample_pos] if sample_pos >= 0 else text

    if level == "easy":
        header_re = r"(?:\*{0,2}Easy\s+Level\s*:?\s*\*{0,2})"
        stop_re = r"(?:\*{0,2}(?:Medium|Hard)\s+Level)"
    elif level == "medium":
        header_re = r"(?:\*{0,2}Medium\s+Level\s*:?\s*\*{0,2})"
        stop_re = r"(?:\*{0,2}Hard\s+Level)"
    else:
        header_re = r"(?:\*{0,2}Hard\s+Level\s*:?\s*\*{0,2})"
        stop_re = r"(?:\*{0,2}(?:Objective|Input/Apparatus|Reading Material))"

    m = re.search(header_re, search_text, re.IGNORECASE)
    if not m:
        return ""

    start = m.end()
    end_m = re.search(stop_re, search_text[start:], re.IGNORECASE)
    end = start + end_m.start() if end_m else len(search_text)
    block = search_text[start:end].strip()

    # Extract from "Problem Statement:" if present
    ps_m = re.search(r"\*{0,2}Problem\s+Statement\s*:?\s*\*{0,2}\s*(.*)", block, re.DOTALL | re.IGNORECASE)
    result = ps_m.group(1).strip() if ps_m else block

    result = re.sub(r"\*{1,2}", "", result).strip()
    result = re.sub(r"\s+", " ", result).strip()
    return result


# ── Code Extraction ───────────────────────────────────────────────

def _extract_all_level_codes(text: str) -> tuple[str, str, str]:
    """
    Extract Java code for easy, medium, and hard levels.

    Handles two formats:
    1. Code under "Sample Code:" with level headers (Easy Level, Medium Level, Hard Level)
    2. Code inlined after problem statements / output markers
    """
    # Find the "Sample Code:" section
    sample_pos = _ci_find(text, "Sample Code")
    if sample_pos >= 0:
        code_area = text[sample_pos:]
    else:
        # Fallback: everything from the first Java-looking line
        code_area = text

    # Split the code area into level blocks using level headers
    level_blocks = _split_code_by_levels(code_area)

    easy_code = _collect_all_java_classes(level_blocks.get("easy", ""))
    medium_code = _collect_all_java_classes(level_blocks.get("medium", ""))
    hard_code = _collect_all_java_classes(level_blocks.get("hard", ""))

    return easy_code, medium_code, hard_code


def _split_code_by_levels(code_area: str) -> dict[str, str]:
    """Split a code area into easy/medium/hard blocks by level headers."""
    # Find positions of level headers
    easy_positions = list(re.finditer(r"(?:^|\n)\s*\*{0,2}Easy\s+Level\s*:?\s*\*{0,2}", code_area, re.IGNORECASE))
    medium_positions = list(re.finditer(r"(?:^|\n)\s*\*{0,2}Medium\s+Level\s*:?\s*\*{0,2}", code_area, re.IGNORECASE))
    hard_positions = list(re.finditer(r"(?:^|\n)\s*\*{0,2}Hard\s+Level\s*:?\s*\*{0,2}", code_area, re.IGNORECASE))

    # Build ordered list of (position, level)
    markers: list[tuple[int, str]] = []
    for m in easy_positions:
        markers.append((m.end(), "easy"))
    for m in medium_positions:
        markers.append((m.end(), "medium"))
    for m in hard_positions:
        markers.append((m.end(), "hard"))

    markers.sort(key=lambda x: x[0])

    result: dict[str, str] = {}

    if not markers:
        # No level headers found — treat entire code area as easy
        result["easy"] = code_area
        return result

    # If there's no "Easy Level" header but there IS medium/hard, then the code
    # before the first marker is the Easy code.
    first_marker_pos = markers[0][0]
    has_easy_header = any(level == "easy" for _, level in markers)

    if not has_easy_header:
        # Find the start of the first marker's header text (not end)
        first_header_start = first_marker_pos
        all_positions = easy_positions + medium_positions + hard_positions
        for m2 in all_positions:
            if m2.end() == first_marker_pos:
                first_header_start = m2.start()
                break
        # Also check for "Output:" before the first level header —
        # the easy code is between start and first Output: or first level header
        output_before = re.search(
            r"(?:^|\n)\s*\*{0,2}Output\s*:\s*\*{0,2}",
            code_area[:first_header_start],
            re.IGNORECASE,
        )
        if output_before:
            result["easy"] = code_area[:output_before.start()]
        else:
            result["easy"] = code_area[:first_header_start]

    for i, (start_pos, level) in enumerate(markers):
        if i + 1 < len(markers):
            end_pos = markers[i + 1][0]
            # Find the header match to get its start position for cleaner cut
            all_positions = easy_positions + medium_positions + hard_positions
            for m2 in all_positions:
                if m2.end() == markers[i + 1][0]:
                    end_pos = m2.start()
                    break
        else:
            end_pos = len(code_area)

        block = code_area[start_pos:end_pos]
        result[level] = block

    return result


def _collect_all_java_classes(block: str) -> str:
    """
    Collect ALL Java source code from a block, including multiple classes.
    Handles the format where classes appear as plain text paragraphs.
    """
    if not block.strip():
        return ""

    lines = block.split("\n")
    code_lines: list[str] = []
    in_code = False
    brace_depth = 0

    for line in lines:
        stripped = line.strip()

        # Skip markdown fencing
        if stripped.startswith("```"):
            in_code = not in_code
            continue

        # Stop at Output: section
        if re.match(r"^\*{0,2}Output\s*:", stripped, re.IGNORECASE):
            break
        # Stop at image references
        if re.match(r"^\[?\*{0,2}image", stripped, re.IGNORECASE):
            break

        # Detect Java code start markers
        is_java_start = bool(re.match(
            r"^(package |import |public |abstract |class |@|//|/\*|private |protected )",
            stripped,
        ))

        if not code_lines and not in_code and not is_java_start:
            continue  # Skip non-code lines before code starts

        if is_java_start or in_code or code_lines:
            in_code = True
            code_lines.append(line.rstrip())
            brace_depth += stripped.count("{") - stripped.count("}")

    code = "\n".join(code_lines).strip()

    # Clean up markdown escapes
    code = code.replace("\\_", "_")
    code = code.replace("\\<", "<").replace("\\>", ">")

    # Remove trailing empty lines
    while code.endswith("\n\n"):
        code = code[:-1]

    return code


# ── Section Extraction ────────────────────────────────────────────

def _extract_objectives(text: str) -> str:
    """Extract objectives section."""
    return _extract_delimited_section(
        text,
        r"\*{0,2}Objective\s*:?\s*-?\s*\*{0,2}",
        [r"\*{0,2}Input/Apparatus", r"\*{0,2}Reading Material", r"\*{0,2}Sample Code"],
    )


def _extract_apparatus(text: str) -> str:
    """Extract apparatus section."""
    return _extract_delimited_section(
        text,
        r"\*{0,2}Input/Apparatus Used\s*:?\s*\*{0,2}",
        [r"\*{0,2}Reading Material", r"\*{0,2}Sample Code"],
    )


def _extract_reading_material(text: str) -> str:
    """Extract reading material section."""
    return _extract_delimited_section(
        text,
        r"\*{0,2}Reading Material\s*:?\s*\*{0,2}",
        [r"\*{0,2}Sample Code"],
    )


def _extract_delimited_section(text: str, header_re: str, stop_patterns: list[str]) -> str:
    """Extract section text between a header and the first matching stop pattern."""
    m = re.search(header_re, text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return ""

    start = m.end()
    end = len(text)
    for sp in stop_patterns:
        sm = re.search(sp, text[start:], re.IGNORECASE)
        if sm and start + sm.start() < end:
            end = start + sm.start()

    result = text[start:end].strip()
    result = re.sub(r"\*{1,2}", "", result)
    return result.strip()


def _ci_find(text: str, substr: str) -> int:
    """Case-insensitive find."""
    idx = text.lower().find(substr.lower())
    return idx
