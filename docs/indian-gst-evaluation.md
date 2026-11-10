# Primary invoice evaluation: Indian GST

The primary invoice-reading dataset is [Divya52/indian-gst-invoices](https://huggingface.co/datasets/Divya52/indian-gst-invoices), revision `fece40b9a96ac3949934fc05c714853a5283d730`, CC BY 4.0. It replaces InvoiceOCR-Synth for new invoice-extraction evaluations. Historical results and deterministic business-rule fixtures are retained with their original scope.

## Measured baseline — 10 November 2026

The complete run processed all **261 images with zero technical failures**. The main 197-invoice result shows that the current field parser does not yet support these GST layouts well enough for automation. Successful processing is not successful extraction.

| Main official test metric | Raw readings | After source-verification gate |
|---|---:|---:|
| Core header recall | 35.5% | 33.3% |
| Precision of proposed core headers | 83.5% | 86.1% |
| Core values correct / all labels | 350 / 985 | 328 / 985 |
| Proposed core values | 419 | 381 |
| All five core headers correct | 0 / 197 | 0 / 197 |
| Complete line rows correct / labelled | 0 / 769 | 0 / 769 |
| Predicted item rows | 0 | 0 |
| Complete-row F1 | 0.0% | 0.0% |
| Technical failures | 0 / 197 | 0 / 197 |

Row precision is undefined because no rows were proposed; recall and F1 are zero. Do not describe header precision as invoice accuracy: it measures only proposed values, while most labelled values were missing. The gate retains 53 incorrect core values among 381 proposals, so it is not a safe automatic-approval confidence threshold.

| Core field | Correct / 197 labelled | Found values | Recall | Precision among found |
|---|---:|---:|---:|---:|
| vendor name | 29 / 197 | 79 | 14.7% | 36.7% |
| invoice number | 108 / 197 | 121 | 54.8% | 89.3% |
| invoice date | 80 / 197 | 81 | 40.6% | 98.8% |
| subtotal | 0 / 197 | 0 | 0.0% | Undefined (no proposals) |
| grand total | 133 / 197 | 138 | 67.5% | 96.4% |

The parser recognizes its earlier subtotal/amount headings, but the inspected GST validation layouts use **Taxable Value** and net **Taxable** columns with separate GST components. Those mappings are not implemented in the existing parser. Supplier selection and photographed layouts are additional weak areas. Zero item rows is a field/table-parsing limitation; it must not be presented as 769 correctly handled manual reviews. This extraction corpus has no correct decision-bucket labels.

| Main source quality | Documents | Core header recall |
|---|---:|---:|
| clean | 57 | 54.0% |
| photo | 83 | 14.0% |
| scan | 57 | 48.4% |

| Separate robustness suite | Documents | Raw core header recall | Raw proposed-header precision |
|---|---:|---:|---:|
| injection | 24 | 54.2% | 97.0% |
| regional | 40 | 33.0% | 75.9% |

These results establish a reproducible starting point, not readiness for Indian invoice automation. Additional GST targets remain missing and are included in the raw report. Next: implement and test GST-aware header/table extraction on train/validation images, audit label visibility, and calibrate abstention using separate development data. Any later test re-score must disclose reuse of this inspected test; obtain a new unseen audit set for fresh confirmation.

Raw evidence: [metrics](../ml/results/indian-gst/baseline-v2/metrics.json), [all predictions](../ml/results/indian-gst/baseline-v2/predictions.jsonl), and [frozen run metadata](../ml/results/indian-gst/baseline-v2/run-start.json).

## What goes in and what counts as the answer

The input is the publisher's original invoice image. The expected answer is its publisher-supplied structured invoice JSON: supplier, buyer, invoice identifiers, rows and GST totals. We did not ask Nemotron to invent labels. We did not manually rewrite labels to fit our parser. These are generated synthetic labels, not independently audited real-invoice annotations.

The main source has 1,613 train, 190 validation and 197 test records. We selected **all 197 official test rows using the source `split` column**. Hugging Face's loader exposes the whole config as `train`; that loader name is not the evaluation selection. All 24 injection examples and 40 Hindi/Kannada examples are separate robustness suites, not added to the main score. No output-guided subset or easy-case filtering is used.

The frozen [manifest](../ml/data/indian-gst-v1/manifest.json) includes source revision, metadata hashes, image hashes and original label-string hashes. Two preselected validation images received an implementation-agent visual spot-check, recorded in [the audit note](../ml/data/indian-gst-v1/validation-audit.json). This is not a full independent label audit. A source label can contain a zero tax component that is not printed, so additional tax-field recall needs that caveat.

The [source split audit](../ml/data/indian-gst-v1/split-audit.json) finds no overlapping record IDs, exact label strings or supplier/invoice/date identities across train/validation/test. All 25 product descriptions occur in every split. Therefore these are new invoice records, not held-out product families; image near-duplicates have not been independently audited.

## How the baseline runs

1. Verify every frozen source hash before scoring. Keep original images and publisher metadata outside Git.
2. Embed each original image in a neutral, image-only PDF at 200 DPI, with no deliberate image resampling, extra text layer or label-bearing filename. The PDF bytes are the reader's sole input.
3. Call the same bounded PDF child used by the application: native-text detection, Tesseract OCR, geometry parser and source-quality policy. No SQL ledger, expected answers, GPU, external model or fine-tuning is involved.
4. Join the publisher label only after extraction finishes. Keep missing/ambiguous readings and technical failures; do not repair values from labels or drop failed documents.
5. Score raw readings and readings that pass the application's source-verification gate separately. Store per-document predictions, runtime versions and source hashes alongside aggregate metrics.

The first launcher probe ran without a container init process. The PDF child interpreted its parent PID 1 as loss of its supervisor and exited before reading. This was an invalid infrastructure run, not an OCR score. It is documented in `harness-repair.json`; Compose test containers now use `init: true`, and the evaluator refuses PID 1.

The following partial run exposed pathological Tesseract threading latency. On preselected validation image `syn_0_00222`, the existing `OMP_NUM_THREADS=1` setting still timed out at 30.75 seconds; adding Tesseract's `OMP_THREAD_LIMIT=1` read 139 tokens in 3.60 seconds on the same shared host. We stopped the partial run, preserved its evidence, and applied that runtime-only thread bound to the production child. The parser, image inputs, labels, OCR mode and 30-second timeout remain unchanged. `runtime-repair.json` and `validation-runtime-probe.json` record this decision; `baseline-v2` is the full scored run after both runtime repairs. No field-score-guided parser fixes were made. Timing is diagnostic, not a portable latency benchmark.

## What the metrics mean

Five core headers are supplier name, invoice number, invoice date, net taxable subtotal and grand total. A value is correct only if it matches the published target: Unicode/case/whitespace normalization for text, exact identifiers preserving separators/leading zeros, and exact Decimal numeric equality. Dates must already be in the reader's ISO output format; the scorer does not guess ambiguous source dates.

- **Header recall:** correct extracted core values divided by all labelled core values. Missing readings and failures lower it.
- **Header precision:** correct core values divided by proposed `found` values. A withheld value does not improve recall.
- **All five headers correct:** documents with all five exact values divided by eligible documents. This still excludes line items and business decisions.
- **Complete-row precision/recall/F1:** rows must have exact normalized description, quantity, unit rate and **net taxable line amount**. Predicted/expected rows are aligned using description similarity alone (Hungarian assignment, minimum 0.65); numerical values cannot choose a more favorable row. Extra/missing rows count against the score.

Additional supplier/buyer GSTIN/address/state, place of supply, reverse-charge, individual tax totals, rounding, units, HSN and per-line GST/gross totals are reported separately, including targets the current parser does not implement. Null labels stay null; we do not add together tax components to manufacture a missing aggregate extraction target. Quality/layout slices expose weak areas without excluding them from the primary denominator.

The `raw_extracted` track includes all parser readings marked `found`. The `source_verified` track withholds readings flagged for source verification. That flag is an OCR quality heuristic, not a calibrated probability. Its extraction coverage is **not** invoice automation, and neither track assumes a human has corrected the page.

## Reproduce

```sh
make invoice-data
docker compose --profile test build test
make evaluate
```

Results default to `/tmp/reconcile-indian-gst-evaluation/results`; use a fresh `INVOICE_EVAL_OUT` to rerun because completed predictions are never overwritten. `INVOICE_EVAL_DATA` selects the downloaded data directory. The checked-in baseline lives under [ml/results/indian-gst](../ml/results/indian-gst/). Existing `.env`/Compose database configuration is required to resolve the test service, but this evaluator uses no database records and makes no model-provider calls.

## Limits and the next development boundary

This benchmark tests reading invoices, not deciding whether they should be paid. The source has no verified company PO ledger, approved-item identities or prior-approval history. We cannot derive honest accept/reject labels or top-k retrieval truth from these images alone. Existing authored business-rule cases continue to test those mechanics separately.

The dataset is Indian but synthetic: four recurring layouts and a small recurring product catalog do not represent the whole Indian invoice population. Hindi/Kannada, mixed GST rates and several units exceed current automatic scope. No fine-tuning was performed for this baseline; switching the benchmark does not train MiniLM. Future reader improvements must use train/validation data, with calibration kept separate; this first scored test is now inspected development evidence and cannot be presented as a fresh blind confirmation after tuning. A new unseen audit set and linked company records remain necessary for real-world automation claims.
