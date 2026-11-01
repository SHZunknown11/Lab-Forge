# Deploying LabForge

## Hugging Face Spaces (free)

A Docker Space gives 2 vCPU and 16 GB RAM for free; the container sleeps
after two days without visitors and wakes on the next visit (about a minute).

1. Create a write token at https://huggingface.co/settings/tokens and add
   `HF_TOKEN=...` to `.env`.
2. `pip install huggingface_hub`, then `python scripts/deploy_hf.py`.

The script creates `<you>/labforge`, stores the AI keys from `.env` as Space
secrets (non-secret settings as variables), uploads only git-tracked source
files, waits for the build and smoke-tests `https://<you>-labforge.hf.space`.
Run it again to deploy a new version. Job folders and the draft cache live on
the container's disk, so a restart clears them.

AdSense needs a domain you own: put one in front of the Space (Cloudflare
proxy or a redirect) or move to a host with custom domains.

## One machine with Docker

```bash
cp .env.example .env          # add at least one AI key
docker compose up -d --build  # app on :8000, Gotenberg for PDFs on the private network
```

Put a reverse proxy with HTTPS in front (Caddy, nginx, Cloudflare Tunnel). The
compose file sets `LABFORGE_TRUST_PROXY=1`, so per-visitor limits use the
`X-Forwarded-For` address; only enable that when a proxy really sets the header.

Data lives in the `labforge-data` volume: job folders (deleted after
`LABFORGE_JOB_TTL_HOURS`), the draft cache and `usage.jsonl`.

## Running student code safely

Uploaded sheets decide what code the model writes, so treat every program as
untrusted. Layers already in place:

- Programs get a scrubbed environment: no API keys or other secrets. The
  server process marks itself non-dumpable on Linux, so a program running as
  the same user can't read its keys from `/proc/<pid>/environ` either.
- Wall-clock timeouts on every compile, run and build. On Linux each run is
  its own process group, killed as a whole, with `prlimit` caps on CPU time,
  file size and core dumps; `LABFORGE_MAX_PARALLEL_RUNS` caps concurrency.
- `EXEC_ALLOW_NETWORK=0` (the image default): programs only reach loopback.
  If the kernel allows unprivileged namespaces, each run gets a private
  network namespace; otherwise the Python, Node and Java launchers refuse
  non-loopback connections. `GET /api/admin/status?token=...` shows which.
- The image's app code is owned by root and read-only to the app user.
- Screenshotted pages can only reach LabForge's own throwaway static server
  (outbound requests go to a dead proxy). Keep `HTML_ALLOW_NETWORK=0`.
- Uploaded screenshots are re-encoded as PNG.
- File names from the model can't leave the work folder.

For a public site, also do one of these:

1. Run the container as in `docker-compose.yml`: unprivileged user, memory,
   CPU and process limits, `no-new-privileges`. The container is the boundary.
2. Stronger: set `EXEC_BACKEND=docker` on a host with Docker, so each program
   runs in its own container with `--network none`, `--cap-drop ALL`, 384 MB
   and one CPU. Build a Python image with the scientific libraries and set
   `EXEC_IMAGE_PYTHON` to it.

## Token spend

`GET /api/admin/usage?token=$LABFORGE_ADMIN_TOKEN&days=7` returns calls and
input, cached, output and thinking tokens per model. Typical numbers with
Gemini Flash: a new three-program sheet costs about 2k input and 2k output
tokens; an uploaded-before sheet costs nothing.

## Ads (Google AdSense)

1. Get approved: AdSense wants a live domain with real content. The About and
   Privacy pages (`#/about`, `#/privacy`) are already there; keep them.
2. Create two display units (a 300x250 rectangle for the sidebar, a responsive
   horizontal unit under the page) and build with:

   ```bash
   VITE_ADSENSE_CLIENT=ca-pub-XXXXXXXXXXXXXXXX \
   VITE_ADSENSE_SLOT_RAIL=1111111111 \
   VITE_ADSENSE_SLOT_BENCH=2222222222 \
   docker compose up -d --build
   ```

3. Add `apps/frontend/public/ads.txt` containing
   `google.com, pub-XXXXXXXXXXXXXXXX, DIRECT, f08c47fec0942fa0` and rebuild.
4. In the EU/UK, AdSense requires a consent banner: enable Google's CMP in the
   AdSense dashboard (Privacy & messaging).

Ads sit in the sidebar and under the page, never between the student and the
download button.
