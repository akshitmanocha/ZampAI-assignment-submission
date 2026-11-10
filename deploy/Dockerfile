# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS web
WORKDIR /build/web
COPY web/package*.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-trixie AS dependencies
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; export PIP_CERT=/run/secrets/proxy_ca; fi; \
    apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir uv==0.9.9 && useradd --create-home --uid 10001 reconcile
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    uv sync --project backend --frozen --no-dev --no-install-project && chmod -R a+rX /app
# Model provisioning is cached independently from business/application source.
COPY --chmod=755 backend/reconcile/model_setup.py backend/reconcile/retrieval.py backend/reconcile/settings.py /bootstrap/reconcile/
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    PYTHONPATH=/bootstrap /app/backend/.venv/bin/python -m reconcile.model_setup --directory /opt/reconcile/minilm
COPY --chmod=755 backend/reconcile/ocr_models.py /bootstrap/reconcile/
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    PYTHONPATH=/bootstrap /app/backend/.venv/bin/python -m reconcile.ocr_models --directory /opt/reconcile/ppocr-v5 --profile mobile

FROM dependencies AS runtime
COPY --chmod=755 backend/reconcile /app/backend/reconcile
COPY --chmod=755 backend/alembic.ini /app/backend/alembic.ini
COPY --chmod=755 backend/migrations /app/backend/migrations
COPY --from=web /build/web/dist /app/web/dist
USER reconcile
ENV MINILM_DIR="/opt/reconcile/minilm" TOKENIZERS_PARALLELISM="false" OMP_NUM_THREADS="2"
ENV OCR_ENGINE="paddle" OCR_PROFILE="mobile" OCR_MODEL_DIR="/opt/reconcile/ppocr-v5"
ENV PYTHONPATH="/app/backend" PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn reconcile.app:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM runtime AS test
USER root
RUN --mount=type=secret,id=proxy_ca \
    if [ -s /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    uv sync --project backend --frozen --group dev && chmod -R a+rX /app/backend/.venv
USER reconcile
