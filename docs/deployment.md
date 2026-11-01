# Deploying LabForge

## One machine with Docker (simplest)

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

- Programs get a scrubbed environment: no API keys or other secrets.
- Wall-clock timeouts on every compile, run and build.
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
