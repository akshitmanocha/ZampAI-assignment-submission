# Matching at approximately 90% automation

The updated objective is maximum measured accuracy around 90% automatic coverage, followed by OCR work. These results concern **product-pair decisions**, not the percentage of invoices accepted/rejected without a reviewer. A 'different product' prediction eliminates a candidate; it does not reject an invoice.

## Procedure

1. Fit lower/upper model-score boundaries using validation labels only. The objective maximizes correct automatic pair decisions while keeping validation coverage at least 90% and close to that target. Scores between the boundaries abstain.
2. Measure the fixed boundaries elsewhere. Actual coverage can shift: the original checkpoint's fixed policy automated 90.3% on validation, 82.6% on the old test, and 60.6% on a new 720-pair challenge. Do not advertise a validation target as an achieved serving rate.
3. For the requested fixed-budget comparison, rank examples by absolute distance from the validation-fixed decision boundary and review the lowest-margin approximately 10%. Selection uses scores, not evaluation labels. This is an offline batch diagnostic, not a production quota. It can expose how much accuracy is lost when forcing higher coverage.
4. Compare the saved epoch-1 and epoch-3 checkpoints using validation automatic accuracy at ~90% coverage, then lower validation binary-cross-entropy as a tie-break. Both had perfect validation automatic accuracy; epoch 3 had lower validation loss and was selected. No new training in this step.

## Measured results

| Data | Automatic decisions | Human-review candidates | Accuracy among automatic decisions |
|---|---:|---:|---:|
| Earlier simple pilot test, selected epoch 3 | 130/144 (90.3%) | 14 | 100% |
| New harder challenge, epoch 1 | 648/720 (90.0%) | 72 | 94.0% |
| Harder challenge, selected epoch 3 | 648/720 (90.0%) | 72 | **94.6%** |

The selected model made **35 wrong automatic pair decisions** on the harder challenge: 2 wrong 'same product' and 33 wrong 'different product'. Same-product precision 99.23%; different-product precision 91.52%. Overall 613 of 720 examples were automatically correct (85.1% correct automation coverage). The 72 reviewed pairs are not counted as correct. No human corrections were performed or scored.

The 720 pairs cover 10 new fictional product families and new phrasing, balanced positive/negative labels. Manifest and labels were frozen before first scoring. Once inspected and used in this comparison process, the challenge is development evidence; the later checkpoint result is **not a new blind test**. Templates remain synthetic, attributes are explicit, and there is no real OCR noise, missing-attribute ambiguity, no-candidate behavior or independently audited invoice ground truth. This is the best tested result in this comparison, not a claim of globally optimal accuracy.

The 90% selection is an offline comparison with deterministic tie-breaking. A real system must review additional cases when evidence is missing, contradictions exist or the distribution changes. Do not force 90% automatic invoice decisions by guessing or rejecting unmatched products. The application has not enabled this policy.

## Artifacts and reproduction

- `ml/coverage_policy.py`: validation threshold search, fixed-policy metrics, score-only 90% batch comparison.
- `ml/curate_challenge.py`: reproducible 720-pair catalog challenge, manifest and hashes.
- `ml/results/coverage90/`: policy, initial fixed-policy failures, budget results, updated checkpoint comparison, exported-artifact digest.
- `ml/compare_coverage.py`: reproducible checkpoint comparison in the existing ML environment.
- Selected epoch-3 model exported to `/workspace/reconcile-artifacts/selected90-model.tar.gz`, outside Git; archive and contained file hashes verified. The previous epoch-1 artifact remains separate.

Next stage is OCR: audit visible labels, evaluate native versus scanned documents and clean/faded/bad-scan slices, then improve structured field and row extraction. Pair accuracy alone is insufficient to claim 90% invoice automation. End-to-end invoice evaluation remains required after extraction is integrated.
