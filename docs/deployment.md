# Deploying LabForge

## Render (free, no card)

`render.yaml` describes the service; `scripts/deploy_render.py` creates it
through Render's API (needs `RENDER_API_KEY` in `.env`), copies the AI keys
from `.env`, waits for the build and smoke-tests the live URL. Render builds
from the GitHub repo, so push before deploying.

The free instance has 512 MB RAM and 0.1 CPU, so the service runs with
`LABFORGE_MAX_PARALLEL_RUNS=1` (programs, Chrome and LibreOffice take turns)
and `LABFORGE_TIMEOUT_SCALE=5`. A report takes a minute or two instead of
seconds. Free services sleep after 15 idle minutes; `deploy/keepalive` is a
Cloudflare Worker cron that pings `/api/health` every 10 minutes from 07:30 to
00:30 IST. All free services in a workspace share 750 hours a month, and
Render suspends them all when the hours run out, so don't ping around the
clock if the workspace has other free services.

## Hugging Face Spaces (needs PRO)

Since 2026 Hugging Face only hosts Docker and Gradio Spaces for PRO accounts
(free accounts get static Spaces only). With PRO, a Docker Space gives 2 vCPU
and 16 GB RAM.

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

## Accounts and sign-in

Students sign in with a 6-digit code sent to their college email
(`core/accounts.py`). Three things must be set before turning it on:

1. **A database.** `LABFORGE_DATABASE_URL` (Neon). Without it accounts go to
   `artifacts/accounts.sqlite3`, which is lost whenever the host wipes its disk.
2. **A way to send email.** `RESEND_API_KEY` plus `LABFORGE_MAIL_FROM` on a
   domain you've verified with Resend, or `SMTP_HOST`/`SMTP_USER`/
   `SMTP_PASSWORD` (Gmail with an app password sends about 500 a day). Render's
   free plan blocks outgoing SMTP, so use Resend there. `/admin` status shows
   which backend is active. Send yourself a code first: college mail servers
   sometimes put mail from new senders in spam.
3. **`LABFORGE_SECRET`**, a long random value that never changes. It keys the
   sign-in codes and the key that locks each student's reports on their device.

`LABFORGE_EMAIL_DOMAINS` (default `cuchd.in`) says who may sign in,
`LABFORGE_FREE_REPORTS` and `LABFORGE_FREE_PERIOD` how many reports are free.
`LABFORGE_REQUIRE_LOGIN=0` turns sign-in off again.

In `/admin`: **Accounts** lists who signed in, lets you give extra reports or
block an account; **Failed sessions** shows every session where a program
failed or couldn't be run, with the sheet, the code and the error, kept for
`LABFORGE_FLAG_DAYS` days.

## Extra reports for watching an ad

A signed-in student who has run out of free reports can watch an ad for another one
(`apps/frontend/src/rewarded.ts`, `/api/ads/ticket` and `/api/ads/claim`).

1. In Google Ad Manager, create a **rewarded** ad unit for the web and copy its path
   (`/<network code>/<unit name>`). Ordinary AdSense display units must not be used for this:
   rewarding visitors for looking at them is against AdSense policy. The rewarded format is
   the one made for it.
2. Build the frontend with `VITE_REWARDED_AD_UNIT=<that path>`.
3. Set `LABFORGE_AD_REWARDS_PER_DAY` (e.g. `5`) on the server. `0` keeps the feature off.

The browser tells the server the ad was watched, and the server has no way to confirm it with
Google, so a student who knows how can claim reports without watching. Three things limit
that: a ticket can't be claimed sooner than `LABFORGE_AD_MIN_SECONDS` after it was issued,
each ticket pays once, and the daily cap. Keep the cap low.

`VITE_REWARDED_AD_TEST=1` shows a labelled stand-in with a countdown, to try the flow without
an ad account.

## Gaps: what to add next

Whenever a report hits something LabForge can't do (a language it can't run, a library that
isn't installed, a program that needs a window, the runner being offline), it is counted
under a stable name (`core/gaps.py`). The **Gaps** tab in `/admin` lists them, most reports
first, with the subjects they came from and a link to the latest saved session.

