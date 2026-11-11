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

## 2026-11-10 — Three-bucket uncertainty policy

User requested accept/human review/reject with minimum review and 100% precision. Added recommendation router requiring verified mandatory checks and a confirmed match for acceptance, evidenced blockers for rejection, and review for missing/unverified/uncertain evidence. Low match score alone never rejects an invoice. Router is not yet integrated into a completed PDF/API flow and never moves money/balances.

Added threshold-selection and uncertainty diagnostics. Selected maximum automatic-match coverage with zero observed validation false matches, then kept the threshold fixed for calibration/existing-test scoring. Observed: validation 72/144 auto-matches, calibration 48/96, test 72/144; zero wrong automatic matches, 50% pair coverage. This is a matching diagnostic on previously inspected synthetic splits, not invoice bucket precision or independent final evidence. Two calibration categories cannot establish production safety. Default model automation remains disabled; zero future error not claimed.

`make test`: 47 passed, 16 PostgreSQL tests skipped locally (separately passed in prior milestone). New tests cover every mandatory-check omission, accept/no-money behavior, confirmed blockers, unverified failures, unknown matches, contradictory aggregate input and risk-bound/threshold behavior. Saved report explains precision separately for accept and reject, abstention, group dependence, and remaining required evaluation. No additional training or invoice-level performance claim.

## 2026-11-10 — Approximately 90% coverage experiment

User changed the target to highest accuracy around 90% automation, then OCR. Implemented validation-selected two-sided pair abstention and a score-only fixed-budget comparison. Negative pair decisions are candidate elimination, never automatic invoice rejection.

Fixed thresholds reached 90.3% validation coverage but 82.6% on the old test and 60.6% on a 720-pair challenge. Preserved those results. Created/froze the challenge before first scoring: 10 new families, 720 balanced fictional description pairs, explicit materials/specifications. No OCR noise or independent human audit.

At 90% score-ranked automatic coverage on challenge, original epoch-1 checkpoint reached 94.0% automatic accuracy. Compared saved epoch-1 and epoch-3 using validation auto accuracy and validation BCE only, selected epoch 3. It reached 94.6% (613 correct/648 automatic), with 72 pairs abstained; 2 false same-product and 33 false different-product. Challenge was already inspected, so later results are development evidence, not blind confirmation. Old easy test reached 100% among 130 automatic pairs; do not substitute that for harder result.

Saved policy, all initial challenge scores, raw reports and reproduction script. Exported selected epoch-3 weights separately outside Git with archive/contained checksum verification. No production policy enabled and no 90% invoice automation claim. `make test`: 51 passed, 16 real-DB tests skipped locally (previous dedicated DB run passed). Boundary/invalid-score/score-only budget selection tests added.

Matching milestone findings documented in docs/coverage90.md. Next: OCR label observability audit and structured extraction/native-vs-scan evaluation. Missing evidence must continue to override any nominal 10% review budget.

## 2026-11-10 — OCR stage started after matching comparison

Implemented actual native/scanned PDF text reader with page-word bounding boxes, file/page limits, explicit OCR errors, and unreadable-page warnings. It uses native extraction on text-only populated pages, renders sparse/image-bearing pages for Tesseract, and preserves engine confidence without presenting it as correctness probability. Not yet a structured invoice parser, worker-isolated upload path or end-to-end application.

Four new functional tests passed, including actual Tesseract on an image-only PDF. `make test`: 55 passed, 16 database tests skipped locally; native/scanned paths genuinely executed. Next OCR work: public-dataset label observability audit, noisy/mixed-page benchmark, structured fields/rows, and source-grounded accuracy metrics. See docs/ocr-progress.md for limitations.

## 2026-11-10 — Structured OCR, source-linked fields and optional vision comparison

Continued OCR work as requested. Added shared text-layer types, geometry/label-based invoice parser, private-output local extraction CLI, optional schema-validated vision proposals, and recovery merging that preserves original readings/conflicts. Missing/ambiguous fields are not filled from PO records or labels. Decimal strings preserved. Arithmetic contradictions produce warnings rather than repaired values. Raw OCR and vision proposals are not automatically verified evidence.

