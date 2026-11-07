# Security

The main risk is running code that a model wrote from a sheet anyone can
upload: a crafted sheet can steer the model into writing hostile code. Treat
every program as untrusted.

## In place

- **No secrets in child processes.** Programs get a minimal environment
  (`PATH`, temp folders, encoding settings); API keys never reach them.
- **Timeouts** on every compile, run, React build and screenshot.
- **Contained file names.** Paths from the model are reduced to safe relative
  names inside the work folder (`safe_rel`).
- **No outbound requests from screenshotted pages.** Chrome uses a dead proxy,
  with only LabForge's throwaway static server reachable
  (`HTML_ALLOW_NETWORK=0`). This blocks SSRF to internal services.
- **Uploads are re-encoded** to PNG with Pillow; anything that isn't an image is refused.
- **Unguessable job ids** (UUID4) and strict file-name patterns on download routes.
- **Per-IP limits** on new sheets, runs, renders and uploads.
- **Jobs expire** after `LABFORGE_JOB_TTL_HOURS` (6 hours in the image).
- **Server keys stay private** from programs on Linux: the API process is
  non-dumpable, so `/proc/<pid>/environ` and `/proc/<pid>/mem` are root-only.
- **No internet for programs** (`EXEC_ALLOW_NETWORK=0` in the image): a
  network namespace when the host allows it, loopback-only guards otherwise.
- **Process limits** on Linux: process-group kill on timeout, `prlimit` on
  CPU time, file size and core dumps, and a global cap on parallel runs.
- **Read-only app code** in the image; only `artifacts/` is writable.
- **Spoof-resistant visitor IPs**: with `LABFORGE_TRUST_PROXY=<hops>` only the
  addresses your own proxies appended to `X-Forwarded-For` count.

- **Programs can't be fed arbitrary code for free.** The server remembers the
  code it wrote for each task. Re-running that code with any input is a normal
  run; changed code counts against a separate, small hourly limit, and changed
  shell scripts are refused. Limits are per browser and per IP, in Postgres.
- **Output can't be invented.** Run results are stored on the server. A
  rendered report always takes its console output, status and captured figures
  from there, for the exact code and input that produced them; whatever output
  a browser sends is ignored. Changed code has no output until it runs again.
- **Runs happen outside job folders** (`LABFORGE_RUN_DIR`), so relative paths
  can't reach a report's files, and the draft cache lives in Postgres when
  `LABFORGE_DATABASE_URL` is set.
- **Separate execution worker** (`EXEC_BACKEND=remote`, `apps/worker`): the
  real fix for everything below. Student code then never runs on the web server.
- **Admin token only in a header**, never in URLs (which end up in logs).
- **Security headers**: a strict, nonce-based Content-Security-Policy on pages
  (compatible with AdSense), `X-Frame-Options: DENY`, `Permissions-Policy`,
  HSTS behind HTTPS.
- **Minimal logging**: no names or UIDs by default, IPs hashed, only the start
  of each sheet, 14 days; students can delete a report and its log rows.

## Known limits on single-container hosts

On hosts without nested containers (Hugging Face Spaces, Render, Koyeb),
programs run as the app user inside the one container. The loopback guards
in the launchers stop ordinary programs, but a deliberately hostile program
(raw syscalls, C) could still reach the network when the host forbids network
namespaces, and could read other visitors' job folders for up to
`LABFORGE_JOB_TTL_HOURS`. Keep the TTL short there, or use a host with Docker
and `EXEC_BACKEND=docker` for a hard boundary.

## Required for a public deployment

`EXEC_BACKEND=local` runs programs as the server's user, which is fine on your
own machine and not enough on the internet. Use `EXEC_BACKEND=remote` with a
worker on a separate machine (best), or `EXEC_BACKEND=docker` for one
network-less container per run. See [deployment.md](deployment.md).
