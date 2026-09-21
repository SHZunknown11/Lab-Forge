# LabForge

LabForge generates university Java-programming lab reports from structured source notes. It parses the experiment requirements, produces structured Java content, compiles and executes every level, captures the real terminal output as screenshots, fills the university DOCX template, and validates the result.

## Requirements

- Python 3.11 or newer
- A JDK available on `PATH` (`javac` and `java`)
- LibreOffice on `PATH` (`soffice`) when PDF export is required
- A Gemini API key only for `AI_MODE=cloud`

## Setup

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
python scripts\tokenize_template.py
```

Copy `.env.example` to `.env`. The default `AI_MODE=local` uses deterministic fixture content and requires no API key. For live generation, set `AI_MODE=cloud`, `GEMINI_API_KEY`, and optionally `GEMINI_MODEL` (default: `gemini-3.6-flash`). Transient Gemini responses are retried up to `GEMINI_MAX_ATTEMPTS` times (default: 5), rotating through `GEMINI_FALLBACK_MODELS` when needed.

## Generate a report (CLI)

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:AI_MODE="local"
.venv\Scripts\python.exe main.py generate --source examples\source-notes.md --subject 24CSH-301
```

## Web Interface

LabForge now includes a modern, web-based dashboard for easier report generation.

1. Configure your profile via CLI if you haven't already:
   ```powershell
   python labforge.py setup
   ```
2. Start the web server:
   ```powershell
   uvicorn apps.api.main:app --reload
   ```
3. Open `http://localhost:8000` in your browser.
4. See [USER_GUIDE.md](USER_GUIDE.md) for more detailed instructions on using the Web Interface.

For a fresh cloud generation, remove `artifacts\ai_cache`, set `AI_MODE=cloud`, and rerun the command. Caches are isolated by AI provider and model, so local fixture data is never reused for a cloud report. Generated artifacts are stored in `artifacts\exp_<number>\`:

- `Experiment_<number>_Report.docx`
- `Experiment_<number>_Report.pdf` when LibreOffice is available
- terminal-output screenshots
- `manifest.json` containing generation, execution, and validation evidence

## Portable PDF conversion

Production deployments should run the included Gotenberg service, which packages LibreOffice behind a stable HTTP API. It produces the same result on development machines and servers without requiring LibreOffice to be installed in the LabForge process.

```powershell
docker compose -f docker-compose.pdf.yml up -d
$env:PDF_BACKEND="gotenberg"
$env:GOTENBERG_URL="http://localhost:3000"
```

For a web deployment, keep Gotenberg on the private application network and set `GOTENBERG_URL=http://gotenberg:3000`; do not expose its port publicly. Add licensed, university-approved fonts to `fonts/` before visual QA, then pin `GOTENBERG_IMAGE` to the approved image digest. `PDF_BACKEND=auto` keeps the previous local LibreOffice fallback for development when no service URL is configured.

Every successful PDF is reopened and rendered to `artifacts/exp_<number>/pdf_preview/page_*.png` at 144 DPI. These previews are recorded in the manifest and should be visually reviewed whenever the template, fonts, or conversion image changes.

## Test

```powershell
.venv\Scripts\python.exe -m pytest tests\ -v --basetemp artifacts\pytest-temp -p no:cacheprovider
```

The project-local temporary directory avoids systems where the default user Temp folder is inaccessible.

## Safety

Generated Java code is compiled and run locally with a wall-clock timeout. Treat cloud-generated code as untrusted; this MVP does not provide container-level CPU, memory, or network isolation.
