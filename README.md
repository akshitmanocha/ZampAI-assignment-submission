# Reconcile

A working local invoice-review application: upload a real PDF, watch processing, inspect source evidence, resolve uncertain matches, and approve against the current purchase-order balance. Reconcile records approvals and allocations; it never executes payment.

## Start locally

Requires Docker with Compose and Python 3.12. The first build downloads the public, pinned MiniLM model; invoice processing then runs locally without an API key.

```sh
make local
```

Open **http://127.0.0.1:8000**. Generated staff credentials are saved outside Git at `/tmp/reconcile-private/local-accounts.json`. The default stack binds to loopback. `make local` preserves existing documents, approvals and the database volume. Sign in as the approver for the complete workflow; the clerk can review but cannot approve.

The workspace includes downloadable fictional PDFs covering packaging, material conflicts, hidden price errors, competing partial invoices, semantic matching and a genuine scanned PDF. Their results depend on the current company ledger. Original PDFs, extracted readings, corrections, runs, versioned decisions and audit records persist in PostgreSQL.

## What runs

- Argon2id staff passwords, revocable 12-hour sessions, role checks, CSRF protection and database-backed login/upload limits.
- Durable processing queue, real stage events, retries, worker heartbeats and fenced recovery after worker death.
- Native PDF reading or PP-OCRv5 English mobile OCR (about 3.1M stored model values) in a bounded subprocess; source-page previews and original-coordinate field highlights.
- Pinned `all-MiniLM-L6-v2` embeddings on CPU retrieve top product candidates after supplier/PO filtering. Similarity alone never confirms a match.
- Decimal business checks: supplier/order eligibility, duplicates, specifications, explicit packaging conversions, line prices, arithmetic, uniform separated tax and cumulative quantity/value balances.
- Human corrections and candidate choices preserve original readings and trigger a new validation run.
- Approval rechecks locked, current records. Repeated approval has one effect; competing invoices cannot consume the same remaining quantity.
- Searchable invoice history, review filters, order ledger, saved evaluation reports and operational CLI commands.

## Verify

```sh
make install                  # local Python/frontend development dependencies
make models                   # CPU model for commands outside Docker
make test                     # unit tests; DB cases skip without explicit test URLs
make integration-test         # all tests, real PostgreSQL, private disposable schemas
# Install Chromium once for browser checks:
web/node_modules/.bin/playwright install chromium
make browser-test             # isolated company/app on loopback port 18000; cleaned afterward
```

Use `PLAYWRIGHT_BROWSERS_PATH` if Chromium is installed in a custom location. Browser tests exercise the actual UI, PDF processing, human correction, MiniLM selection, approval, source evidence, search, ledger, mobile layout and logout, with accessibility checks.

See [local application and operations](docs/local-application.md), [demo walkthrough](docs/local-demo.md), and [test evidence](ml/results/local-application/). Cloud deployment, public access and hiring submission are intentionally excluded from this milestone. No CI/CD is configured.

## Evaluation and limits

Our primary invoice-reading benchmark is now [Divya52/indian-gst-invoices](https://huggingface.co/datasets/Divya52/indian-gst-invoices), pinned to an immutable source revision. We evaluate every one of its **197 official test invoices**; 24 adversarial and 40 Hindi/Kannada documents form separate robustness suites. Publisher-supplied labels remain unchanged and never enter the reader. This replaces InvoiceOCR-Synth as the primary OCR benchmark; earlier results remain historical evidence.

The [small-model OCR upgrade](docs/ocr-upgrade.md) compares the compact reader with Tesseract, a larger PP-OCR model and two GPU vision models below one billion parameters. GST columns and receipt rows now have source-based parsing. Development uses 24 training images, 60 model-selection images and 130 separate calibration images. No model was fine-tuned. The official test is a disclosed re-score of an already inspected test, not a new blind benchmark. OCR confidence remains a heuristic; high scores can still be wrong.

```sh
make invoice-data             # original images/metadata outside Git; verify frozen hashes
docker compose --profile test build test
make evaluate                 # actual local PDF/OCR reader; no training or model API calls
```

See [the Indian GST evaluation report](docs/indian-gst-evaluation.md), [frozen source manifest](ml/data/indian-gst-v1/), and [saved predictions and metrics](ml/results/indian-gst/). These labels measure extracted invoice fields. They provide no verified purchase-order ledger, catalog-match identities or approval history, so they cannot establish accept/reject accuracy or invoice automation.

The earlier [25-scenario edge-case suite](docs/workflow-validation.md) passed 100 PDF checks and three database traces. These are author-known synthetic acceptance tests, not 100 independent invoices or guaranteed future accuracy. Its labels were authored before evaluation; no LLM generated the correct answers.

The live application now connects matching, review, persistence and approval, with additional source-quality and tax checks. [ML experiments](ml/README.md) remain separate from application tests. The trained cross-encoder experiment is not a live approval policy. The CPU embedding implementation is checked against the saved GPU diagnostic; semantic identity without explicit evidence still requires human confirmation.

This release handles English/INR, one invoice per PO, individual-item orders and evidenced box conversions. Mixed/inclusive tax, credit notes, bundles and extra charges remain manual-review cases. OCR engine scores and embedding similarities are not correctness probabilities. Approximately 90% automation on representative unseen invoices has **not** been established; independent label audit and real-data evaluation remain necessary before production claims.

The candidate guide PDF is intentionally absent from the repository. The optional Nemotron extractor remains available for explicit experiments; the application makes no external document/model calls during processing. Existing Kaggle and OCR reports are retained as historical evidence.
