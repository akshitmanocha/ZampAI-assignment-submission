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

.PHONY: local models integration-test
local:
	python scripts/bootstrap_local.py
models:
	UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend python -m reconcile.model_setup
	UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend python -m reconcile.ocr_models --directory "$${OCR_MODEL_DIR:-../reconcile-artifacts/ppocr-v5}" --profile mobile
integration-test:
	docker compose --profile test build test
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile test run --rm test

.PHONY: browser-test
browser-test:
	docker compose --profile test build test
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile test up -d --force-recreate browser-test
	cd web && npm exec -- playwright test; result=$$?; docker compose --profile test stop browser-test; exit $$result

# Primary external invoice evaluation (business-rule fixtures remain regressions).
.PHONY: invoice-data evaluate
invoice-data:
	PYTHONPATH=backend UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend python ml/indian_gst_dataset.py
	python ml/audit_indian_gst_splits.py
evaluate:
	python scripts/evaluate_invoices.py

.PHONY: submission-edge-test
submission-edge-test:
	UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/reconcile-uv-cache} uv run --project backend python scripts/evaluate_submission_edges.py