Prepared pinned InvoiceOCR-Synth sample: 24 independent documents across six templates, all three quality variants (72 images), grouped 12-document development/holdout split. Skipped first 100 source records to avoid earlier smoke examples. Local baseline improved on development only; x2-geometry-baseline-0.4 frozen before 36-image holdout. Real PDF ingestion and Tesseract executed; no technical failures.

User explicitly provided a free OpenRouter key/model and authorized the optional public-data comparison. Key stored only outside Git, not echoed. Verified specified model exists with zero catalog prices. Used it as extractor, never as evaluation judge. One initial request failed coordinate schema validation (model emitted 0..1000 boxes); adapted declared coordinate convention using development only. Then 16 valid development and 16 valid holdout calls completed. All 33 calls with usage evidence reported zero cost. No paid fallback, private invoices, or additional credentials configured.

On identical 16 holdout images, Nemotron proposals vs local: supplier 16/16 vs 2/16; labelled invoice number 9/9 vs 7/9; date 15/16 vs 8/16; currency 12/16 both; grand total 16/16 vs 10/16. Vision also proposed three invoice IDs where labels are null (ticket/receipt references), so invoice-number proposal precision is 75%, not 100%. PO reference 0/1 for both remains unresolved. Description/qty/amount rows 27/28 vs 17/28; full rows including unit price 20/28 vs 17/28. Preserved all outputs and strict scores. Manually confirmed a development receipt never prints separate unit prices; labels include them. No label edits or LLM-generated gold.

Metrics compare exact same images, retain correlated variant counts, distinguish invoice-template subset, source observability, incomplete fields and model-proposed boxes. Added strict identifier and exact-description metric checks. Model prompt/schema/usage and source/code hashes saved. Documented remaining unsupported/reference-type cases; no invoice automation/approval claim.

Validation: `make test` 91 passed, 16 database tests skipped locally (prior dedicated PostgreSQL run passed). Native and real scanned PDF paths executed. Rebuilt Docker image, imported OCR/vision modules in non-root container and verified native invoice extraction there. Browser desktop/mobile checks passed; API stays anonymous-401, readiness stays intentionally 503 pending full pipeline. See docs/ocr-results.md for primary report and next steps.

Final OCR regression: encrypted PDFs are classified as PDF_ENCRYPTED even when pdfplumber wraps the password exception; initially failing regression fixed and full 91-test suite passed. Free-model comparison processes completed; no further provider requests running.

## 2026-11-10 — Frozen workflow edge-case validation

Implemented 25 authored validation cases in 15 groups: four main edge families plus duplicate/vendor/status/tax/tolerance/aggregation regressions and three stateful approvals. Curated inputs and explicit oracles before running the production validator; separate Fraction audit, no engine/LLM-generated expected outcomes. Frozen manifest hash remained 157ab0ed9a8fd142259e52e4f6c85300a67f4ac2d676fcd27d7daebef5f6a309 throughout debugging. All cases are validation, author-known, with no independent human audit or blind-test claim.

Added bounded source-field normalization, exact printed-SKU/explicit-attribute procurement validator, SQL company snapshot reader, neutral deterministic native/scanned rendering, strict oracle/PDF evaluation, real PostgreSQL traces, reproducibility checks, nonzero exit on failed/incomplete runs, and human-readable PDF/report ZIP. Expectations and guide PDF remain outside runtime; application API stays closed.

Found/fixed real errors: tilted rows lost items; empty extraction was incorrectly treated as arithmetic failure; uncertain later rows could hide a known failure; absent invoice IDs could steal a PO reference; alphabetic IDs were dropped. Added regressions. Scanned-PDF timestamp nondeterminism fixed. Original failed outputs retained, without altering labels.

