# Small-model OCR upgrade evidence

`model-assets.json` audits model size/revisions and the selected ~3.1M stored-value PP-OCRv5 English mobile detector/recognizer. SHA-256 weight pins are in `reconcile.ocr_models`; weights remain outside Git. There was no fine-tuning.

`selection-v2-pdf-coordinates` contains the complete 24-image training debug report, 60-image reader selection, 130-image calibration, and twelve-image CPU qualification. The parser/OCR ablation uses the original parser from commit `12a8dd4` and the current GST parser on identical cached OCR pages. `original_parser.py` is an exact frozen copy for reproducibility; its hash matches the original baseline component. Publisher labels join only after parsing.

`gpu-qualification-v2-pdf-coordinates` contains all twelve predeclared images for each corrected GPU candidate, including incomplete generations. Original source-image copies embedded by Docling are omitted from the exported JSON; text, table structure and proposed coordinates remain. Full source exports are outside Git with hashes recorded. VLM proposals and inferred layout locations always require source review; they are not a calibrated automatic policy. Initial invalid precision/API/decoding probes are not treated as valid quality scores. Completed outputs were checkpointed before the first Kaggle session expired and missing identities resumed on the new session.

The current official 197-image re-score and the separate 24/40 robustness reports are under `ml/results/indian-gst/baseline-v4-ppocr`. The original baseline remains under `baseline-v2`. See [the plain-language upgrade report](../../../docs/ocr-upgrade.md) and [main methodology](../../../docs/indian-gst-evaluation.md). No experiment establishes production invoice approval accuracy or 90% invoice automation.

See `report-notes.json` for an explicit clarification of the inherited no-test-guided-fixes caption in the raw harness reports. The coordinate repair followed an inspected-test re-score; this upgrade makes no untouched-test or production-accuracy claim.
