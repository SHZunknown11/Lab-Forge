# LabForge: the web app plus everything student programs need, in one image.
#   docker build -t labforge .
#   docker run -p 7860:7860 --env-file .env labforge
# Works as-is on Render (render.yaml), Hugging Face Spaces (port 7860, user 1000), Koyeb, Fly or any VPS.

# ── frontend ─────────────────────────────────────────────────────
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY apps/frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY apps/frontend/ ./
ARG VITE_ADSENSE_CLIENT=""
ARG VITE_ADSENSE_SLOT_RAIL=""
ARG VITE_ADSENSE_SLOT_BENCH=""
RUN npm run build

# ── app ──────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Java, C/C++, Chromium (page screenshots), LibreOffice (PDF), fonts, Node 22.
# util-linux gives prlimit/unshare and iproute2 brings loopback up in the run sandbox.
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jdk-headless gcc g++ libc6-dev \
        chromium libreoffice-writer-nogui \
        fonts-dejavu-core fonts-liberation2 fonts-crosextra-carlito fonts-crosextra-caladea \
        util-linux iproute2 curl libcurl4 ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc/* /usr/share/man/*

WORKDIR /app
COPY pyproject.toml README.md main.py ./
COPY core ./core
COPY apps/api ./apps/api
RUN pip install ".[server]"

# Libraries student programs may import (numpy, matplotlib, OpenCV, scikit-image, pandas;
# React, Express, Mongoose, ...), Spring Boot + H2 jars and a MongoDB server binary, all under /app/.runtime.
COPY scripts ./scripts
RUN python scripts/setup_runtime.py --mongo --spring \
    && MPLCONFIGDIR=/app/.runtime/mplconfig .runtime/python/bin/python -c "import matplotlib.pyplot" \
    && rm -rf /root/.npm /root/.cache

COPY templates ./templates
COPY config/subjects.json config/student_profile.example.json ./config/
COPY --from=web /web/dist ./apps/frontend/dist

# Hugging Face runs containers as uid 1000. The app code stays root-owned (read-only for
# the programs it runs); only scratch space is writable.
RUN useradd --create-home --uid 1000 user \
    && mkdir -p /app/artifacts \
    && chown -R user /app/artifacts /app/.runtime/mplconfig
USER user
ENV HOME=/home/user \
    PORT=7860 \
    EXEC_BACKEND=local \
    EXEC_ALLOW_NETWORK=0 \
    HTML_ALLOW_NETWORK=0 \
    CHROME_PATH=/usr/bin/chromium \
    CHROME_NO_SANDBOX=1 \
    PDF_BACKEND=auto \
    LABFORGE_TRUST_PROXY=1 \
    LABFORGE_JOB_TTL_HOURS=6 \
    LABFORGE_MAX_PARALLEL_RUNS=3 \
    EXEC_JAVA_OPTS="-XX:+UseSerialGC -XX:TieredStopAtLevel=1"

EXPOSE 7860
HEALTHCHECK --interval=60s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"7860\")}/api/health',timeout=4)"
# exec: uvicorn becomes PID 1 and marks itself non-dumpable (see apps/api/main.py).
CMD ["sh", "-c", "exec uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-7860} --timeout-keep-alive 30"]
