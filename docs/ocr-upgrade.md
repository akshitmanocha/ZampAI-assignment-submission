# Small-model OCR and Indian GST extraction — 11 November 2026

The new local reader uses **PP-OCRv5 English mobile** through RapidOCR/ONNX Runtime, with a GST-aware field parser. The two OCR files contain about **3.1 million stored weight/buffer values** and total **12.7 MB** (decimal bytes), comfortably below one billion. There is no fine-tuning in this upgrade: we use pretrained OCR and improve source-based parsing. Models receive document pixels, never the answer labels, supplier catalog or expected purchase-order values.

## Official-test re-score

On the same 197 test invoices, core header recall rises from **35.5% to 90.5%**, proposed-header precision from **83.5% to 98.0%**, and complete-row F1 from **0% to 85.0%**. The new reader correctly recovers 640 of 769 labelled item rows; there are 736 proposed rows, so row precision is 87.0% and recall 83.2%. All 261 images, including separate robustness suites, process without technical failure.

All five core headers are correct together on **120/197 invoices (60.9%)**. The per-field result is not invoice automation. Photographed pages remain the main bottleneck: row F1 is 67.8%, versus 96.3% clean and 98.6% scanned. Human source review and independent real-invoice validation remain necessary. See [the complete result tables](indian-gst-evaluation.md).

## What changed

1. Native text-only PDFs still use their text layer. Image pages use the pinned small OCR detector/English recognizer on CPU in the same credential-isolated, resource-bounded child.
2. Recognized line orientations provide deskewed logical coordinates for layout parsing. Each word separately retains its original-page rectangle; evidence highlights and quality checks use that original rectangle. Original PDF bytes and source previews are preserved.
3. The GST parser recognizes quantity, unit, HSN, unit rate, **net taxable line value**, GST rate and separate tax columns. Net amounts are not confused with CGST/SGST or gross totals. Receipt-style items need a printed quantity/unit × rate/amount line plus HSN evidence.
4. Supplier identification stays above the seller GSTIN/buyer block. An unreadable seller does not fall back to the buyer's name. Taxable subtotal, separate tax totals and round-off have explicit source anchors.
5. Numeric dates such as `03/04/2026` stay ambiguous. A BOX label does not invent its pack size. Missing printed amounts are not reconstructed by multiplying quantities and prices.
6. Weights are provisioned during setup and checked against fixed SHA-256 values. The app checks its selected OCR assets at readiness. A failed model is a visible processing failure; it does not silently change readers.

The compact model can misread packaging notation in an otherwise clear scanned demo. It reads `100 EA/box` incompletely and gives that description a low score. The source gate correctly routes that reading to review. A simulated reviewer restoring the authored printed text revalidates successfully while preserving the original extraction. The regression test checks this fallback rather than forcing an uncertain reading to auto-accept; that correction is not counted as OCR accuracy.

## Coordinate consistency and preserved interim results

The first full PP-OCR run exposed a coordinate-unit mismatch: development OCR caches used pixels, while the application uses PDF points. A fixed table gutter could therefore include a printed serial number in the description at PDF scale. The interim `baseline-v3-ppocr` is retained with its 63.8% row F1; its exact pre-fix GST component is snapshotted and hash-checked under `pre-coordinate-fix`.

Column gutters now depend on glyph height, with authored regression tests at multiple coordinate scales. Development caches and VLM adapters are mapped to the same 200-DPI PDF-point frame before the shared parser runs. No OCR text, prices, quantities or publisher labels were changed. The complete source suite is re-run as `baseline-v4-ppocr`. The corrected validation reports are `selection-v2-pdf-coordinates` and `gpu-qualification-v2-pdf-coordinates`; the first coordinate protocol reports are retained as interim evidence. Both the initial test inspection and this engineering repair are disclosed; the final re-score is not a blind test. The inherited no-test-guided-fixes caption in the raw harness is clarified in [report notes](../ml/results/ocr-upgrade/report-notes.json); it is not a global claim for this upgrade.

## Data boundaries

We keep the same pinned Divya52 Indian GST source and unchanged publisher labels. [The new development manifest](../ml/data/indian-gst-ocr-v1/manifest.json) was frozen before model inference:

| Group | Selection | Use |
|---|---|---|
| 24 parser-development images | First two train IDs for each of four layouts × three quality levels | Develop the GST rules |
| 60 model-selection images | First five validation IDs in each layout/quality stratum | Compare the reader/parser variants |
| 130 calibration images | Remaining validation records | Audit confidence behavior separately |
| 197 official test images | Original frozen source test suite | Re-score only after freezing the new pipeline |
| 24 adversarial + 40 regional | Original separate robustness suites | Separate scores, no mixing into primary result |

Twelve model-selection examples, one per stratum, form a common qualification set for the larger CPU/GPU candidates. All twelve stay in their subsequent selection group. No test example enters model selection or calibration. This is an exploratory staged comparison, not a preregistered exhaustive model search.

