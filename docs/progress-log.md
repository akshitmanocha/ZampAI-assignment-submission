# Implementation progress

## 2026-11-10 — T-00 discovery and first implementation milestone

- Kickoff: approximately 13:08 IST. User explicitly authorized starting implementation, removing the candidate guide PDF from GitHub, and a Kaggle heartbeat.
- Existing checkout: documentation only; no AGENTS.md, application, manifests, tests, or pre-existing working-tree changes. All implementation backlog tasks initially missing.
- Preserved the guide outside the checkout for reference; removed it with an ordinary Git commit and pushed that deletion to `main`. Historical commits still contain it; no history rewrite requested or performed.
- Branch: `reconcile/main-build`, using the existing isolated checkout (no additional worktree).
- T-21 partial: Jupyter API reachable; a real execute_request received status=ok. Five-minute heartbeat running in this cloud instance, bounded to 12 hours, private credential/log outside Git. GPU count and training capabilities remain unverified. No fine-tune started.
- T-02 partial: FastAPI + React/Vite/TypeScript scaffold; frozen uv/npm lockfiles; multi-stage non-root Docker image; private PostgreSQL Compose service; loopback-only application publishing; Tesseract 5.5 installed in image. Authentication dependency selected: fastapi-users 15.0.5; database-backed revocable sessions remain to implement. All API routes currently deny anonymous access.
- Validation: production frontend type-check/build passed; four backend tests passed, including all-method anonymous gates and static serving. Docker build passed. Starlette emits an upstream httpx TestClient deprecation warning; tests execute successfully.
- T-01 blocked externally: user confirms Render account is not set up yet. No paid resources, signup, deployment, CI/CD, or messages created.
- Honest readiness: 503 until migrations, worker and blob storage exist. No invoice behavior or hosted acceptance has passed. T-03 and onward remain missing.
- Next work: persistent schema/Alembic plus auth/session setup, synthetic seed/fixtures, upload + durable worker + real extraction, then HP-01 end-to-end. See the ordered backlog in reconcile-design/05-CODEX-HANDOFF.md.

### Container and browser verification

- Corrected non-root source permissions in the Docker image after the first startup failed; rebuilt and restarted successfully.
- `docker compose exec -T db psql ... SELECT current_database(), version()` verified PostgreSQL 16.15.
- Container UID is 10001; application published only at 127.0.0.1:8000; DB has no published host port.
- Playwright Chromium verified desktop and 390px mobile views, live DB/OCR checks, no JavaScript page errors, and no horizontal mobile overflow. Screenshots retained outside Git at `/tmp/reconcile-browser/overview-{desktop,mobile}.png`.
- Live HTTP checks: `/health/live` 200; `/health/ready` 503 (intentionally incomplete application); `/api/invoices` 401 with session challenge.

## 2026-11-10 — SQL history and first measured ML experiments

User authorized implementation and requested plain-language updates. Existing branch was clean before changes.

### Database history

- Added initial Alembic migration and SQLAlchemy procurement/history models. This is a subset of the design schema, not completion of T-03.
- Added vendor-scoped duplicate candidate checks, exact-file detection, revision/normalized-identifier distinctions, approved balance aggregation, bounded historical candidate retrieval and TF-IDF ranking. Historical similarity is explicitly not authorization.
- Added internal approval transaction with locks, current vendor/PO/state checks, exact-price initial policy, aggregated line quantities, and once-only allocations. It trusts a validated recommendation; complete decision validation/auth/audit remains outstanding. No public API access was opened.
- `make test`: 6 passed; 16 PostgreSQL tests skipped locally without explicit connection configuration.
- `docker compose exec -T app python < backend/tests/test_history_postgres.py`: **16 actual PostgreSQL tests passed**, including migration repeatability/schema agreement, concurrent competing approvals, repeated approval, duplicates, pending/rejected history, aggregate overage and historical suggestions.
- Built Docker image and ran fictional isolated-schema demo: before remaining 600; approval left 0; repeat returned already_approved and left 0. Data survives container restarts; demo seed is non-destructive and repeatable.

### Kaggle/ML

