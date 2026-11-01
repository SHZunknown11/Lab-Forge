# Architecture

## Request flow

1. `POST /api/drafts` (multipart: file or text, language, subject, `fresh`).
   The API extracts and condenses the sheet, checks the per-IP limit (cache
   hits are free), creates a job folder and streams NDJSON events:
   `job`, `stage`, `draft` (as soon as the model answers), `task` (one per
   program as it finishes), `done`, or `error`.
2. The browser keeps the draft. Edits never touch the server until the
   student re-runs a program (`POST /api/jobs/{id}/run`) or uploads a
   screenshot (`POST /api/jobs/{id}/images`).
3. `POST /api/jobs/{id}/render` takes the draft, the student's fields, the
   template and options, and writes a fresh render folder with the DOCX, the
   PDF and page thumbnails. No model call.

## Boundaries

- The model returns structured data only (`core.schemas.AIReport`). Layout is
  decided by `core/documents/generator.py`.
- Output text and images come only from the executor or from the student's
  uploads. The model never writes output.
- Each template is a DOCX whose first six paragraphs are the title, a spacer
  and four metadata lines; everything after them is generated. Add a college
  by adding a template to `core/documents/templates.py`.
- Student details never leave the browser except inside a render request,
  and render folders expire with the job.

## Token budget

See the module docstring in `core/ai/provider.py`: content-addressed cache,
condensed input, static system prompt first (prefix caching), structured
output, low thinking, capped output, and a single batched fix call that
carries only failing code.