Final: 25/25 oracle-input initial recommendations and 100/100 case/PDF assignments pass all current assertions; 68 distinct PDF byte sequences, 24 unique context/action scenarios. Coverage 84% automatic/16% correct review on this deliberately enriched set, 83.3% deduplicated; not 90% live automation or future 100% precision. Cases verify exact reasons, normalized values, both offsetting price errors, extracted fields and no recommendation-side balance mutation.

Three actual PostgreSQL traces pass using parsed native PDFs: sequential stale detection, repeat/no extra effect, concurrent approvals/no overspending; post-conflict recheck returns rejection. Fresh disposable schemas and recorded source hashes/version; existing records preserved. Full ordinary suite: 131 passed, 16 existing PostgreSQL tests skipped locally; three scenario database traces executed separately. Browser report preview and PDF links checked.

Limits: deterministic SKU/attribute baseline only, not trained MiniLM/Nemotron; controlled layouts/mild corruption; no browser upload/jobs/review persistence. Approval tolerance-policy alignment remains before enabling tolerant-price recommendations through live approval. See docs/workflow-validation.md. No new external API calls, training, publication or deployment.

## 2026-11-10 — Complete local application, excluding cloud deployment

User authorised completion of the remaining project except cloud deployment. Implemented persistent staff authentication/roles, immutable PDF storage, additive application migration, durable leased/fenced processing, bounded OCR subprocess, actual live stage events, CPU MiniLM retrieval, source-linked page previews, human corrections/attestations, decision/run history, duplicate links, revalidation, current-record approval, matching tolerance policies and cumulative quantity/value guards. React now exposes the complete workflow, searchable history, review filters, order ledger and contextual benchmark reports.

Added separated uniform-rate tax verification and source-quality abstention. Missing rates/classifications remain review; source rates are not guessed from PO prices. Low OCR engine scores flag readings without erasing original values. Percentages beside money no longer create false amount candidates. Existing author-known validation labels are unchanged. Optional Nemotron and the trained cross-encoder remain experiments, not live approval policies; no provider calls or retraining were made.

Local bootstrap provisions unique passwords outside Git and preserves existing records. Added non-destructive company-master import and operational verification/latency commands. Tests use disposable PostgreSQL schemas; browser tests use a separate company/app and never reset the ordinary company ledger. Existing database volume and historical reports retained. Docker cache exhausted disk during iteration; only unused cache/dangling images were removed, freeing space. Model provisioning is now cached separately from application source. No environment publication, cloud deployment or external messages.

Final evidence and exact counts are recorded under ml/results/local-application after the final regression run. See docs/local-application.md for architecture, operations and supported scope; docs/local-demo.md for the live demo narrative. Controlled acceptance tests and CPU/GPU parity are development evidence; independent human label audit and real-world automation/accuracy remain unproven.

Final verification: 179 tests passed with real PostgreSQL (zero skipped in that run); ordinary host run 143 passed / 36 DB tests skipped without test URLs. Browser journey passed, including source highlights, approval, pack correction, semantic choice, ledger/search, mobile and logout. Axe found zero violations in the tested login and mobile workspace. Frozen 25-oracle/100-PDF/three-stateful regressions pass on the current code. CPU embeddings reproduce all 36 previous GPU top-1 results; maximum reference cosine difference 4.2e-7.

Actual production Compose containers (UID 10001, read-only root filesystem) processed additional native/scanned PDFs, retained identical input bytes and previews, and left balances unchanged. An initial randomized scanned reference was read incompletely; the low-score gate correctly withheld it and routed to review. Preserved that probe, visually checked the original page, recorded an explicitly agent-authored correction, and verified version 2 accepts while the original extraction remains unchanged. Subsequent smoke tests explicitly distinguish raw OCR from simulated reviewer corrections. No independent human audit or real-world accuracy claim.

## 2026-11-10 — Replace primary invoice benchmark with Indian GST

User requested the Indian dataset as the primary evaluation source. Pinned Divya52/indian-gst-invoices at fece40b9a96ac3949934fc05c714853a5283d730 (CC BY 4.0). Froze all 197 source test invoices plus separate 24 adversarial/40 regional suites before scoring. The loader's train split contains all 2,000 main records, so selection uses the publisher's split column. Original images/metadata stay outside Git; record, image and original label-string hashes are checked before every run. No labels were rewritten or generated by Nemotron.

