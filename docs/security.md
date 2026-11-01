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
- **Jobs expire** after `LABFORGE_JOB_TTL_HOURS`.

## Required for a public deployment

`EXEC_BACKEND=local` runs programs as the server's user, which is fine on your
own machine and not enough on the internet. Run the provided container
(unprivileged user, memory, CPU and process limits) or use
`EXEC_BACKEND=docker` for one network-less container per run. See
[deployment.md](deployment.md).
