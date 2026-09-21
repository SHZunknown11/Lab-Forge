# Workflow

This is the planned LabForge workflow. It has not been implemented yet.

## 1. Input

The user supplies an experiment source. In the inspected references, the populated source is `examples/source-notes.md`; `examples/experiment-source.txt` is empty.

The first MVP should support Java programming experiments with an overall aim and Easy, Medium, and Hard levels.

## 2. Parsing

Ingestion should identify:

- Experiment label and report title
- CO mapping when present
- Aim
- Easy, Medium, and Hard problem statements
- Overall objectives and per-level objectives when present
- Apparatus or environment notes when present
- Reading material when present
- Sample code blocks
- Output image links or output references

Parsing should preserve source wording and report missing sections rather than filling gaps silently.

## 3. Normalization

Parsed data should be converted into a stable internal schema. The schema should keep source fields separate from generated fields so that later stages can compare what was requested against what was produced.

## 4. Structured Generation

AI may generate objectives, code candidates, explanatory content, or learning outcomes, but it must return structured data. It must not directly edit the final DOCX or decide final layout.

## 5. Code Validation

Generated Java code must be written to a temporary directory, compiled, and checked before it is eligible for report insertion. Compilation errors should be captured as validation failures.

## 6. Execution

Compiled Java programs should run with explicit input, timeout, filesystem isolation, and no production network access. Program output must be captured from the real process.

## 7. Output Capture

Captured output should be stored as structured text and linked to the code version that produced it. LabForge must never fabricate output.

## 8. Screenshot Rendering

Screenshots should be generated from captured output using deterministic styling that resembles the target terminal output format. Screenshots must be traceable to captured output.

## 9. DOCX Generation

Document generation should use the copied template at `templates/chandigarh-university/pblj/template.docx` as the initial candidate. Deterministic code should populate metadata, aim, level sections, code, output screenshots, and learning outcomes while preserving university formatting.

## 10. Final Validation

Validation should confirm:

- Required metadata is present.
- Easy, Medium, and Hard requirements are preserved.
- Java code compiled successfully.
- Program output came from execution.
- Screenshots exist and correspond to captured output.
- DOCX contains all required report sections.
- DOCX/PDF rendering passes visual checks for layout, clipping, and overlap.

## 11. Export

The final report should be written under `artifacts/`. Export should keep the original references unchanged and should retain enough metadata to audit the generated report.
