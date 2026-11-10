# Reconcile

Invoice PDF → evidence-backed accounts-payable recommendation. Built against the contracts in `reconcile-design/03-CONTRACTS.md`.

## Current milestone

The runnable application foundation is implemented: FastAPI serves the React/TypeScript build, PostgreSQL runs on a private Compose network, Tesseract is installed in the non-root runtime image, and all API paths fail closed. The overview displays actual service checks rather than simulated invoice data.

**New:** PostgreSQL history schema/migration, duplicate checks, remaining-balance queries, historical description ranking, and an internal transaction-safe approval service with a repeatable fictional demo. A real GPU matching pilot and Hugging Face OCR smoke evaluation now have saved results. See [history checks](docs/history-checks.md) and [experiment report](ml/README.md).

**Not implemented yet:** staff sign-in/session persistence, full pipeline schema, live PDF upload-to-decision processing, and approval/review screens. The trained model is not deployed into the application. `/health/ready` deliberately returns 503 until these required components exist. This is not yet a working invoice-reconciliation product.

## Development

Requires Python 3.12, uv, Node 22.12+ (or Node 24), npm, and Docker with Compose.

```sh
make install
make build
make test
make dev
```

`make dev` binds the API and built frontend to loopback port 8000. Build the frontend again after editing it. For frontend-only iteration use `npm --prefix web run dev`; API integration uses the built same-origin app.

## Container workflow

Create `.env` using `.env.example` as a reference and set a unique `POSTGRES_PASSWORD`. Do not commit it. No database port is published.

```sh
docker compose up --build -d
curl --fail http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
make test
```

Compose binds the application to `127.0.0.1:8000`. For environments with an HTTPS inspection proxy, set `RECONCILE_BUILD_CA` to the supplied combined CA bundle; Compose mounts it as a build secret. TLS verification remains enabled. Stop with `docker compose down`; the Postgres volume is retained.

No CI/CD or automatic deployment is configured. Render deployment is pending account setup and completion of the application.

## Kaggle heartbeat

`scripts/kaggle_heartbeat.py` reads an authenticated proxy URL from a private file outside Git and executes a harmless cell in an **existing idle** Python kernel every five minutes. It never creates a kernel or interrupts running work. Errors log their type only. The process stops after 12 hours; it cannot extend the platform's hard session lifetime, and activity-clock reset is not guaranteed.

Use the backend development virtualenv to run the script, with `--secret-file` pointing to the private file and `--log` pointing to an external log. `--once` verifies one execution. Live processes do not survive environment shutdown. Keep the proxy credential out of screenshots, commands, logs, and commits.

The candidate guide PDF is intentionally absent from the current repository tree. The design package remains the implementation reference. No Git history was rewritten.

## OCR and field extraction

The local CLI reads real native/scanned PDFs into source-linked fields and item rows:

```sh
uv run --project backend python -m reconcile.extract_cli /path/invoice.pdf --output /path/new-output.json
```

It does not call an external model. [OCR results](docs/ocr-results.md) document the public-data comparison with the optional free Nemotron vision adapter, including failures, ambiguous fields, label visibility, cost and remaining limitations. Provider keys stay outside Git. Full upload-to-decision integration is still pending.