Added reproducible data preparation, source split audit, production-child extraction evaluation, exact Decimal/identifier scoring, description-only row alignment, raw-versus-source-verified results, missing/unimplemented target reporting, quality/layout slices and default make evaluate. Primary registry and README now point to Indian GST. Old InvoiceOCR-Synth results are historical; authored business-rule fixtures and matching experiments remain separately labelled because the new invoice images have no verified PO/approval or catalog-match truth.

Diagnosed two runtime problems without fitting the field parser to test labels: PID-1 launcher refusal (Compose test now has init), and Tesseract oversubscription despite OMP_NUM_THREADS=1. A preselected validation image timed out after 30.75 seconds without OMP_THREAD_LIMIT and completed in 3.60 seconds with a limit of one. Stopped/preserved the partial run and restarted the full baseline with that production runtime bound; parser, OCR mode, image wrapping, source-quality policy and labels stayed unchanged. Diagnostic hashes and validation probe are retained alongside the completed baseline. Timing is not a portable performance claim.

All 191 tests pass with real PostgreSQL after the runtime repair (zero skips, 84.42 seconds). A prior concurrent run had 188 passes/two worker wait deadline failures; both the loaded failure and isolated final pass are recorded, without treating test timings as a controlled comparison. Frontend TypeScript/build checks pass. Exact dataset results and browser evidence are recorded in ml/results/indian-gst and docs/indian-gst-evaluation.md.

No new training or external model calls, cloud deployment, environment publication, or manufactured approval/retrieval accuracy. Publisher labels have not received an independent human audit; source splits share the same 25 product descriptions, so this is not an unseen-product-family test.

Completed primary baseline: 350/985 core header values correct (35.5% recall); 350/419 proposed headers correct (83.5% conditional precision). Source gate: 328/985 correct, 328/381 proposal precision (86.1%); 53 incorrect retained proposals. No predicted item rows; 0/769 complete rows, 0/197 documents with all five core headers. All 261 examples processed without technical failure. Main quality recall: clean 54.0%, scan 48.4%, photo 14.0%. These failures expose missing GST header/table support; no parser tuning was performed on the scored test. Future development must use train/validation and disclose test reuse.

Final browser journey passes in 18.1 seconds, including the primary Indian GST benchmark card, actual PDF processing, staff review, MiniLM selection and approval. Axe reports zero violations in the scanned login/mobile workspace views; this is not a full accessibility certification. Manifest/reader hashes and all 261 unique prediction records were checked; no technical failures in the completed dataset run.

## 2026-11-11 — Small-model OCR and GST extraction upgrade

User requested stronger OCR below one billion parameters. Compared Tesseract, PP-OCRv5 server, PP-OCRv5 English mobile, Granite Docling and PaddleOCR-VL-1.6 using frozen validation selections. Verified actual loaded GPU-model sizes and pinned ONNX assets. Selected the compact English mobile detector/recognizer: 3,113,414 stored initializer values including buffers, 12,691,927 weight bytes; CPU inference, no API key, no fine-tuning. Model weights remain outside Git.

Frozen 24 source-training images for parser development, 60 validation images for selection and 130 separate validation images for confidence diagnosis. Labels remain unmodified publisher JSON and never enter OCR/model prompts. Native PDFs retain the text path. Image pages use the new reader in the credential-isolated bounded child. Added logical deskew coordinates with separate original-page evidence rectangles, GST net/tax columns, receipt rows, seller/buyer separation and explicit taxable-total anchors. Ambiguous dates stay unresolved; BOX never invents a pack size or a missing printed amount.

GPU runtime probes found an API mismatch, missing explicit KV cache and Granite FP16 numerical degeneration on T4. Corrected inference uses native pinned models, explicit KV cache, FP32 Granite and FP16 Paddle, with generation limits and incomplete outputs counted. Saved old-session checkpoints (3 Granite / 11 Paddle records) before expiry; resumed only remaining identities on the supplied new session, with matching model/input/runtime versions. New private heartbeat is active and URLs stay outside Git. No external model-provider calls or training.