The official test was already inspected in the original Tesseract baseline. The new result is a **disclosed re-score**, not fresh blind confirmation. The source has four recurring layouts and 25 recurring product descriptions; images alone contain no authoritative PO/approval history or same-product retrieval truth. This benchmark cannot establish invoice accept/reject accuracy, invoice automation or a future zero-error guarantee.

## Validation comparison

On the same 60 model-selection images and the same new GST parser:

| Reader | Correct core headers / labels | Precision of proposed headers | Complete-row F1 |
|---|---:|---:|---:|
| Tesseract | 178 / 300 — 59.3% | 89.9% | 42.4% |
| PP-OCRv5 English mobile | 268 / 300 — 89.3% | 98.2% | 87.3% |

The row score requires exact normalized description, quantity, rate and net amount. Extra and missing rows count against it. The report also compares each OCR with the frozen original parser, so the OCR change and the GST parser change can be distinguished. These are development results; they are not the official-test headline.

On the separate 130 calibration images, the compact reader gets 601/650 core labels correct (92.5% recall), 601/607 proposed values correct (99.0% conditional precision), and 85.8% complete-row F1. A confidence threshold alone cannot remove all observed mistakes: even thresholds through 99.9 retain errors; 100 retains no proposals. We therefore do not relabel OCR scores as probabilities or claim a calibrated automatic-approval guarantee. Business checks, explicit source-review flags, staff correction and separate authorised approval remain necessary.

## GPU comparisons and size verification

[The model audit](../ml/results/ocr-upgrade/model-assets.json) records revisions, licenses and weight sizes. Granite Docling has about 258M stored parameters; PaddleOCR-VL-1.6 has about 959M. Stored checkpoint counts can differ from unique loaded parameter counts. The two tested GPU models explicitly assert fewer than one billion loaded parameters; those actual counts are recorded with their results. Other researched models were not all benchmarked, and this is not an exhaustive leaderboard.

The GPU qualification uses fixed generic prompts on the same twelve validation images. Paddle uses its native Spotting task; Granite emits DocTags converted to document structure. Their proposed locations are unverified and all VLM-derived readings require source review. This measures these adapters in our extraction task, not the models' published benchmark scores or Paddle's separate official layout pipeline. Caption/position-token adapters and time budgets can affect the result.

Initial runtime probes exposed a processor API mismatch, slow decoding without an explicit key/value cache, and Granite FP16 numerical degeneration on T4. Those invalid/stopped probes are preserved outside Git and are not passed off as valid model-quality results. The corrected runs use KV caching, FP32 for Granite (T4 lacks BF16), FP16 for Paddle, fixed generation limits and recorded incomplete generations. The old Kaggle session expired; completed outputs were copied locally and the remaining IDs resumed on the replacement session, with matching source hashes, model revisions and runtime versions. No completed example was discarded because its answer was bad.


The corrected common twelve-image qualification gives:

| Candidate | Model size | Core-header recall | Complete-row F1 |
|---|---:|---:|---:|
| Tesseract | Legacy baseline | 56.7% | 35.9% |
| PP-OCRv5 English mobile | ~3.1M stored values | 90.0% | 83.3% |
| PP-OCRv5 server | ~43.1M stored values | 81.7% | 81.5% |
| Granite Docling | 257.5M loaded parameters | 50.0% | 0.0% |
| PaddleOCR-VL-1.6 | 905.6M loaded parameters | 86.7% | 65.3% |

Paddle-VL proposed 52/52 core values correctly on this small qualification set, with lower header coverage and row recovery than the compact reader. All its proposed geometry remains unverified. Granite had three incomplete generations within the fixed budget. Mean GPU reading times were 21.6 seconds for Paddle and 44.6 seconds for Granite on shared T4 sessions; these are task/protocol diagnostics, not portable latency guarantees.

## Reproduce and inspect

```sh
make invoice-data
PYTHONPATH=backend uv run --project backend python ml/prepare_ocr_development.py
make models
# Cache a complete group, selecting paddle-mobile or tesseract:
PYTHONPATH=backend uv run --project backend python ml/cache_ocr_development.py \
  --engine paddle-mobile --purpose model_selection \
  --output /workspace/reconcile-artifacts/ocr-development/paddle-mobile
docker compose --profile test build test
make evaluate
```

The default Docker application/evaluator now selects the compact OCR. Standalone Python reading retains Tesseract compatibility unless `OCR_ENGINE=paddle`, `OCR_PROFILE=mobile` and a provisioned `OCR_MODEL_DIR` are set. The candidate-scoring script requires complete caches for every group it reports; it refuses incomplete or changed input/label hashes. See [selection and calibration evidence](../ml/results/ocr-upgrade/selection-v2-pdf-coordinates/), [official evaluation methodology](indian-gst-evaluation.md), and [model/GPU evidence](../ml/results/ocr-upgrade/).

Regional Hindi/Kannada pages remain outside the English model's supported automatic scope. Additional GST/buyer targets are still reported separately, including missing capabilities and unprinted-zero label visibility issues. A larger independent real-invoice audit remains necessary before production accuracy or automation claims.
