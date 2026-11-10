# Frozen edge-case validation v1

This adds a linked, reproducible business validation set: ordinary vendor/order/history inputs, printed invoice specifications, actual PDFs, independent expected recommendations, and real PostgreSQL action traces. It is a synthetic acceptance suite, not a production accuracy estimate or a new model-training result.

## Scope and cases

25 authored cases across 15 named control/edge groups. All belong to **validation**; none are used for model training or confidence-threshold fitting. Controls and mutations remain grouped. No blind final-test claim: the implementation agent authored both the specification and implementation, and an independent human audit has not occurred.

| Family | Cases | What a correct system must do |
|---|---|---|
| Packaging/specification | W01–W03 | Convert six boxes only with printed 100-EA evidence; block latex/nitrile conflict; review absent pack evidence |
| Total hides price errors | W04–W05 | Accept agreed prices; detect BOTH overpricing and underpricing despite unchanged total |
| Partial billing | W06–W07 | 1000 ordered minus 400 approved leaves 600; accept 600 and block 700 by 100 |
| Missing/ambiguous references | W08–W10 | Infer a unique eligible vendor PO; review two plausible POs or missing invoice number |
| Vendor/duplicate controls | W11–W14 | Preserve explicit vendor/PO conflict; detect prior file/business invoice; review possible revision; allow another vendor's same number |
| Arithmetic/status/boundaries | W15–W20 | Check separated tax arithmetic; block closed PO/blocked vendor; inclusive .05 unit-price boundary passes while .051 fails |
| Multiple rows, one order line | W21–W22 | Aggregate 300+300 and 600+600 before checking a remaining 600 |
| Stateful approvals | W23–W25 | Block stale and competing approvals; repeated approval has exactly one allocation effect |

Four PDF representations per case: two native layouts, clean image-only scan, and mildly rotated/noisy/blurred/compressed scan. This makes **100 case/PDF assignments**, not 100 independent documents. Several cases deliberately reuse an identical invoice with different history/vendor/order status. There are **68 distinct PDF byte sequences** and **24 unique document/company/action scenarios** (one control is shared). The evaluator caches extraction by document hash but recomputes decisions against each isolated company context.

Cases do not constitute a batch to approve against one shared ledger. Each case starts from its own snapshot; the three stateful traces explicitly define within-case history changes.

## Labels and leakage protection

- Input JSON lives in `fixtures/workflows/v1/inputs`; expected answers in a separate `expected` directory.
- `ml/curate_workflows.py` contains explicit authored expectations and a separate Fraction-based arithmetic audit. It imports no production decision code and never uses an LLM to generate the correct bucket.
- Manifest SHA-256 was frozen before the first pipeline evaluation: `157ab0ed9a8fd142259e52e4f6c85300a67f4ac2d676fcd27d7daebef5f6a309`. It remained unchanged throughout debugging.
- The evaluator checks every input/oracle hash and exact curator reproducibility. Regeneration refuses to overwrite an existing dataset. A future specification change needs an explicit dataset version/review.
- Recommendation code receives only extracted document values, ordinary company records, policy and fingerprint. No case ID, filename, family or expected answer is passed to it.
- PDFs have neutral content-based filenames and ordinary invoice metadata. No expected bucket or case label is printed in them.
- Expected files are excluded from the application image. No new API or public preview exposes them.

Expected answers specify bucket, exact blocking-rule set, required review reasons, and selected independently authored normalized values. PDF runs additionally check header readings, exact normalized descriptions, numeric item fields and line count. A correct bucket with wrong extraction does not pass. Recommendations must not mutate history.

## Two evaluation tracks

1. **Oracle-input diagnostic:** supply the correct printed fields directly. This isolates normalization, vendor/PO resolution, deterministic SKU/attribute matching, price/quantity arithmetic and routing. It is explicitly not OCR performance.
2. **Actual PDF track:** pass PDF bytes through the real PDF reader/Tesseract/parser, then the same validator. The runtime never sees the invoice specification used to render it. The evaluator compares only after the pipeline returns.

The matcher in this suite requires an exact printed catalog SKU and explicit matching material/size. Missing identity evidence remains review. MiniLM, embedding retrieval and Nemotron are **not used** here, so these results do not improve or supersede their earlier measured scores. This bounded baseline is intended to test business logic independently of learned matching.

