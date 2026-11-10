# Three invoice buckets and uncertainty

Objective: minimize the fraction needing human review while separately protecting the precision of automatic acceptance and automatic rejection. Review is an intentional abstention, not a forced guess. Accept means ready for approval after required checks; routing itself never moves balances or money. Reject is a recommendation based on a confirmed blocking discrepancy, not an automatic permanent database rejection action.

## Bucket rules

- **Accept:** all mandatory checks pass using verified evidence, and product identity is confirmed by a separately validated match policy (or later by reviewed evidence and revalidation).
- **Human review:** missing/ambiguous extraction, weak or competing matches, absent candidate, missing unit conversion, unsupported cases or unverified findings. Top-k suggestions and none-correct/wider search assist review.
- **Reject:** a confirmed, evidenced blocking business violation. Preserve any other unresolved questions alongside it. A low similarity score alone never proves invoice invalidity.

The router consumes aggregated rule findings. Every invoice line must be included in those aggregates; duplicate rule IDs are rejected so a passing line cannot hide a failing one. `evidence_verified` must come from actual checked source evidence. Setting this flag because a field exists or a model score is high is invalid.

## What uncertainty means

Use model score and distance to the second-best candidate as ranking signals, plus explicit missing evidence, attribute conflicts, retrieval/no-match behavior, and supported input scope. Do not interpret cosine similarity or a raw cross-encoder logit as a confidence percentage.

Choose candidate thresholds on validation data to maximize automated coverage with no observed false matches. Freeze the choice, evaluate separate calibration data and an independent final invoice test, and report accepted/rejected precision, review rate and finite-sample uncertainty. A high score can still be wrong. Thresholds/margins require representative evidence before being enabled.

## Measured first diagnostic

Selected a cross-encoder match threshold using the pilot validation split only, maximizing the number matched with zero observed validation false matches. Threshold was then fixed for the remaining split checks:

| Split | Pairs | Automatically matched | Wrong automatic matches | Reviewed/unresolved | Observed match precision |
|---|---:|---:|---:|---:|---:|
| Validation | 144 | 72 | 0 | 72 | 100% |
| Calibration | 96 | 48 | 0 | 48 | 100% |
| Existing test | 144 | 72 | 0 | 72 | 100% |

These are **pair matching** results, not invoice buckets. The existing synthetic sets had already been inspected in earlier experiments, so this is not fresh blind evidence. No invoice rejection precision, end-to-end acceptance precision, or human-review correctness has been measured. Pair negatives mean different products, not necessarily an invalid invoice.

Data cover only two calibration categories and three test categories, with repeated template pairs within each category. Treating all pairs as independent would exaggerate confidence. An illustrative one-sided 95% bound using 'any automatic error in an accepted category' as the group event is 77.6% with two error-free calibration groups. That is a bound for comparable independent category events, **not** an estimated 77.6% invoice error rate or a validated production risk bound. The fictional categories are not established as a representative deployment sample.

Even with genuinely independent, representative cases, zero errors in 299 accepted cases supports an approximate 1% error upper bound at 95% confidence; it does not prove exactly zero error. Finite evidence cannot certify a universal 100% precision guarantee. Perfect human review is an assumption, not a measured result, and missing evidence must remain unresolved.

## Current implementation

- `backend/reconcile/invoice_routing.py` implements the three-bucket recommendation logic; it is not wired into a completed PDF/API workflow.
- `ml/uncertainty.py` selects a development threshold, measures coverage/observed precision and computes an explicit finite-sample bound. It never certifies zero future risk.
- `ml/results/uncertainty/` contains actual scores and results. Existing operational model automation remains disabled.
- Required-check omission, unverified failure, uncertain identity and confirmed-blocker routing are tested. Unit passes validate code behavior; they are not an invoice accuracy benchmark.

Next evidence needed: independently audited linked invoice scenarios with accept/review/reject labels, genuine no-match cases, scans and missing fields; candidate ranking/margin evaluation; threshold selection without final-test feedback; and real reviewed-case outcomes. Select an operational risk target explicitly before enabling learned automatic decisions. Do not silently substitute a nonzero tolerance for a requirement of zero errors.
