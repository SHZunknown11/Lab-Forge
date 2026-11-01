# LabForge: web app + everything student programs need to run, in one image.
# Build:  docker build -t labforge .
# Run:    docker compose up -d      (see docker-compose.yml and docs/deployment.md)

FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY apps/frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY apps/frontend/ ./
ARG VITE_ADSENSE_CLIENT=""
ARG VITE_ADSENSE_SLOT_RAIL=""
ARG VITE_ADSENSE_SLOT_BENCH=""
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CHROME_PATH=/usr/bin/chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jdk-headless gcc g++ chromium fonts-dejavu-core fonts-liberation curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 labforge
WORKDIR /app
COPY pyproject.toml README.md main.py ./
COPY core ./core
COPY apps/api ./apps/api
RUN pip install --no-cache-dir -e ".[server]"
COPY templates ./templates
COPY config ./config
COPY scripts ./scripts
COPY --from=web /web/dist ./apps/frontend/dist
RUN python scripts/setup_runtime.py --mongo && chown -R labforge /app
USER labforge
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