When `LABFORGE_GAP_ALERT_AT` reports (default 3) have hit the same gap you get one alert: on
Telegram if `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set, otherwise by email to
`LABFORGE_OWNER_EMAIL`. A runner that is offline alerts the first time. "Dealt with" in the
tab clears a gap, so it alerts again if it ever comes back.

## Your own server (VPS)

Render's free plan (a tenth of a CPU, asleep when idle) can't serve a class at deadline time.
Any small Linux server with Docker can: 2 CPUs and 4 GB are enough to start.

```bash
git clone https://github.com/SHZunknown11/Lab-Forge && cd Lab-Forge
cp .env.example .env            # AI keys, LABFORGE_DATABASE_URL, LABFORGE_SECRET, mail, ...
WITH_OCTAVE=1 LABFORGE_DOMAIN=labforge.in docker compose --profile https --profile worker up -d --build
```

That starts the app, Gotenberg for PDFs, a worker for student programs and Caddy, which gets
the HTTPS certificate for `LABFORGE_DOMAIN` by itself (point the domain's A record at the
server and open ports 80 and 443 first). Set `EXEC_BACKEND=remote`,
`EXEC_WORKER_URL=http://worker:8100` and `EXEC_WORKER_TOKEN` in `.env` so programs run in the
worker, which holds no secrets.

**More capacity.** Run the worker on more machines (same image, `EXEC_WORKER_TOKEN` set,
port 8100 reachable only from the app) and list them all in `EXEC_WORKER_URL`, comma-separated.
Each run goes to one of them, and to the next if it is down. `LABFORGE_MAX_ACTIVE_DRAFTS`
caps how many reports are written at once; the rest wait in a queue the student can see.

**Nothing to lose on a restart.** Accounts, credits and the cache are in Postgres; job folders
are in the `labforge-data` volume and are deleted after a few hours anyway; finished reports
live on the students' own devices. So there is no separate file store to run.

**Uptime.** Point a free monitor (UptimeRobot, Better Stack) at `/api/health`. LabForge's own
alerts (Telegram or email) cover gaps, the runner going offline, and a weekly summary.

## MATLAB sheets (GNU Octave)

Built with `WITH_OCTAVE=1`, the image has GNU Octave with its image, signal and statistics
packages, and MATLAB tasks are run in it: printed output and every figure go into the report
(`core/execution/harness/lf_octave.m`). MATLAB's sample pictures (`cameraman.tif`,
`coins.png`, ...) aren't part of Octave, so stand-ins with the same names are put next to
each script. A script that uses a function Octave doesn't have is marked for the student to
run in MATLAB, and shows up under Gaps. `EXEC_MATLAB=0` turns this off.

This runner was written without an Octave install to try it on. Build one image with
`WITH_OCTAVE=1`, write an Image Processing sheet, and check the result before relying on it.

## Paid packs (Razorpay)

1. Create a Razorpay account and take the **test** key id and secret from the dashboard.
2. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` and `LABFORGE_PACKS` (rupees:reports, e.g.
   `10:10,49:70`). A "Buy reports" box appears for signed-in students.
3. In the dashboard add a webhook to `https://<your site>/api/pay/webhook` for the
   `payment.captured` event, and put its secret in `RAZORPAY_WEBHOOK_SECRET`. It adds the
   reports even if the student's page closed before the payment was confirmed.
4. Pay for a pack with Razorpay's test UPI id, see the reports arrive, then switch to live keys.

Razorpay asks for a contact address, terms, a privacy policy and a refund policy on the site
before it turns live payments on: `/terms` and `/privacy` have them, and `VITE_CONTACT_EMAIL`
must be set. Read the refund paragraph in the terms and change it if you want another policy.

## Notes, invites and subjects

- **Personal note.** A student can add a short note to a report ("use a while loop"). It is
  written for them instead of coming from the shared cache, so it costs
  `LABFORGE_NOTE_EXTRA_COST` extra reports (default 1).
- **Invites.** Each student has a link. A classmate who signs up with it gets
  `LABFORGE_REFERRAL_WELCOME` report at once; the inviter gets `LABFORGE_REFERRAL_REWARD` when
  that classmate writes a first report, for up to `LABFORGE_REFERRAL_MAX` classmates.
- **Subjects.** Subject names students type are counted. Approve them under **Subjects** in
  `/admin` and they appear in everyone's subject list, with the code filled in.

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
  non-loopback connections. `GET /api/admin/status` with the `X-Admin-Token`
  header shows which.
- The image's app code is owned by root and read-only to the app user.
- Screenshotted pages can only reach LabForge's own throwaway static server
  (outbound requests go to a dead proxy). Keep `HTML_ALLOW_NETWORK=0`.
- Uploaded screenshots are re-encoded as PNG.
- File names from the model can't leave the work folder.

