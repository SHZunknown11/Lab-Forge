"""Deploy LabForge to a free Hugging Face Space (Docker, 2 vCPU, 16 GB RAM).

    pip install huggingface_hub
    python scripts/deploy_hf.py                 # create/update <you>/labforge, push secrets, wait, smoke-test
    python scripts/deploy_hf.py --space me/lab  # another Space name
    python scripts/deploy_hf.py --no-wait

Needs HF_TOKEN (a *write* token from https://huggingface.co/settings/tokens) in the
environment or .env. API keys from .env become Space secrets; nothing else from .env
is uploaded. The source sent is the committed HEAD (git archive), so commit first;
your profile, keys and uncommitted files never leave the machine.
"""
from __future__ import annotations

import argparse
import os
import io
import secrets
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files the Docker build needs (tracked by git, filtered by these prefixes).
INCLUDE = ("Dockerfile", ".dockerignore", "pyproject.toml", "main.py", "apps/api/", "apps/frontend/",
           "core/", "scripts/", "templates/", "config/subjects.json", "config/student_profile.example.json")
SECRETS = ("GEMINI_API_KEY", "CLOUDFLARE_AI_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY",
           "MISTRAL_API_KEY", "GITHUB_MODELS_TOKEN", "LABFORGE_ADMIN_TOKEN")
VARIABLES = ("AI_PROVIDERS", "GEMINI_MODEL", "GEMINI_FALLBACK_MODELS", "GEMINI_MAX_ATTEMPTS", "GEMINI_THINKING",
             "CLOUDFLARE_BASE_URL", "CLOUDFLARE_MODEL", "GROQ_MODEL", "OPENROUTER_MODEL", "AI_REASONING_EFFORT",
             "LABFORGE_AI_DAILY_LIMIT", "VITE_ADSENSE_CLIENT", "VITE_ADSENSE_SLOT_RAIL", "VITE_ADSENSE_SLOT_BENCH")

SPACE_README = """---
title: LabForge
emoji: 🧪
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
pinned: false
short_description: Lab reports from your experiment sheet, with real output
---

# LabForge

Upload an experiment sheet, fill in your details, and get a finished lab report
(Word and PDF): aim, objectives, code that was actually compiled and run, real
console output and screenshots, and learning outcomes.

Source: https://github.com/SHZunknown11/Lab-Forge
"""


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    values.update({k: v for k, v in os.environ.items() if k in values or k == "HF_TOKEN"})
    return values


def ensure_admin_token(env: dict[str, str]) -> None:
    if env.get("LABFORGE_ADMIN_TOKEN"):
        return
    env["LABFORGE_ADMIN_TOKEN"] = secrets.token_urlsafe(24)
    with (ROOT / ".env").open("a", encoding="utf-8") as fh:
        fh.write(f"\n# /api/admin/status and /api/admin/usage on the deployed site\n"
                 f"LABFORGE_ADMIN_TOKEN={env['LABFORGE_ADMIN_TOKEN']}\n")


def committed_files() -> dict[str, bytes]:
    """The build inputs exactly as committed (LF line endings, no local edits)."""
    listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.splitlines()
    wanted = [f for f in listed if f.startswith(INCLUDE)]
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD", "--", *wanted], cwd=ROOT,
                             capture_output=True, check=True).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                files[member.name] = tar.extractfile(member).read()
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--space", help="owner/name (default: <your user>/labforge)")
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()

    try:
        from huggingface_hub import CommitOperationAdd, HfApi
    except ImportError:
        sys.exit("pip install huggingface_hub")

    env = read_env()
    token = env.get("HF_TOKEN")
    if not token:
        sys.exit("Add HF_TOKEN=<write token from https://huggingface.co/settings/tokens> to .env")
    api = HfApi(token=token)
    user = api.whoami()["name"]
    repo_id = args.space or f"{user}/labforge"
    host = repo_id.replace("/", "-").replace("_", "-").lower()
    url = f"https://{host}.hf.space"

    print(f"Space {repo_id}")
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True, private=False)

    ensure_admin_token(env)
    for key in SECRETS:
        if env.get(key):
            api.add_space_secret(repo_id, key, env[key])
            print(f"  secret   {key}")
    for key in VARIABLES:
        if env.get(key):
            api.add_space_variable(repo_id, key, env[key])
            print(f"  variable {key}={env[key]}")

    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *INCLUDE], cwd=ROOT).returncode:
        print("  note: uncommitted changes are not deployed; commit them first to include them")
    files = committed_files()
    ops = [CommitOperationAdd(path_in_repo=name, path_or_fileobj=data) for name, data in files.items()]
    ops.append(CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=SPACE_README.encode("utf-8")))
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    api.create_commit(repo_id, ops, repo_type="space", commit_message=f"Deploy {sha or 'local'}")
    print(f"  uploaded {len(files) + 1} files; building (first build takes ~10 minutes)")

    if args.no_wait:
        print(url)
        return 0
    last = ""
    deadline = time.time() + 40 * 60
    while time.time() < deadline:
        stage = api.get_space_runtime(repo_id).stage
        if stage != last:
            print(f"  {stage}")
            last = stage
        if stage == "RUNNING":
            break
        if stage in ("BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"):
            print(f"  see the logs: https://huggingface.co/spaces/{repo_id}?logs=build")
            return 1
        time.sleep(20)
    print(f"Live: {url}")
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "smoke_test.py"), url, "--ai"])


if __name__ == "__main__":
    sys.exit(main())
