# Architecture

LabForge is not implemented yet. This document defines the intended module boundaries for the future implementation.

## Components

`apps/api`

Future FastAPI application boundary. It should expose endpoints only after the core pipeline is usable and tested.

`apps/web`

Reserved for a future React frontend. It should remain empty until the core pipeline is working.

`core/ingestion`

Reads source files such as LMS Markdown exports or future text inputs. It should parse experiment metadata, level sections, problem statements, objectives, code references, and output references into structured data.

`core/ai`

Owns AI prompts and structured response schemas. AI should return structured data only. It should not directly edit DOCX files or control final layout.

`core/execution`

Compiles and executes generated Java code in temporary working directories with isolation, timeout, and resource limits. It is responsible for proving that generated code works before any successful solution claim.

`core/screenshots`

Turns verified program output into screenshots suitable for report insertion. It must not fabricate screenshots.

`core/documents`

Populates DOCX templates using deterministic code. It owns template selection, field replacement, screenshot placement, style preservation, and export coordination.

`core/profiles`

Stores and reads student metadata such as name, UID, branch, section, semester, and related profile fields. Student metadata must come from a stored profile.

`core/validation`

Checks parsed source data, generated structured content, compilation results, execution output, screenshots, DOCX integrity, and final report completeness.

`core/pipeline`

Coordinates the end-to-end workflow without owning the internals of ingestion, AI, execution, screenshots, document generation, or validation.

`templates`

Stores university template candidates. The current Chandigarh University PBLJ template copy is at `templates/chandigarh-university/pblj/template.docx`.

`examples`

Stores untouched reference copies used for analysis and tests.

`artifacts`

Future generated outputs. This directory should contain generated reports and transient user-visible artifacts, not source references.

`config`

Future non-secret configuration and local profile examples.

## Boundaries

- Ingestion produces normalized experiment data.
- AI consumes normalized data and produces structured content.
- Execution compiles and runs generated code before success is claimed.
- Screenshots are derived from actual captured output.
- Document generation is deterministic and template-aware.
- Validation verifies each stage before the pipeline advances.
- Storage separates references, templates, temporary execution files, and generated artifacts.

## Extension Points

- Additional programming languages can be added under execution-specific strategies after Java is stable.
- Additional universities or subject templates can be added under `templates/<university>/<subject>/`.
- Frontend and Telegram delivery can be added only after the core pipeline works.
- Alternate AI providers can be introduced behind structured interfaces without changing document generation.
- More robust sandbox providers can replace local MVP execution without changing ingestion or document generation.