- Code the server wrote can be re-run with any input. Changed code (a
  student's own edits, or anything else a browser sends) has its own, smaller
  hourly limit, and changed shell scripts are never run.
- Programs run in throwaway folders under `LABFORGE_RUN_DIR` (the system temp
  folder), never inside a job folder, and the draft cache can live in Postgres
  where programs can't write to it.

For a public site, also do one of these:

1. **Recommended: a separate execution worker** (`EXEC_BACKEND=remote`). The
   web server sends each program to `apps/worker` on another machine, so
   student code never runs next to your API keys, the cache or other students'
   reports. See "Execution worker" below.
2. Run the container as in `docker-compose.yml`: unprivileged user, memory,
   CPU and process limits, `no-new-privileges`. The container is the boundary.
3. Set `EXEC_BACKEND=docker` on a host with Docker, so each program runs in
   its own container with `--network none`, `--cap-drop ALL`, 384 MB and one
   CPU. Build a Python image with the scientific libraries and set
   `EXEC_IMAGE_PYTHON` to it. (A worker can use this too:
   `WORKER_EXEC_BACKEND=docker`.)

## Execution worker

Any small VM works (Hetzner, DigitalOcean, Oracle Cloud's free ARM VM, a
spare machine behind Cloudflare Tunnel). Keep **no secrets** on it apart from
the worker token.

```bash
# on the worker machine
docker build -t labforge .
docker run -d --restart unless-stopped --name labforge-worker -p 8100:8100 \
  -e EXEC_WORKER_TOKEN=<random, 24+ characters> -e EXEC_ALLOW_NETWORK=0 \
  --memory 2g --cpus 2 --pids-limit 512 --security-opt no-new-privileges \
  labforge sh -c 'exec uvicorn apps.worker.main:app --host 0.0.0.0 --port 8100'
```

Then on the web server (Render) set:

```
EXEC_BACKEND=remote
EXEC_WORKER_URL=https://worker.example.com   # put HTTPS in front (Caddy or Cloudflare Tunnel)
EXEC_WORKER_TOKEN=<the same token>
```

`GET /api/admin/status` shows `exec_backend` and the runtimes the worker
reports. If the worker is unreachable, programs come back as "not run" and
students are asked for a screenshot; nothing runs on the web server.

For the strongest isolation on the worker, give it Docker and set
`WORKER_EXEC_BACKEND=docker` (one network-less container per program), or a
kernel that allows unprivileged user namespaces so `EXEC_ALLOW_NETWORK=0`
uses a private network namespace.

## Postgres

Set `LABFORGE_DATABASE_URL` (a free Neon database is enough; the old
`LABFORGE_LOG_DB_URL` also works). It holds the draft cache, rate limits and
the activity log, so a redeploy or restart on Render's wiped disk no longer
throws away every cached sheet and resets every limit. Tables are created on
first use.

## Token spend

`GET /api/admin/usage?days=7` with the header `X-Admin-Token: $LABFORGE_ADMIN_TOKEN` returns calls and
input, cached, output and thinking tokens per model. Typical numbers with
Gemini Flash: a new three-program sheet costs about 2k input and 2k output
tokens; an uploaded-before sheet costs nothing.

## Activity panel

Open `/admin` and enter `LABFORGE_ADMIN_TOKEN`. Each report shows the experiment, every
program's result with the reason it didn't run, feedback and content reports (🚩). By default
no names or UIDs are stored and IP addresses are kept only as a salted hash; set
`LABFORGE_LOG_PERSONAL=1` to keep names and UIDs (the privacy page then says so
automatically). With `LABFORGE_DATABASE_URL` the log survives restarts; without it the log
lives in `artifacts/activity.jsonl`. Rows older than `LABFORGE_LOG_DAYS` (14) are deleted, and a
student who deletes their report deletes its rows too.

## Ads (Google AdSense)

1. Get approved: AdSense wants your own domain (not `onrender.com`) with real
   content. The site has real pages for crawlers: `/guide`, `/faq`, `/about`,
   `/privacy` and `/terms`, each with its own title, plus `/robots.txt` and
   `/sitemap.xml`. Set `LABFORGE_PUBLIC_URL` to the domain, and build with
   `VITE_CONTACT_EMAIL` so the privacy page has a real contact address.
2. Create two display units (a 300x250 rectangle for the sidebar, a responsive
   horizontal unit under the page) and build with:

   ```bash
   VITE_ADSENSE_CLIENT=ca-pub-XXXXXXXXXXXXXXXX \
   VITE_ADSENSE_SLOT_RAIL=1111111111 \
   VITE_ADSENSE_SLOT_BENCH=2222222222 \
   docker compose up -d --build
   ```

3. Set `ADSENSE_CLIENT=ca-pub-XXXXXXXXXXXXXXXX` on the server: `/ads.txt` is
   served from it automatically.
4. In the EU/UK, AdSense requires a consent banner: enable Google's CMP in the
   AdSense dashboard (Privacy & messaging).

Ads sit in the sidebar and under the page, never between the student and the
download button.
