# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS web
WORKDIR /build/web
COPY web/package*.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-trixie
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock /app/backend/
COPY backend/reconcile /app/backend/reconcile
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir uv==0.9.9 && \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    uv sync --project backend --frozen --no-dev
COPY --from=web /build/web/dist /app/web/dist
RUN chmod -R a+rX /app && useradd --create-home --uid 10001 reconcile
USER reconcile
ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn reconcile.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
