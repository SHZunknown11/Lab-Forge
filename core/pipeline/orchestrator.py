"""End-to-end pipeline orchestrator coordinating all stages."""
from __future__ import annotations

import re
from pathlib import Path

from core.ingestion.parser import parse_source_file
from core.profiles.manager import ProfileManager
from core.ai.provider import AIOrchestrator
from core.execution.runner import JavaRunner
from core.screenshots.terminal_renderer import TerminalRenderer
from core.documents.generator import DocxGenerator
from core.validation.validator import DocumentValidator
from core.schemas import (
    ExecutionEvidence,
    ExecutionResult,
    GeneratedContent,
    ReportManifest,
    ScreenshotArtifact,
)


def generate_report(
    source_path: str,
    subject_code: str,
    force_refresh: bool = False,
) -> ReportManifest:
    """
    Full pipeline: parse → AI generate → execute → screenshot → DOCX → validate.

    Returns a ReportManifest with paths to generated files and execution evidence.
    """
    # 1. Parse source
    print(f"[1/7] Parsing source: {source_path}")
    document = parse_source_file(source_path)
    exp_num = document.metadata.experiment_number
    exp_title = document.metadata.title or f"Experiment {exp_num}"

    # 2. Load profiles
    print("[2/7] Loading profiles...")
    profile_mgr = ProfileManager()
    student = profile_mgr.get_student_profile()
    if not student:
        raise RuntimeError("No student profile configured. Run: labforge profile set ...")
    subject = profile_mgr.get_subject(subject_code)
    if not subject:
        raise RuntimeError(f"Subject '{subject_code}' not found. Run: labforge subject add ...")

    # 3. AI generation
    print("[3/7] Generating structured content...")
    ai = AIOrchestrator()
    generated = ai.generate(document, force_refresh=force_refresh)

    # Merge source code into generated if AI didn't provide it
    _merge_source_code(document, generated)

    # 4. Execute Java code
    print("[4/7] Compiling and executing Java code...")
    execution_evidences: dict[str, ExecutionEvidence] = {}
    runner = JavaRunner(timeout_seconds=15)

    for level_name in ("easy", "medium", "hard"):
        gen_level = getattr(generated, level_name, None)
        src_level = getattr(document, level_name, None)
        code = ""
        filename = ""

        if gen_level and gen_level.code:
            code = gen_level.code
            filename = gen_level.filename
        elif src_level and src_level.code:
            code = src_level.code

        if not code:
            continue

        # Clean up the Java code for compilation
        code = _prepare_java_code(code)

        # Determine filename from the public class name
        if not filename:
            filename = _extract_filename(code)

        # Determine test input for interactive programs
        test_input = _determine_test_input(code, level_name, document)

        print(f"  -> Executing {level_name}: {filename}")
        comp_result, exec_result = runner.execute(filename, code, test_input=test_input)

        success = (
            comp_result.exit_code == 0
            and exec_result is not None
            and exec_result.exit_code == 0
        )

        evidence = ExecutionEvidence(
            level=level_name,
            source_code=code,
            compilation_result=comp_result,
            execution_result=exec_result,
            success=success,
        )
        execution_evidences[level_name] = evidence

        if not success:
            stderr = comp_result.stderr if comp_result.exit_code != 0 else (exec_result.stderr if exec_result else "")
            print(f"  ! {level_name} failed: {stderr[:200]}")

    # 5. Render screenshots
    print("[5/7] Rendering output screenshots...")
    artifacts_dir = Path("artifacts") / f"exp_{exp_num}"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = artifacts_dir / "screenshots"

    renderer = TerminalRenderer()
    screenshot_artifacts: dict[str, ScreenshotArtifact] = {}

    for level_name, evidence in execution_evidences.items():
        if evidence.success:
            artifact = renderer.render(evidence, screenshot_dir)
            screenshot_artifacts[level_name] = artifact

    # 6. Generate DOCX
    print("[6/7] Generating DOCX report...")
    template_path = subject.template_reference
    safe_title = re.sub(r"[^\w\s-]", "", exp_title).strip().replace(" ", "_")
    docx_path = str(artifacts_dir / f"{safe_title}_Report.docx")

    generator = DocxGenerator()
    generator.generate(
        template_path=template_path,
        output_path=docx_path,
        student=student,
        subject=subject,
        experiment=document,
        generated=generated,
        screenshots=screenshot_artifacts,
    )

    # 7. Validate
    print("[7/7] Validating report...")
    validator = DocumentValidator()
    validation_result = validator.validate(docx_path)

    if validation_result.is_valid:
        print(f"[OK] Report generated successfully: {docx_path}")
    else:
        print(f"[WARN] Validation failed: {len(validation_result.errors)} errors")
        for error in validation_result.errors:
            print(f"  - {error}")

    manifest = ReportManifest(
        source_identifier=source_path,
        subject_code=subject_code,
        docx_path=docx_path,
        execution_evidences=execution_evidences,
        screenshot_artifacts=screenshot_artifacts,
        validation_status=validation_result,
    )

    # Save manifest
    manifest_path = artifacts_dir / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    return manifest


