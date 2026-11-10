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
