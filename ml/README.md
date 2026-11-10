# Evaluation datasets and historical experiments

## Primary invoice benchmark: Indian GST

[Divya52/indian-gst-invoices](https://huggingface.co/datasets/Divya52/indian-gst-invoices) replaces InvoiceOCR-Synth as our primary OCR/field-extraction benchmark. Use `make invoice-data`, build the Compose test image, then `make evaluate`. The frozen selection contains all 197 records marked `test` in the source metadata; Hugging Face's loader labels the whole config `train`, so selecting by its loader split would be incorrect. The 24 adversarial and 40 regional records are scored separately.

See [methodology and results](../docs/indian-gst-evaluation.md), [dataset attribution and manifest](data/indian-gst-v1/), [evaluation registry](evaluation_config.json), and [raw evidence](results/indian-gst/). Labels come from the dataset publisher, remain unchanged, and are joined only after the production PDF reader returns. No model was trained for this baseline. The dataset has no linked company records for measuring approval or retrieval accuracy.

The matching and older OCR experiments below are retained as historical development evidence. Authored business fixtures remain regression tests. Changing the invoice benchmark does not retrain MiniLM or replace product-pair labels with invoice images.

## Pair matching: real GPU training, fictional data

`curate.py` generates 80 catalog products in 20 categories and 960 balanced labelled pairs. Four simple descriptions per product create positive pairs; material/size changes create negatives. Categories/products are disjoint across train (576 pairs), validation (144), calibration (96), and test (144). Labels come from exact catalog identity. Integrity checks ran; an independent human audit of all pairs has **not** happened.

The small, templated dataset does not represent real invoices, OCR noise, missing attributes, packaging evidence, or procurement policy. The pilot is intended to validate the training/evaluation machinery. The test has only three independent product families; its 144 pairs are correlated.

`experiment.py` ran on one verified Kaggle Tesla T4 (two GPUs visible):

| Experiment | Test correct / 144 | Accuracy | Pair precision | Pair recall | Pair F1 | Wrong matches | Missed matches |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0: character TF-IDF only | 100 | 69.44% | 63.46% | 91.67% | 75.00% | 38 | 6 |
| B1: frozen MiniLM | 127 | 88.19% | 92.31% | 83.33% | 87.59% | 5 | 12 |
| E1: fine-tuned MiniLM | 138 | 95.83% | 100.00% | 91.67% | 95.65% | 0 | 6 |

B0 is a lexical scorer only; the full attribute-aware operational baseline is not evaluated here. These figures isolate pair scoring and are not invoice approval accuracy. Zero wrong matches on this tiny synthetic sample does not prove zero production risk.

The model is `cross-encoder/ms-marco-MiniLM-L6-v2`, pinned revision in `results/pilot/metrics.json`. It is originally a relevance model; we fine-tuned its single output using binary cross-entropy with logits. Three epochs, batch size 16, learning rate 2e-5, seed 17, maximum length 128. Best checkpoint selected using validation F1; binary threshold selected separately using calibration F1. One seed only. No test-guided changes were made after seeing results. Test must not become a tuning set in the next experiment.

All three epochs achieved validation F1=1 at a validation-selected threshold; the earliest checkpoint was retained. Final calibration threshold produces lower validation F1, which is reported without hiding it. Training losses were 0.4113, 0.0825, 0.0429. See raw JSON for actual timings and confusion matrices.

Selected weights, tokenizer, metrics and predictions were exported from Kaggle to `/workspace/reconcile-artifacts/selected-model.tar.gz` (outside Git), with bundle SHA-256 and each contained file checked. `results/pilot/artifact.json` records its digest. A full last-epoch optimizer checkpoint remains in Kaggle; it has not been exported or validated for resume. These are distinct artifacts.

The selected model was also loaded on CPU in Kaggle: the same 144 binary predictions, maximum GPU/CPU logit difference 0.0000043, and 0.517 seconds for the warm batch with two CPU threads. This excludes model loading, PDF reading, HTTP and database operations. It is not app latency and not a measurement on the deployment host. See `cpu_validation.json`.

The trained model is **not deployed into the app or approval path**. Verify model/data licensing, independently audited tougher data, candidate ranking/no-match performance, and end-to-end behavior before adoption. MS MARCO training-data restrictions are separate from the weight license; this remains a research/case-study experiment.

Reproduce the data from repository root:

```sh
python ml/curate.py
```

Run training in a separately prepared ML environment with torch, transformers, huggingface_hub, numpy and sklearn:

```sh
python ml/experiment.py --data ml/data/pilot --output /path/outside/git/pilot
```

Observed Kaggle versions: Python 3.13.16, torch 2.11.0+cu130, transformers 5.20.2, scikit-learn 1.6.1, datasets 4.8.5. Model downloads preserve normal TLS/checksum verification. `scripts/kaggle_run.py` executes a supplied script in the existing idle kernel and reads its private connection URL from an external file. Never place that URL in a script, argument or log. Do not rerun an unchanged script after a timeout without inspecting kernel status.

## Hugging Face OCR smoke test

Source: [InvoiceOCR-Synth](https://huggingface.co/datasets/alamgirqazi/invoice-ocr-synthetic), author Alamgir Qazi, dataset card CC BY 4.0. Exact source revision and selection are in `results/ocr-smoke/metrics.json`. No public images were used to train the matching model.

`evaluate_ocr.py` streamed the **first 12 clean images** (12 documents covering six templates), then ran Tesseract 5.3.4 in Kaggle. This is a convenience smoke sample, not a randomly sampled held-out benchmark. It checks whether label text/numbers occur **anywhere** in OCR, not whether they were assigned to correct fields:

- Supplier name recovered: 12/12.
- Invoice number recovered: 8/8 eligible.
- Total amount found somewhere: 12/12.
- PO number recovered: 0/3 eligible.

Manual inspection of one failed PO case (`synth_0002_8f01361b.png`) found that the supplied `PO-5678` label is not visible in the rendered freelancer invoice. This is a label-to-image observability issue, not established evidence of an OCR mistake. The other two failures are not yet visually audited. Preserve original scores and label this limitation; do not manufacture the missing number or silently change labels to boost metrics.

The smoke test does not cover faded/bad scans, native PDFs, row extraction, supported INR workflows, or saved PDF-to-decision behavior. Expand image-label audits and define observable field targets before a full extraction benchmark. `results/ocr-smoke/predictions.jsonl` retains raw OCR for this synthetic sample.

## Top-k retrieval diagnostic

See `results/retrieval/metrics.json` and [matching-review design](../docs/matching-review.md). A separate frozen `sentence-transformers/all-MiniLM-L6-v2` embedding model retrieved candidates; the selected pilot cross-encoder reranked them. All 36 simple queries retrieved their true product in the top five among 80 fictional products (also top one). This reused already-inspected test families, all queries were matchable, and no human review was conducted. It is not a fresh blind test or evidence of 100% real-world accuracy. No automatic-match policy has been enabled.

## Approximately 90% automatic pair coverage

[Coverage report](../docs/coverage90.md) records the changed target, threshold selection and a harder 720-pair synthetic challenge. The best tested checkpoint reached 94.6% accuracy among 648 automatic decisions (90% of 720); 72 pairs abstained. There were 2 wrong same-product and 33 wrong different-product decisions. This is an offline score-ranked batch diagnostic, not 90% invoice automation. The new challenge became development evidence after inspection; later results are not blind confirmation. Operational automation remains disabled. OCR is the next stage.