## Failures found and fixed

The first run correctly handled native PDFs and clean scans, but tilted scans lost the item table. The validator incorrectly summed an empty extraction as zero and issued an arithmetic rejection. That was a real defect, not a wrong expected answer.

Fixes: geometry grouping tolerates slight row skew; missing item extraction is unknown/review; a later uncertain row cannot erase an earlier confirmed violation; absent invoice numbers cannot steal PO references below; explicitly labelled alphabetic invoice IDs are retained. Unit regressions cover these plus file-vs-business duplicates, normalized-identifier collisions, generic SKUs and both offsetting price errors. Expectations were not changed to make the tests pass.

The renderer also exposed timestamp nondeterminism in Pillow's scanned PDF metadata. Fixed creation/modification times; identical native, scanned and degraded source bytes repeat on this pinned host. Renderer versions and artifact hashes are saved; cross-platform byte identity is not claimed.

Initial raw outputs remain under `ml/results/workflows/initial`. That early harness did not yet include the final strict field-by-field extraction checks. Initial bucket accuracy was 85%; final bucket accuracy is 100% under the same frozen business expectations. Use `final` for the full current assertion definition.

## Observed final results

| Check | Result |
|---|---:|
| Correct-field/oracle recommendations | 25/25 pass |
| Actual case/PDF assignments, all assertions | 100/100 pass |
| Case/PDF verdicts | 44 accept, 16 human review, 40 reject recommendations |
| Named groups with every control/variant correct | 15/15 |
| Real PostgreSQL action traces | 3/3 pass |

Observed accept/reject precision is 100% **within this authored suite**. There is no statistical guarantee for future invoices. Ordinary recommendation coverage is 84% automatic and 16% review because four of 25 cases deliberately need information or investigation. After deduplicating shared document/context/action controls, automatic coverage is 83.3%. Do not remove hard cases or guess missing evidence to force this deliberately enriched set to 90%.

PostgreSQL runs use isolated, freshly migrated schemas, actual parsed native PDFs and company snapshots read from SQL. Prior allocations are seeded from ordinary case inputs; PO dates are 2026-11-01, before the test invoices. The fixed validation clock is 2026-11-10. Each schema is removed after its trace; existing application/demo records are untouched.

- Sequential competing bills: both initially qualify, first approves, second returns APPROVAL_STALE; remaining 200, one new approval.
- Repeat: approved then already_approved; remaining zero, no second allocation.
- Concurrent: one approved and one APPROVAL_STALE; remaining 200, one new approval. Rechecking the losing invoice returns a quantity rejection recommendation.

These check ledger effects, not persistent decision-version/audit/UI behavior. Current approval service still uses its initial exact-price guard; configurable tolerance recommendation cases are not yet exercised through approval. Policy alignment/version persistence must be completed before using those cases in live approval.

## Reproduce

```sh
make install
make workflow-data-check
make workflow-test
# Requires the built/running local app and PostgreSQL services:
docker compose up --build -d
make workflow-db-test
```

Default test outputs go under `/tmp/reconcile-workflow-validation`; override `WORKFLOW_OUT` if needed. `workflow-test` fails if any expected assertion fails. Hash mismatches, missing variants, duplicate assignments and zero-case runs are errors, not passes. The ordinary test suite separately exercises the frozen oracles and regression guards.

Current canonical results and source hashes: `ml/results/workflows/final/metrics.json` and `ml/results/workflows/database.json`. Generated PDF manifest and ZIP digest are tracked; PDFs/HTML review bundle are retained outside Git at `/workspace/reconcile-artifacts/workflow-v1/` and can be regenerated.

## Remaining limitations

Two controlled render layouts and mild scan corruption are not a diverse invoice population. No independent human annotation audit, external holdout, learned-match uncertainty, severe unreadability, inclusive-tax ambiguity, discounts, bundles or multi-PO cases are evaluated. Source trust/confidence policy is not production-calibrated. Unknown inputs must remain review.

The harness is backend PDF-to-recommendation plus separate database traces. It is not a browser upload, durable worker/job, persisted correction/decision-history or hosted acceptance test. Those integrations remain outstanding. No external model requests or training were run in this step.