The first production re-score exposed a pixel/PDF-point table-gutter inconsistency. Preserved baseline-v3-ppocr and an exact hash-matching pre-fix GST module. Made gutters relative to glyph height, added scale-invariance tests, and mapped cached comparison geometry into the same 200-DPI PDF-point frame. Re-scored every example as baseline-v4-ppocr. This inspected-test repair and inherited raw-caption caveat are explicitly documented; no blind-test claim or label/text/number repair.

Final official test: 891/985 correct core values (90.5% recall), 891/909 correct proposed core values (98.0% conditional precision), all five core headers correct on 120/197 documents (60.9%). Complete-row TP 640, proposed 736, labelled 769: precision 87.0%, recall 83.2%, F1 85.0%. All 261 images process with zero technical failures; the 24 adversarial and 40 regional scores stay separate. Photo row F1 is 67.8%, versus 96.3% clean / 98.6% scan, and regional documents remain outside the English model's supported automatic scope. These are extraction metrics, not invoice approval accuracy or automation.

Corrected 60-image validation comparison: header recall 89.3% compact / 59.3% Tesseract, row F1 87.3% / 42.4% using the same GST parser. The 130-image calibration diagnostic has six high-confidence header errors, so OCR confidence thresholds alone are not a correctness guarantee. Existing business rules, source verification and separate staff approval remain.

Final software verification: 200 real-PostgreSQL tests pass; the extended browser journey passes in 22.1 seconds, including actual compact-OCR upload, source highlight, explicit authored reviewer correction, preserved original reading and current benchmark page. The scanned fixture now correctly requires review for uncertain pack notation rather than being forced to auto-accept. Simulated correction is not counted as OCR accuracy. Axe reports zero violations in the scanned login/mobile workspace views. Frozen source/input hashes and all 261 unique prediction records were verified. No cloud deployment or environment publication.

## 2026-11-11 — Focused submission edge-case acceptance

Re-read the user-uploaded guide outside Git and selected four nontrivial PS-1
families: missing box conversion evidence, offsetting line-price errors, partial
and concurrent billing, and supplier-scoped duplicates/revisions. Added eleven
focused actual-application checks, including two controls, with explicit authored
expected outcomes and JUnit observed evidence. These reuse known fictional source
fixtures; no blind evaluation, new model training or label generation is claimed.

All eleven pass with real PostgreSQL, authenticated API uploads, the actual
durable worker and saved decisions, plus review/approval actions where specified.
The scan engine is asserted to be PP-OCRv5 mobile. Its observed EA/box -> EAbox
error is flagged for source verification; the test explicitly distinguishes a
simulated reviewer correction from OCR accuracy. Concurrent approvals permit only
one 400-item allocation against the remaining 600, leaving 200. Different-layout
duplicates are caught while another supplier's same invoice number is allowed;
a changed total remains revision review. Ordinary company data is not modified.

Added a reproducible evaluator, runtime-source/image provenance, expected/observed
report and demo-input bundle. See docs/submission-edge-cases.md. No changes to the
production model, business policy or confidence threshold; no deployment,
environment publication or external communication. This focused check is not a
new full-suite run or a production accuracy/automation measurement.

## 2026-11-11 — Code review, documentation images and main-branch handover

Reviewed the core authenticated workflow, original-source preservation, corrections,
supplier/PO matching, duplicate identity, locked approvals, idempotency, cumulative
balances and evaluation evidence. Reproduced a compact-date chronology bypass:
20261001 was accepted but string comparison missed an order date of 2026-11-01.
Fixed canonical review dates and actual calendar comparison, with six regressions.
Archived edge reports now freeze/verify original run hashes and JUnit bytes;
distinct expected test identities are required, with four provenance regressions.
The runtime probe also uses the same UID/GID as test execution. No model/policy
threshold tuning or new OCR benchmark was performed.

