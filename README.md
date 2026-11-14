# LabForge

**A free AI lab report generator, created by [Mohammad Taha](https://github.com/SHZunknown11), a student at Chandigarh University.**

Upload an experiment sheet, fill in your name, UID and subject, and download a
finished lab report as Word or PDF: aim, objectives, working code, real output
screenshots and learning outcomes, laid out the way your college wants it.

- **Any practical subject.** Java, Python (NumPy, OpenCV, Matplotlib,
  scikit-image), Node.js with Express and Mongoose, React, HTML/CSS/JS. Other
  languages get the code and a slot for your screenshot.
- **Real output, never invented.** Every program is compiled and run. Typed
  input is echoed like a terminal (`Enter PIN: 1234`), Matplotlib figures and
  web pages are captured as images, and a failing program gets one automatic
  fix from the model before you see it.
- **Takes whatever the LMS gives you.** PDF, Word, PowerPoint, text, pasted
  text, or a `.zip` of your project folder.
- **Your format.** The Chandigarh University CSE layout (department header,
  two-column details, 1. Aim … 5. Learning Outcome) or a plain one. Several
  Easy/Medium/Hard problems get a section each.
- **Cheap to run.** One model call per new sheet, cached by content, so a whole
  class uploading the same sheet costs one call. Changing your name, date or
  subject never calls the model. Free-tier providers fail over automatically.
- **Sign in with a college email.** A 6-digit code is emailed (no passwords),
  only `@cuchd.in` addresses by default. Each account gets a few free reports
  a day; a report that fails costs nothing.
- **Reports stay on the student's device.** Name and UID are saved in the
  browser and sent only when the Word or PDF file is made. Finished files are
  kept in the browser, encrypted with a key only that account gets; the server
  deletes its copy after a few hours. Ad-supported (AdSense slots built in).
- **Problems come to you.** A session whose program failed or couldn't be run
  is saved (sheet, code, input, output, errors) and shown under "Failed
  sessions" in `/admin`, so you can see what to add next.
- **Understand it, don't just submit it.** "Explain this code" walks through
  each program and offers likely viva questions with answers.

## Run it locally

Requirements: Python 3.11+, Node 20+, a JDK, Google Chrome (for page and React
screenshots) and LibreOffice (for PDFs; optional).

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[server,dev]"
python scripts\setup_runtime.py           # libraries for student programs (add --mongo for MongoDB)
copy .env.example .env                    # add a free key, e.g. GEMINI_API_KEY
cd apps\frontend; npm install; npm run build; cd ..\..
.venv\Scripts\python -m uvicorn apps.api.main:app --port 8000
```

Open http://localhost:8000. For frontend work, run `npm run dev` in
`apps/frontend` as well (it proxies `/api` to port 8000).

## Command line

```powershell
labforge profile set --name "Your Name" --uid 24BCS00000 --branch BE-CSE --section 719-A --semester 5th --university "Chandigarh University"
labforge generate --source "EXP-2.1.pdf" --subject "Competitive Coding - II" --code 24CSP-305
labforge batch --dir "C:\Users\me\Desktop\cc sem5" --subject "Competitive Coding - II" --skip-existing
labforge doctor     # which languages run here, which AI providers are set, PDF support
```

## How it works

```
sheet ─► extract text ─► condense (drop tutorial text, links, boilerplate)
      ─► cache hit? ──yes──────────────────────────────┐
             │ no                                      │
             ▼                                         ▼
        one model call (structured JSON) ─► run every program in parallel
                                               │ failures: one batched fix call
                                               ▼
                      draft you can edit (code, input, screenshots) ─► DOCX ─► PDF
```

| Path | What it does |
| --- | --- |
| `core/ingestion/extract.py` | PDF, DOCX, PPTX, ZIP, text to compact prompt text |
| `core/ai/provider.py` | Gemini plus OpenAI-compatible free tiers, failover chain, cache, usage log |
| `core/execution/runner.py` | Runs Java, Python, Node, React, HTML, C/C++ with scrubbed env and timeouts |
| `core/documents/` | Template-driven DOCX writer, PDF via LibreOffice or Gotenberg |
| `core/pipeline/orchestrator.py` | Draft, re-run and render steps |
| `apps/api/main.py` | HTTP API (progress as NDJSON, resumable), limits, security headers, serves the app |
| `apps/worker/main.py` | Execution worker: runs programs on a separate machine (`EXEC_BACKEND=remote`) |
| `core/pipeline/jobs.py` | Reports are written in the background; a dropped connection picks up where it was |
| `core/limits.py`, `core/db.py` | Limits per browser and per IP; Postgres for cache, limits and logs |
| `core/accounts.py`, `core/mailer.py` | Sign-in by emailed code, sessions, report credits, saved failed sessions |
| `apps/frontend/` | React app: the live page preview is the editor |

## Configuration

Everything is in [`.env.example`](.env.example). Free keys:
[Gemini](https://aistudio.google.com/apikey), [Groq](https://console.groq.com/keys),
[Cerebras](https://cloud.cerebras.ai), [OpenRouter](https://openrouter.ai/keys),
[Mistral](https://console.mistral.ai), GitHub Models, and Cloudflare Workers AI
through a small proxy Worker on your own account
([deploy/cloudflare-ai](deploy/cloudflare-ai/README.md), no extra signup if you
use Cloudflare). Set any of them; the order in `AI_PROVIDERS` is the failover order.

## Deploy and monetise

Live on Render's free plan (no card): https://labforge-e9yk.onrender.com

```powershell
# RENDER_API_KEY=<key> in .env, push to GitHub, then:
.venv\Scripts\python scripts\deploy_render.py
```

It creates or updates the service, copies your AI keys into its environment,
waits for the build and runs `scripts/smoke_test.py` against the live site. A
scheduled Cloudflare Worker ([deploy/keepalive](deploy/keepalive/worker.js))
keeps it awake during the day. The same `Dockerfile` runs on Hugging Face
Spaces (`scripts/deploy_hf.py`, needs PRO), Koyeb, Fly or any VPS. See
[docs/deployment.md](docs/deployment.md) for sandboxing, token spend and AdSense.

## Tests

```powershell
.venv\Scripts\python -m pytest tests -q
```

The suite runs offline (`AI_MODE=local`) and needs a JDK for the Java and API tests.
`python scripts/smoke_test.py <url>` checks a running server end to end: every
runtime, Word and PDF. CI runs both, builds the production image and smoke-tests
it on every push.

## Author

LabForge is designed and built by **Mohammad Taha** (Chandigarh University). It is an
independent project and isn't affiliated with or endorsed by any university.

## Before going public

See [docs/security.md](docs/security.md) and [docs/deployment.md](docs/deployment.md):
run programs on a separate worker (`EXEC_BACKEND=remote`), set `LABFORGE_DATABASE_URL`,
use your own domain with `LABFORGE_PUBLIC_URL`, and build with `VITE_CONTACT_EMAIL`.
For search engines and AI assistants, see [docs/seo.md](docs/seo.md).

## Use it honestly

LabForge does the formatting and the screenshots. Read and run the code
yourself, and be ready to explain it in your viva.