- Verified two Tesla T4 GPUs, CUDA available, 20.9 GB free disk at probe. Used one GPU.
- Generated 960 labelled synthetic description pairs for 80 products in 20 categories; split by category/product: 576 train, 144 validation, 96 calibration, 144 test. Catalog identity supplies labels; no independent full human label audit yet. Hashes and split integrity tests saved.
- Ran lexical TF-IDF, frozen MiniLM, and actual three-epoch BCE fine-tuning. Selected earliest best validation checkpoint; calibrated threshold separately. Model revision and observed package versions saved.
- Test correct: B0 100/144; frozen MiniLM 127/144; fine-tuned 138/144. Fine-tuned confusion counts: TN72 FP0 FN6 TP66. This is pair classification on a small simple synthetic set, not invoice accuracy or approval safety. Test data was not used to tune after results.
- Exported selected weights/tokenizer/reports as an 83,440,366-byte bundle to `/workspace/reconcile-artifacts/selected-model.tar.gz`, outside Git. Bundle SHA-256 and all eight contained file digests verified. Last optimizer checkpoint remains remote and is not exported/verified for resume.
- Rechecked selected model on Kaggle CPU: identical binary outputs for all 144 pairs; max GPU/CPU logit difference 0.0000043. Warm scoring batch 0.517 s with two CPU threads; excludes loading, OCR/API/DB and is not deployment-host latency.
- Weights are **not adopted into application serving**. Tougher independent audits/evaluation and deployment-host checks remain required.

### Public dataset OCR diagnostic

- Streamed first 12 clean InvoiceOCR-Synth images from pinned Hugging Face revision and ran Tesseract 5.3.4 in Kaggle. This is raw OCR label-text recovery, not structured extraction or PDF-to-decision acceptance.
- Recovered supplier names 12/12, invoice numbers 8/8 eligible, total number somewhere in text 12/12, PO number 0/3.
- Visually inspected one failed PO example: labelled PO-5678 is not visible in the rendered freelancer invoice. Saved audit finding; preserve original scores and do not claim this is an OCR failure. Other two PO failures not manually audited. Publisher label observability needs further audit.
- Raw predictions, metadata, metrics and readable limitations saved under ml/results and ml/README.md. Dashboard shows the saved matching experiment with explicit synthetic/non-approval scope.

Next: complete persistent staff authentication and full run/job/evidence schema, then real PDF-to-saved-decision flow; expand independent image-label audits and tougher matching scenarios before promoting any model. Deployment still awaits Render account setup.

Final checks: rebuilt app image after dependency/UI changes; desktop/mobile browser smoke passed and saved 95.8% synthetic pair result is visible. API remains fail-closed and readiness intentionally 503 for the incomplete pipeline. Added observed ML environment versions and a thin, unexecuted handoff notebook; the actual experiment ran through the checked-in Python training script. No connection secret in candidate commit content; no weights committed.

## 2026-11-10 — Top-k review fallback

User requested top-k retrieval and human review when model reliability is insufficient. Added standalone conservative match/review policy, defaulting all model matches to review. Human choice validates eligibility/evidence/conflicts/version and returns an attestation requiring later rule revalidation; it does not itself persist a review or approve an invoice. None-correct remains unresolved. Public API remains closed; review screen/persistence are not implemented.

Ran actual frozen `sentence-transformers/all-MiniLM-L6-v2` embedding retrieval and selected cross-encoder reranking on Kaggle: correct item found at top1/top3/top5 for 36/36 simple descriptions against 80 catalog products. This reused previously inspected pilot test families and includes only matchable queries. It is a diagnostic, not a new blind benchmark or a guarantee of 100% final correctness. No human review performed. Model revision, counts, raw predictions, and limitations saved under ml/results/retrieval.

`make test`: 23 passed including 17 new match/review checks, 16 database tests skipped without explicit local connection configuration (the database suite passed separately in the previous milestone). Tests cover ambiguous scores, missing evidence, explicit conflicts, invalid values, ineligible choices, stale review, second-choice selection and none-correct. No further weights trained or test-guided threshold tuning in this step.
