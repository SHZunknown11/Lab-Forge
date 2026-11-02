"""Model access: one call per new sheet, one batched call for fixes, everything cached.

Token budget, in order of impact:
1. Content-addressed cache. The key is a hash of the condensed sheet, so every
   student who uploads the same sheet after the first costs zero tokens, and
   changing name, date or subject never calls the model.
2. Condensed input (see core.ingestion.extract): tutorial text, boilerplate and
   links are removed before the prompt is built.
3. Static system instruction first, so the provider's implicit prefix cache
   can reuse it across requests; structured output, so there are no
   malformed-JSON retries.
4. Low thinking level and capped output tokens.
5. Failed programs are fixed in a single batched call that carries only the
   failing code and its error, never the whole sheet again. The fixed code is
   written back to the cache, so the next student skips the fix as well.

Providers: every provider with a key in the environment joins a failover
chain (AI_PROVIDERS sets the order). When one is rate-limited or down, the
next one answers. All of the defaults have free tiers.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from core.schemas import AIFile, AIFixes, AIReport, AITask

ROOT = Path(__file__).resolve().parents[2]
PROMPT_VERSION = "6"

SYSTEM_PROMPT = """You turn a university lab experiment sheet into the content of a lab report. Reply with JSON only.
- One task per problem, level or part the sheet lists (e.g. Easy, Medium, Hard), in order; a sheet with a single practical question is one task. Keep every requirement; add none.
- title: the sheet's label for the task, e.g. "Easy Level" or "Problem 2"; for a single task, a short name for it.
- problem: the task's problem statement as one clear paragraph.
- objectives: 2-4 short learning objectives for the task.
- If the sheet gives code for a task, reuse it and fix only real errors. Otherwise write complete, correct code a student could explain in a viva: clear names, brief comments, no over-engineering.
- language: one of java, python, c, cpp, javascript (Node.js), react, html, matlab, sql, r, shell, other; use what the sheet asks for.
- files: usually one {name, code}. Use several only when the project needs them (React components, Express routes). Names like SquareRoot.java, main.py, App.jsx, server.js, index.html.
- Programs run unattended: no reading files, no external network, no GUI windows, no command-line arguments. Java: Java 17 (no Java 21+ features such as record patterns or pattern matching in switch); no package line; exactly one public class per file.
- If the task reads user input, read it normally (Scanner, input(), cin) and put realistic demo input in stdin, one value per line, covering the cases the task mentions. Otherwise stdin is "".
- Printed output must show the required behaviour, including handled error cases.
- Spring Boot (when the sheet uses Spring/JPA/Hibernate): language java; Spring Boot 3 with spring-boot-starter-web, data-jpa, validation and an H2 in-memory database are available, nothing else (no Lombok, no application.properties: rely on defaults). One @SpringBootApplication class with main; a file per public class like the sheet, or one file with the other classes non-public. Print every result from a CommandLineRunner. For REST endpoints, call them from the runner with RestTemplate on "http://localhost:" + env.getProperty("local.server.port") (Environment env, read inside run), print status and body, and catch HttpStatusCodeException to print error responses.
- Node.js: CommonJS require; only express, mongoose, bcryptjs, jsonwebtoken, cors, uuid, axios, dotenv, body-parser, morgan, express-validator. A server must start, call its own routes with fetch, print each response, then close and exit. MongoDB: mongoose.connect(process.env.MONGO_URI || "mongodb://127.0.0.1:27017/<db>") and disconnect at the end.
- React: function components, App.jsx with a default export; only react, react-dom, react-router-dom and imported .css files; no network calls on load.
- HTML: self-contained pages, CSS and JS inline or in sibling files, no external links.
- Python image processing: use skimage.data sample images (e.g. camera(), astronaut()) or numpy arrays, never files from disk; show results with matplotlib (plt.show(), no matplotlib.use()), several images per figure with subplots.
- K&R braces; compact code.
- experiment_no: the number as the sheet writes it (e.g. "3" or "1.3"). title: "Experiment <no>". aim: copy the sheet's "Aim" text word for word; write one sentence only if the sheet has no aim.
- learning_outcomes: 3-5 one-sentence outcomes."""

FIX_PROMPT = """You fix student programs that failed to compile, run or build. For each item return its index, the full corrected files and the stdin to feed it (one value per line, "" if none). Keep the same program, structure and behaviour; change only what the error requires. Programs run unattended with no files, external network or GUI. Node servers must call their own routes, print the responses and exit; MongoDB code must use process.env.MONGO_URI. Reply with JSON only."""

# Compact schema text for providers without native structured output.
SCHEMA_HINT = {
    "draft": '{"experiment_no":str,"title":str,"aim":str,"tasks":[{"title":str,"problem":str,"objectives":[str],'
             '"language":str,"files":[{"name":str,"code":str}],"stdin":str}],"learning_outcomes":[str]}',
    "fix": '{"fixes":[{"index":int,"files":[{"name":str,"code":str}],"stdin":str}]}',
}


class AIError(RuntimeError):
    """Error with a message that is safe to show to the student."""


class RetryableAIError(AIError):
    """Quota, rate limit or outage: the next provider in the chain should try."""


# ── cache ──────────────────────────────────────────────────────────

class DraftCache:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.environ.get("LABFORGE_CACHE_DIR", ROOT / "artifacts" / "cache" / "drafts"))

    @staticmethod
    def key(sheet: str, language: str = "", variant: int = 0) -> str:
        """Sheet and language only: the subject a student types varies between classmates."""
        norm = re.sub(r"\s+", " ", sheet).strip().lower()
        raw = "\x1f".join([PROMPT_VERSION, norm, (language or "").lower(), str(variant)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]

    def get(self, key: str) -> AIReport | None:
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        try:
            return AIReport.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None

    def put(self, key: str, report: AIReport) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f"{key}.tmp"
        tmp.write_text(report.model_dump_json(), encoding="utf-8")
        tmp.replace(self.root / f"{key}.json")


# ── usage log ──────────────────────────────────────────────────────

_usage_lock = threading.Lock()


def log_usage(kind: str, model: str, meta: Any) -> dict:
    if isinstance(meta, dict):  # OpenAI-style usage block
        prompt_details = meta.get("prompt_tokens_details") or {}
        completion_details = meta.get("completion_tokens_details") or {}
        counts = {
            "input": meta.get("prompt_tokens"),
            "cached": prompt_details.get("cached_tokens") if isinstance(prompt_details, dict) else 0,
            "output": meta.get("completion_tokens"),
            "thinking": completion_details.get("reasoning_tokens") if isinstance(completion_details, dict) else 0,
        }
    else:
        counts = {
            "input": getattr(meta, "prompt_token_count", 0),
            "cached": getattr(meta, "cached_content_token_count", 0),
            "output": getattr(meta, "candidates_token_count", 0),
            "thinking": getattr(meta, "thoughts_token_count", 0),
        }
    record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind,
              "model": model, **{k: v or 0 for k, v in counts.items()}}
    path = Path(os.environ.get("LABFORGE_USAGE_LOG", ROOT / "artifacts" / "usage.jsonl"))
    with _usage_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    return record


def usage_summary(days: int = 1) -> dict:
    path = Path(os.environ.get("LABFORGE_USAGE_LOG", ROOT / "artifacts" / "usage.jsonl"))
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    totals: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                if datetime.fromisoformat(rec["ts"]).timestamp() < cutoff:
                    continue
            except (ValueError, KeyError):
                continue
            t = totals.setdefault(rec["model"], {"calls": 0, "input": 0, "cached": 0, "output": 0, "thinking": 0})
            t["calls"] += 1
            for k in ("input", "cached", "output", "thinking"):
                t[k] += rec.get(k, 0)
    return totals


# ── prompts ────────────────────────────────────────────────────────

def build_user_prompt(sheet: str, language: str = "", subject: str = "", variant: int = 0) -> str:
    lines = []
    if subject:
        lines.append(f"Subject: {subject}")
    if language and language != "auto":
        lines.append(f"Write the programs in: {language}")
    if variant:
        lines.append(f"Variant {variant}: use different identifiers, demo data and wording from the usual answer.")
    lines.append("Sheet:\n<<<\n" + sheet + "\n>>>")
    return "\n".join(lines)


def _validate(text: str, schema: type):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return schema.model_validate_json(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return schema.model_validate_json(match.group(0))
            except ValueError:
                pass
    raise RetryableAIError("the model returned JSON that doesn't match the report format")


# ── Gemini ─────────────────────────────────────────────────────────

class GeminiProvider:
    name = "gemini"

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
        self.fix_model = os.environ.get("GEMINI_FIX_MODEL", "") or self.model
        self.fallbacks = [m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]
        self.attempts = max(1, int(os.environ.get("GEMINI_MAX_ATTEMPTS", "2")))
        self.max_output = int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "12000"))
        self.thinking = os.environ.get("GEMINI_THINKING", "low").strip()
        self._client = None
        self._thinking_ok: dict[str, bool] = {}

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate(self, sheet: str, language: str = "", subject: str = "", variant: int = 0) -> AIReport:
        prompt = build_user_prompt(sheet, language, subject, variant)
        return self._call("draft", SYSTEM_PROMPT, prompt, AIReport, self.model, 0.7 if variant else 0.2)

    def fix(self, items: list[dict]) -> AIFixes:
        return self._call("fix", FIX_PROMPT, json.dumps(items, ensure_ascii=False), AIFixes, self.fix_model, 0.1)

    def _config(self, system: str, schema: type, temperature: float, model: str):
        from google.genai import types

        cfg: dict[str, Any] = dict(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
            max_output_tokens=self.max_output,
        )
        if self.thinking and self._thinking_ok.get(model, True):
            if self.thinking.isdigit():
                cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=int(self.thinking))
            else:
                cfg["thinking_config"] = types.ThinkingConfig(thinking_level=self.thinking)
        return types.GenerateContentConfig(**cfg)

    def _call(self, kind: str, system: str, prompt: str, schema: type, model: str, temperature: float):
        client = self._get_client()
        last: Exception | None = None
        for name in [model, *[m for m in self.fallbacks if m != model]]:
            attempt = 0
            while attempt < self.attempts:
                attempt += 1
                try:
                    resp = client.models.generate_content(
                        model=name, contents=prompt, config=self._config(system, schema, temperature, name))
                    log_usage(kind, f"gemini/{name}", getattr(resp, "usage_metadata", None))
                    return _parse_gemini(resp, schema)
                except RetryableAIError as exc:
                    last = exc
                    break
                except AIError:
                    raise
                except Exception as exc:  # noqa: BLE001 - provider errors are varied
                    last = exc
                    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                    msg = str(exc).lower()
                    if code == 400 and "thinking" in msg and self._thinking_ok.get(name, True):
                        self._thinking_ok[name] = False  # this model doesn't take the setting
                        attempt -= 1
                        continue
                    if code in (429, 500, 502, 503, 504) and attempt < self.attempts and "per day" not in msg:
                        time.sleep(min(2 ** attempt, 8))
                        continue
                    break  # next model
        raise RetryableAIError(f"gemini failed: {str(last)[:200]}") from last


def _parse_gemini(resp: Any, schema: type):
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    text = getattr(resp, "text", None) or ""
    if not text:
        reason = ""
        try:
            reason = str(resp.candidates[0].finish_reason)
        except Exception:  # noqa: BLE001
            pass
        if "MAX_TOKENS" in reason:
            raise AIError("This sheet is too long to write in one go. Upload one experiment at a time.")
        raise RetryableAIError("gemini returned nothing")
    return _validate(text, schema)


# ── OpenAI-compatible free tiers ───────────────────────────────────

OPENAI_COMPATIBLE = {
    # name: (base URL, key variable, default model). Override with <NAME>_MODEL / <NAME>_BASE_URL.
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),
    "cerebras": ("https://api.cerebras.ai/v1", "CEREBRAS_API_KEY", "gpt-oss-120b"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "openai/gpt-oss-120b:free"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "mistral-small-latest"),
    "github": ("https://models.github.ai/inference", "GITHUB_MODELS_TOKEN", "openai/gpt-4.1-mini"),
    # Workers AI behind a tiny proxy Worker on your own Cloudflare account (deploy/cloudflare-ai).
    # Free plan: 10,000 neurons a day, about 30 sheets with gpt-oss-120b.
    "cloudflare": ("", "CLOUDFLARE_AI_KEY", "@cf/openai/gpt-oss-120b"),
}
# Providers that accept OpenAI's reasoning_effort for gpt-oss; low keeps hidden reasoning short.
REASONING_EFFORT = {"groq", "cerebras", "cloudflare"}


class OpenAICompatProvider:
    def __init__(self, name: str, client: httpx.Client | None = None):
        base, key_env, model = OPENAI_COMPATIBLE[name]
        self.name = name
        self.base = os.environ.get(f"{name.upper()}_BASE_URL", base).rstrip("/")
        self.api_key = os.environ.get(key_env, "")
        self.model = os.environ.get(f"{name.upper()}_MODEL", model)
        self.max_output = int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "12000"))
        self.client = client

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base)

    def generate(self, sheet: str, language: str = "", subject: str = "", variant: int = 0) -> AIReport:
        prompt = build_user_prompt(sheet, language, subject, variant)
        return self._call("draft", SYSTEM_PROMPT, prompt, AIReport, 0.7 if variant else 0.2)

    def fix(self, items: list[dict]) -> AIFixes:
        return self._call("fix", FIX_PROMPT, json.dumps(items, ensure_ascii=False), AIFixes, 0.1)

    def _call(self, kind: str, system: str, prompt: str, schema: type, temperature: float):
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": f"{system}\nJSON shape: {SCHEMA_HINT[kind]}"},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": self.max_output,
            "response_format": {"type": "json_object"},
        }
        if self.name in REASONING_EFFORT and "gpt-oss" in self.model:
            body["reasoning_effort"] = os.environ.get("AI_REASONING_EFFORT", "low")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if self.name == "openrouter":
            headers["X-Title"] = "LabForge"
        client = self.client or httpx.Client(timeout=httpx.Timeout(120, connect=10))
        try:
            resp = None
            for attempt in (1, 2, 3):
                try:
                    resp = client.post(f"{self.base}/chat/completions", json=body, headers=headers)
                except httpx.HTTPError as exc:
                    raise RetryableAIError(f"{self.name} unreachable: {exc}") from exc
                if resp.status_code == 400 and "response_format" in body and "response_format" in resp.text:
                    body.pop("response_format")  # model without JSON mode: rely on the prompt
                    continue
                if resp.status_code == 429 and attempt == 1:
                    try:
                        wait = float(resp.headers.get("retry-after", "2"))
                    except ValueError:
                        wait = 2
                    time.sleep(min(wait, 6))
                    continue
                break
        finally:
            if self.client is None:
                client.close()
        if resp is None or resp.status_code != 200:
            code = resp.status_code if resp is not None else "no response"
            raise RetryableAIError(f"{self.name} returned {code}: {resp.text[:200] if resp is not None else ''}")
        data = resp.json()
        log_usage(kind, f"{self.name}/{self.model}", data.get("usage") or {})
        choice = (data.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "length":
            raise RetryableAIError(f"{self.name} ran out of output tokens")
        return _validate((choice.get("message") or {}).get("content") or "", schema)


class ProviderChain:
    """Tries each configured provider in order until one answers."""

    name = "chain"

    def __init__(self, providers: list):
        self.providers = [p for p in providers if p.configured]

    @property
    def configured(self) -> bool:
        return bool(self.providers)

    def describe(self) -> list[str]:
        return [f"{p.name}:{p.model}" for p in self.providers]

    def generate(self, sheet: str, language: str = "", subject: str = "", variant: int = 0) -> AIReport:
        report = self._each(lambda p: p.generate(sheet, language, subject, variant))
        if not report.tasks:
            raise AIError("No tasks were found in this sheet. Check that it's the experiment sheet.")
        return report

    def fix(self, items: list[dict]) -> AIFixes:
        return self._each(lambda p: p.fix(items))

    def _each(self, call):
        if not self.providers:
            raise AIError("No AI provider is configured on the server, so new sheets can't be written yet.")
        errors = []
        for provider in self.providers:
            try:
                return call(provider)
            except RetryableAIError as exc:
                errors.append(str(exc))
        print("[ai] all providers failed: " + " | ".join(errors))
        raise AIError("Every AI service is busy or out of free quota right now. Try again in a few minutes.")


# ── offline ────────────────────────────────────────────────────────

class LocalProvider:
    """Offline stand-in (AI_MODE=local): reuses code found in Easy/Medium/Hard sheets."""

    name = "local"
    model = "offline"
    configured = True

    def describe(self) -> list[str]:
        return ["local:offline"]

    def generate(self, sheet: str, language: str = "", subject: str = "", variant: int = 0) -> AIReport:
        from core.ingestion.parser import parse_text

        doc = parse_text(sheet)
        objectives = [o.strip(" •·-\t") for o in doc.objectives.splitlines() if o.strip(" •·-\t")][:3]
        tasks = []
        for level in ("easy", "medium", "hard"):
            src = getattr(doc, level)
            if not src or not src.code:
                continue
            code = src.code
            lang = language if language and language != "auto" else (
                "java" if re.search(r"\bclass\s+\w+|System\.out", code) else "python")
            tasks.append(AITask(
                title=f"{level.title()} Level",
                problem=src.problem_statement or f"{level.title()} level task.",
                objectives=objectives or ["Apply the concepts from this experiment."],
                language=lang,
                files=[AIFile(name="", code=code)],
                stdin=_guess_stdin(code),
            ))
        if not tasks:
            raise AIError("Offline mode only reads sheets that already contain the code. Set AI_MODE=cloud.")
        return AIReport(
            experiment_no=doc.metadata.experiment_number,
            title=doc.metadata.title,
            aim=doc.metadata.aim or "To implement and test the programs described in this experiment.",
            tasks=tasks,
            learning_outcomes=[
                "Applied the concepts of this experiment in working programs.",
                "Handled invalid input and error cases explicitly.",
                "Tested each program and verified its output.",
            ],
        )

    def fix(self, items: list[dict]) -> AIFixes:
        return AIFixes(fixes=[])


def _guess_stdin(code: str) -> str:
    reads = len(re.findall(r"\.next(?:Int|Double|Line|Float|Long)?\s*\(|\binput\s*\(", code))
    if not reads:
        return ""
    low = code.lower()
    if "pin" in low:
        return "1234\n500\n"
    if "sqrt" in low or "square" in low:
        return "25\n"
    if "yes" in low:
        return "yes\n" * reads
    return "5\n" * reads


def get_provider():
    if os.environ.get("AI_MODE", "cloud").lower() == "local":
        return LocalProvider()
    order = os.environ.get("AI_PROVIDERS", "gemini,cloudflare,groq,cerebras,openrouter,mistral,github")
    providers = []
    for name in (p.strip().lower() for p in order.split(",") if p.strip()):
        if name == "gemini":
            providers.append(GeminiProvider())
        elif name in OPENAI_COMPATIBLE:
            providers.append(OpenAICompatProvider(name))
    return ProviderChain(providers)
