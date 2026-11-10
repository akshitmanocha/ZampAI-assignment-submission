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

WORKFLOW_OUT ?= /tmp/reconcile-workflow-validation
.PHONY: workflow-data-check workflow-test workflow-db-test
workflow-data-check:
	PYTHONPATH=backend UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend python ml/check_workflow_data.py
workflow-test: workflow-data-check
	PYTHONPATH=backend UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend python ml/render_workflows.py --out $(WORKFLOW_OUT)/pdfs
	PYTHONPATH=backend UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend python ml/evaluate_workflows.py --pdfs $(WORKFLOW_OUT)/pdfs --output $(WORKFLOW_OUT)/results --require-all
workflow-db-test:
	PYTHONPATH=backend UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend python scripts/run_workflow_database.py --output $(WORKFLOW_OUT)/database.json
