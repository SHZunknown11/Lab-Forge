"""Deploy LabForge to Render's free plan (no card): one Docker web service built from GitHub.

    python scripts/deploy_render.py              # create or update "labforge", wait, smoke-test
    python scripts/deploy_render.py --no-wait

Needs RENDER_API_KEY in .env (Account Settings -> API Keys). Render builds the
Dockerfile from the public GitHub repo, so push first: what's on GitHub is what
gets deployed. AI keys from .env become the service's environment variables.
"""
from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from deploy_hf import PROVIDER_KEYS, PROVIDER_SETTINGS, read_env  # noqa: E402

API = "https://api.render.com/v1"
REPO = "https://github.com/SHZunknown11/Lab-Forge"
NAME = "labforge"
FROM_ENV = ("GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_FALLBACK_MODELS", "GEMINI_MAX_ATTEMPTS", "GEMINI_THINKING",
            *PROVIDER_KEYS, *PROVIDER_SETTINGS, "AI_PROVIDERS", "AI_TIMEOUT_SECONDS", "AI_HEDGE_SECONDS",
            "AI_REASONING_EFFORT", "LABFORGE_ADMIN_TOKEN", "LABFORGE_AI_DAILY_LIMIT", "LABFORGE_LOG_DB_URL")
# The free instance: 512 MB RAM, 0.1 CPU.
SMALL_HOST = {
    "LABFORGE_MAX_PARALLEL_RUNS": "1",
    "LABFORGE_TIMEOUT_SCALE": "5",
    "LABFORGE_TRUST_PROXY": "1",
    # Render is behind Cloudflare, which sets this from the real connection.
    "LABFORGE_CLIENT_IP_HEADER": "true-client-ip",
}


class Render:
    def __init__(self, key: str):
        self.http = httpx.Client(base_url=API, timeout=60, headers={
            "Authorization": f"Bearer {key}", "Accept": "application/json"})

    def __call__(self, method: str, path: str, **kw):
        resp = self.http.request(method, path, **kw)
        if resp.status_code >= 400:
            sys.exit(f"Render API {method} {path}: {resp.status_code} {resp.text[:300]}")
        return resp.json() if resp.content else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--region", default="singapore")
    args = parser.parse_args()

    env = read_env()
    if not env.get("RENDER_API_KEY"):
        sys.exit("Add RENDER_API_KEY=<key from Render > Account Settings > API Keys> to .env")
    if not env.get("LABFORGE_ADMIN_TOKEN"):
        env["LABFORGE_ADMIN_TOKEN"] = secrets.token_urlsafe(24)
        with (ROOT / ".env").open("a", encoding="utf-8") as fh:
            fh.write(f"\n# /api/admin/status and /api/admin/usage on the deployed site\n"
                     f"LABFORGE_ADMIN_TOKEN={env['LABFORGE_ADMIN_TOKEN']}\n")
    variables = {k: env[k] for k in FROM_ENV if env.get(k)} | SMALL_HOST
    render = Render(env["RENDER_API_KEY"])

    ahead = subprocess.run(["git", "rev-list", "--count", "origin/main..HEAD"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    if ahead not in ("", "0"):
        print(f"  note: {ahead} local commit(s) aren't on GitHub yet; Render builds what's pushed")

    owner = render("GET", "/owners")[0]["owner"]["id"]
    existing = [s["service"] for s in render("GET", "/services", params={"name": NAME, "limit": 20})
                if s["service"]["name"] == NAME]
    env_list = [{"key": k, "value": v} for k, v in variables.items()]
    if existing:
        service = existing[0]
        print(f"Updating {service['name']} ({service['id']})")
        render("PUT", f"/services/{service['id']}/env-vars", json=env_list)
        deploy = render("POST", f"/services/{service['id']}/deploys", json={"clearCache": "do_not_clear"})
        deploy_id = deploy["id"]
    else:
        print(f"Creating {NAME} on the free plan in {args.region}")
        created = render("POST", "/services", json={
            "type": "web_service", "name": NAME, "ownerId": owner, "repo": REPO, "branch": "main",
            "autoDeploy": "no", "envVars": env_list,
            "serviceDetails": {
                "runtime": "docker", "plan": "free", "region": args.region,
                "healthCheckPath": "/api/health",
                "envSpecificDetails": {"dockerfilePath": "./Dockerfile", "dockerContext": "."},
            },
        })
        service, deploy_id = created["service"], created.get("deployId")
    url = service["serviceDetails"]["url"]
    for key in variables:
        print(f"  env {key}")
    print(f"  {url}")
    if args.no_wait:
        return 0

    last, deadline = "", time.time() + 45 * 60
    while time.time() < deadline:
        deploys = render("GET", f"/services/{service['id']}/deploys", params={"limit": 5})
        current = next((d["deploy"] for d in deploys if not deploy_id or d["deploy"]["id"] == deploy_id),
                       deploys[0]["deploy"])
        status = current["status"]
        if status != last:
            print(f"  {time.strftime('%H:%M:%S')} {status}")
            last = status
        if status == "live":
            break
        if status in ("build_failed", "update_failed", "canceled", "deactivated", "pre_deploy_failed"):
            print(f"  logs: https://dashboard.render.com/web/{service['id']}/deploys/{current['id']}")
            return 1
        time.sleep(20)
    print(f"Live: {url}")
    # The admin key keeps the smoke test's reports out of the site's activity log.
    smoke_env = {**os.environ, "LABFORGE_ADMIN_TOKEN": env.get("LABFORGE_ADMIN_TOKEN", "")}
    return subprocess.call([sys.executable, str(ROOT / "scripts" / "smoke_test.py"), url, "--ai"], env=smoke_env)


if __name__ == "__main__":
    sys.exit(main())
