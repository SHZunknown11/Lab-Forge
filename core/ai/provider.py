"""AI provider abstraction with caching, local mock, and Gemini cloud support."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from core.schemas import (
    ExperimentDocument,
    GeneratedContent,
    GeneratedLevel,
)


class LocalMockProvider:
    """Deterministic mock provider for local/test usage."""

    def generate_experiment(self, document: ExperimentDocument) -> GeneratedContent:
        levels = {}
        for level_name in ("easy", "medium", "hard"):
            src_level = getattr(document, level_name, None)
            if src_level:
                levels[level_name] = GeneratedLevel(
                    problem_statement=src_level.problem_statement or f"{level_name.title()} problem",
                    objectives=src_level.objectives or f"Learn {level_name} concepts",
                    filename=src_level.filename or f"{level_name.title()}Level.java",
                    code=src_level.code or f"public class {level_name.title()}Level {{}}",
                    expected_behavior=f"Expected {level_name} output",
                )

        return GeneratedContent(
            experiment_number=document.metadata.experiment_number,
            title=document.metadata.title,
            global_aim=document.metadata.aim,
            easy=levels.get("easy"),
            medium=levels.get("medium"),
            hard=levels.get("hard"),
            learning_outcomes=[
                f"Understand {document.metadata.aim[:50]}",
                "Apply concepts in practice",
            ],
        )

    def get_metadata(self) -> dict[str, Any]:
        return {"provider": "LocalMockProvider", "model": "mock-local"}


class GeminiProvider:
    """Cloud AI provider using the Google GenAI SDK."""

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        self.max_attempts = int(os.environ.get("GEMINI_MAX_ATTEMPTS", "5"))
        fallback_str = os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash")
        self.fallback_models = [m.strip() for m in fallback_str.split(",") if m.strip()]
        self._client = None

    def _get_client(self):
        if self._client is None:
            import google.genai as genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _generate_json(self, prompt: str, schema: type) -> dict:
        """Generate JSON from a prompt with retry and fallback logic."""
        import google.genai as genai
        import time

        models_to_try = [self.model] + self.fallback_models
        client = self._get_client()
        last_error = None

        for model_name in models_to_try:
            print(f"    Trying model: {model_name}")
            for attempt in range(self.max_attempts):
                try:
                    config = genai.types.GenerateContentConfig(
                        response_mime_type="application/json",
                    )
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )
                    return json.loads(response.text) if response.text else {}
                except Exception as e:
                    last_error = e
                    code = getattr(e, "code", getattr(e, "status_code", 0))
                    error_msg = str(e).lower()
                    print(f"    Model {model_name} (attempt {attempt+1}) failed (code={code}): {str(e)[:120]}")
                    
                    if code == 429:
                        if "per day" in error_msg or "daily" in error_msg:
                            print(f"    Daily quota exhausted for {model_name}, moving to fallback immediately.")
                            break  # Skip remaining attempts for this model
                        
                        if attempt < self.max_attempts - 1:
                            # Exponential backoff for RPM limits
                            time.sleep(min(2 ** attempt, 10))
                            continue
                    elif code in (500, 503) and attempt < self.max_attempts - 1:
                        time.sleep(min(2 ** attempt, 10))
                        continue
                    
                    # On other errors (like 404, 400) or exhausted attempts, break to try the next model
                    break
        
        raise last_error

        return {}

    def generate_experiment(self, document: ExperimentDocument) -> GeneratedContent:
        prompt = self._build_prompt(document)
        data = self._generate_json(prompt, dict)
        return GeneratedContent(**data) if data else self._fallback(document)

    def _build_prompt(self, document: ExperimentDocument) -> str:
        parts = [
            f"Generate a structured JSON for Experiment {document.metadata.experiment_number}.",
            f"Title: {document.metadata.title}",
            f"Aim: {document.metadata.aim}",
        ]

        for level_name in ("easy", "medium", "hard"):
            level = getattr(document, level_name, None)
            if level:
                parts.append(f"\n{level_name.upper()} Level:")
                parts.append(f"Problem: {level.problem_statement}")
                if level.code:
                    parts.append(f"Provided code:\n{level.code}")

        parts.append(
            "\nReturn JSON with keys: experiment_number, title, global_aim, "
            "easy (object with problem_statement, objectives, filename, code, expected_behavior), "
            "medium (same structure), hard (same structure), learning_outcomes (list of strings)."
            "\n\nCRITICAL INSTRUCTIONS FOR CODE GENERATION:\n"
            "1. Write clean, concise Java code.\n"
            "2. K&R STYLE: Place opening brackets '{', '[', '(' on the SAME LINE as the statement, never on a new line.\n"
            "3. Minimize unnecessary blank lines and vertical spacing to keep the code compact.\n"
            "4. Generate FULL, COMPILABLE, SELF-CONTAINED code.\n"
            "5. NEVER use Scanner, BufferedReader, or any interactive input. Use HARDCODED demo values instead.\n"
            "6. NEVER connect to external databases. If the problem requires JDBC, you must write mock classes (e.g., MockConnection, MockStatement, MockResultSet) to simulate the database.\n"
            "7. CRITICAL: If you use try-with-resources, EVERY mock class declared in the try(...) block MUST explicitly 'implements AutoCloseable' (and have a public void close() throws Exception method) or it will cause a compilation error!\n"
            "8. The code MUST run standalone with NO user interaction and NO external services.\n"
            "9. Print clear output demonstrating the program's functionality with the hardcoded data.\n"
            "10. Each program should have exactly ONE public class with a public static void main method."
        )

        if document.objectives:
            parts.append(f"\nObjectives from source: {document.objectives}")
        if document.reading_material:
            parts.append(f"\nReading material: {document.reading_material[:500]}")

        return "\n".join(parts)

    def _fallback(self, document: ExperimentDocument) -> GeneratedContent:
        """Fallback to mock if API completely fails."""
        return LocalMockProvider().generate_experiment(document)

    def get_metadata(self) -> dict[str, Any]:
        return {"provider": "GeminiProvider", "model": self.model}


class AIOrchestrator:
    """Wraps any provider with caching."""

    def __init__(self, cache_dir: Optional[Path] = None, provider=None):
        mode = os.environ.get("AI_MODE", "local")
        if provider:
            self.provider = provider
        elif mode == "cloud":
            self.provider = GeminiProvider()
        else:
            self.provider = LocalMockProvider()
        self.cache_dir = cache_dir or Path("artifacts/.ai_cache")

    def generate(
        self, document: ExperimentDocument, force_refresh: bool = False
    ) -> GeneratedContent:
        cache_file = self._cache_path(document)

        if not force_refresh and cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return GeneratedContent(**data)

        result = self.provider.generate_experiment(document)

        # Write cache
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(result.model_dump_json(indent=2), encoding="utf-8")

        return result

    def _cache_path(self, document: ExperimentDocument) -> Path:
        meta = self.provider.get_metadata()
        provider_name = type(self.provider).__name__
        model_name = meta.get("model", "unknown")
        exp_num = document.metadata.experiment_number
        return self.cache_dir / f"exp_{exp_num}_{provider_name}_{model_name}_cache.json"