def _merge_source_code(document, generated: GeneratedContent) -> None:
    """If the source has code but AI didn't generate any, copy from source."""
    for level_name in ("easy", "medium", "hard"):
        gen_level = getattr(generated, level_name, None)
        src_level = getattr(document, level_name, None)
        if src_level and src_level.code and gen_level:
            if not gen_level.code:
                gen_level.code = src_level.code
            if not gen_level.problem_statement and src_level.problem_statement:
                gen_level.problem_statement = src_level.problem_statement


def _extract_filename(code: str) -> str:
    """Extract the public class name from Java code to determine the filename."""
    # Look for: public class Foo, public abstract class Foo
    match = re.search(r"public\s+(?:abstract\s+)?class\s+(\w+)", code)
    if match:
        return f"{match.group(1)}.java"
    # Fallback: any class declaration
    match = re.search(r"class\s+(\w+)", code)
    if match:
        return f"{match.group(1)}.java"
    return "Main.java"


def _determine_test_input(code: str, level_name: str, document) -> str:
    """Determine appropriate test input for interactive Java programs."""
    if "Scanner" not in code:
        return ""

    code_lower = code.lower()

    # Count how many nextInt/nextLine/next calls exist to estimate input needs
    import re
    next_calls = len(re.findall(r'next(?:int|double|line|float|long|short|byte)\s*\(', code_lower))
    next_calls += len(re.findall(r'\.next\(\)', code_lower))

    # Menu-driven programs (CRUD, switch-case menus)
    if any(kw in code_lower for kw in ['switch', 'menu', 'choice', 'crud', 'option']):
        # Provide generous menu input: select options then exit
        return "1\nTest\n100\nDept\n2\n1\n3\n1\n5\n0\n-1\nexit\nno\n"

    # Programs with multiple scanner reads
    if next_calls >= 3:
        return "1\nTest\n100\n2\nDemo\n200\n0\nexit\n"

    # Specific patterns
    if "nextdouble" in code_lower or "square root" in code_lower:
        return "67\n"
    elif "pin" in code_lower and "withdraw" in code_lower:
        return "1234\n500\n"
    elif "yes/no" in code_lower or "y/n" in code_lower:
        return "yes\n"
    elif "scanner.nextline" in code_lower:
        return "test input\n"
    elif "scanner.nextint" in code_lower:
        return "1\n2\n3\n0\n"
    elif "scanner.next()" in code_lower:
        return "test\n"

    return "1\ntest\n0\n"


def _prepare_java_code(code: str) -> str:
    """
    Clean up Java code for compilation:
    - Remove package declarations (we compile in temp dirs)
    - Remove 'abstract' from classes that have main() (can't run abstract classes)
    - Remove excessive blank lines
    - Ensure only one public class exists per file
    - Hoist all import statements to the top
    """
    lines = code.split("\n")
    cleaned: list[str] = []
    
    imports = []
    import_pattern = r"^[ \t]*import\s+[^;]+;"

    for line in lines:
        stripped = line.strip()

        # Remove package declarations
        if re.match(r"^package\s+\w+", stripped):
            continue
            
        if re.match(import_pattern, stripped):
            if stripped not in imports:
                imports.append(stripped)
            continue

        # Skip empty lines if the last line was also empty (collapse double blanks)
        if not stripped and cleaned and not cleaned[-1].strip():
            continue

        cleaned.append(line)

    code = "\n".join(cleaned).strip()
    
    if imports:
        code = "\n".join(imports) + "\n\n" + code

    # Remove 'abstract' from class declarations that contain main()
    if "public static void main" in code:
        code = re.sub(
            r"public\s+abstract\s+class\s+",
            "public class ",
            code,
        )

    # Ensure only one public class — make non-main public classes package-private
    public_classes = re.findall(r"public\s+class\s+(\w+)", code)
    if len(public_classes) > 1:
        # Find which class has main()
        main_class = None
        main_idx = code.find("public static void main")
        if main_idx != -1:
            best_dist = float('inf')
            for match in re.finditer(r"(?:public\s+)?class\s+(\w+)", code):
                cls_idx = match.start()
                if cls_idx < main_idx:
                    dist = main_idx - cls_idx
                    if dist < best_dist:
                        best_dist = dist
                        main_class = match.group(1)
        else:
            # Fallback to the first public class if no main is found
            main_class = public_classes[0]

        if main_class:
            # Make all other public classes package-private
            for cls_name in public_classes:
                if cls_name != main_class:
                    code = code.replace(
                        f"public class {cls_name}",
                        f"class {cls_name}",
                        1,
                    )

    return code