Added two AI-generated architecture/evaluation illustrations to the README and a
plain-language architecture guide. Sources and saved numbers were checked; images
are labelled as illustrations. Candidate guide and credentials remain outside
Git. Earlier benchmark results retain their original code identities, including
the pre-review edge reports.

Verification: full real-PostgreSQL suite 221 passed/zero skipped; TypeScript/Vite
production build passed; browser journey passed; reviewed edge suite 11/11;
provenance regressions 4/4 after the launcher correction. Current backend source
was mounted read-only into the existing model-equipped test image and verified by
hash. Isolated schemas were used, browser fixture stopped, ordinary ledger retained.
See docs/code-review.md and ml/results/code-review-v1. User explicitly requested
advancing main; no force push, environment publication or app deployment is part
of this handover.

## 2026-11-11 — Remove dead code and obsolete dependencies

Removed unused imports and local bindings across the app, tests, evaluation tools
and scripts; invoice-creation calls with side effects are retained. Removed the
unreachable tax-rate label branch from the line editor. The standalone matching
policy/review prototype had no live or evaluation caller beyond its own tests;
removed it and its 17 prototype-only cases, and simplified invoice routing to take
the already verified PO-line ID. Actual persisted review, semantic-confirmation,
source-preservation and approval tests remain.

Removed unused fastapi-users and its six now-unneeded transitive packages,
deduplicated reportlab's development declaration, and regenerated the lockfile
without changing retained package versions. Added pinned development Ruff checks,
`make lint`, and TypeScript unused-local/parameter checks. CLI entry points,
documented experiments, migrations and frozen benchmark artifacts are retained.

Final verification uses a freshly synchronized, locked virtual environment in the
model-equipped test container. All seven removed packages are explicitly absent;
204 tests pass with real PostgreSQL and zero skips. Frontend production build and
unused-code checks pass; the browser journey also passes in 20.5 seconds against
the cleaned source and fresh dependency environment. The isolated browser fixture
was stopped afterward. The earlier 221-test report remains historical evidence,
not relabelled after retiring prototype tests. No OCR re-benchmark, model training,
application deployment or environment publication is part of this cleanup.

## 2026-11-11 — Vercel deployment and live verification

User authorized deployment after connecting their Vercel CLI account. Created
reconcile-invoices on Hobby and connected reconcile-db on Neon's free_v3 plan in
Singapore after the user accepted the provider's integration terms. No paid plan
was selected. The website/API use the existing production container stage; a
separate 2-GiB Vercel Daemon runs the CPU OCR worker. Public URL:
https://reconcile-invoices-xi.vercel.app.

Added managed PostgreSQL URL normalization, serialized first/repeat migrations and
demo initialization, hashed initial-approver provisioning without resetting
existing passwords/sessions, graceful worker shutdown, and a hosted four-MiB
upload limit exposed to the interface. Deployment secrets and generated app
credentials remain outside Git. No environment publication or submission video.

Verification: 216 tests with real PostgreSQL pass with zero skips, including
concurrent/repeated hosted initialization. Frontend build and lint pass. Eleven
actual public API checks pass, including approval replay, differently formatted
duplicate, hidden price errors, overbilling, missing pack review, MiniLM human
confirmation and actual mobile OCR/source correction. Corrections are explicitly
simulated, not model accuracy. One fictional hardware verification invoice was
approved; main glove demo balances remain 600 each. The public browser journey
passes over verified HTTPS, including source highlights, ledger, mobile and logout.

Redeployed the reviewed functional commit and verified the existing session,
original PDF bytes, saved approval and balances survived; new worker readiness
passes. Public root is 200, readiness is 200, unauthenticated invoices API is 401.
Curated evidence is in ml/results/vercel-deployment. The Vercel GitHub app was not
connected, so deployment currently uses the CLI. Hobby's finite daemon quotas and
their approximately 8.75-day continuous-runtime implication are documented in
docs/hosting.md. Existing model benchmarks remain unchanged.
