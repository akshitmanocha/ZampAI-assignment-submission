.PHONY: install test build dev
install:
	UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv sync --project backend --frozen
	npm ci --prefix web --cache /tmp/reconcile-npm-cache
test:
	UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend pytest -q backend/tests
build:
	npm run build --prefix web
dev:
	UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend uvicorn reconcile.app:app --host 127.0.0.1 --port 8000 --reload
