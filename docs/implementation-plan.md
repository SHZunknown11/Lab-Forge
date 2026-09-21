# Implementation Plan

## Phase 0: Audit

### What Already Exists
- Directory structure (`core/`, `apps/`, `docs/`, `examples/`, `templates/`, `tests/`).
- `pyproject.toml` with dependencies (`fastapi`, `pydantic`, `python-docx`, `PyMuPDF`, `Pillow`, `Pygments`).
- Reference assets and templates (`examples/source-notes.md`, `examples/sample-report.docx`, `examples/sample-report.pdf`, `templates/chandigarh-university/pblj/template.docx`).
- Architecture, workflow, template analysis, and security documentation.
- Basic repository contract tests (`tests/unit/test_repository_contract.py`).

### What Is Missing
- **Phase 1 Data Schemas**: Pydantic models representing the internal data state.
- **Phase 2 Ingestion**: Parsers to extract and normalize data from `source-notes.md`.
- **Phase 3 Profiles**: Local persistence for student and subject information.
- **Phase 4 AI Abstraction**: Provider-agnostic interface to generate structured experiment content.
- **Phase 5 Java Runner**: Secure local compilation and execution.
- **Phase 6 Self-Repair**: Loop to fix failing code up to 3 times.
- **Phase 7 Execution Evidence**: Structured capture of stdout/stderr and exit codes.
- **Phase 8 Screenshot Renderer**: Terminal output to PNG generator.
- **Phase 9 DOCX Engine**: `python-docx` based population of the template.
- **Phase 10 Validation**: Programmatic structural and execution validation.
- **Phase 11 Orchestrator**: The end-to-end pipeline script.
- **Phase 12 CLI**: The `labforge` command-line interface.
- **Phase 13 End-to-End Tests**: Full system verification using the reference experiment.

### Unsafe Assumptions
- **Empty Source**: `examples/experiment-source.txt` is empty. Use `examples/source-notes.md` as the authoritative source. Do not assume the root txt file has content.
- **Template Layout**: The DOCX is a flowing paragraph document, not a rigid form with content controls. Pagination will drift. Do not assume fixed page counts.
- **AI Competence**: Do not assume AI-generated code will work on the first try. It must be compiled and executed locally.
- **Missing Data**: Do not silently invent missing requirements, problem statements, or learning outcomes if the source lacks them.

### AI Responsibilities
- Produce structured data representations (JSON) for Easy/Medium/Hard levels (problem statement, objectives, code, test input, expected behavior).
- Generate learning outcomes based on the experiment context.
- Attempt to fix code if the deterministic execution engine reports compilation or runtime errors.
- **Must NOT**: Format DOCX, render screenshots, fabricate execution results, or directly access the file system.

### Deterministic Responsibilities
- Read and normalize the source document.
- Cache normalized data and AI responses to minimize cost.
- Isolate, compile, and execute the Java code.
- Capture real stdout, stderr, and execution duration.
- Render captured output into PNG screenshots.
- Open, populate, and save the DOCX template.
- Perform strict validation of structure and execution success.
- Export final reports and metadata manifests.

### External Dependencies
- **System**: Local JDK (`javac`, `java`) for code execution.
- **Python**: Libraries defined in `pyproject.toml`.
- **AI**: An external AI API (e.g., Gemini) when running in `AI_MODE=cloud`.

### Visual-Validation Requirements
- Check for text clipping, page overflow, and screenshot overlap.
- Ensure the header, logo, and university branding are not broken.
- Maintain correct image proportions.
- Prevent orphaned headings and malformed spacing.
- Code formatting must be preserved.

### Execution-Security Requirements
- Run code in temporary, isolated directories.
- Enforce strict wall-clock timeouts for compilation and execution.
- Generated code must not access or overwrite reference files, templates, or profile data.
- Network access for generated code should be denied conceptually (though local MVP relies on standard subprocesses, do not run untrusted code outside the temp dir).
