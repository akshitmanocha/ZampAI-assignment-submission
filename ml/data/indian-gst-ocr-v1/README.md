# OCR development selection

Source: Divya52/indian-gst-invoices, CC BY 4.0, exact revision and publisher metadata hash in `manifest.json`. Publisher images and structured labels are unchanged; originals stay outside Git. Run `PYTHONPATH=backend uv run --project backend python ml/prepare_ocr_development.py` from the repository root after `make invoice-data`.

The frozen selection contains 24 source-training examples for parser development, 60 source-validation examples for reader selection, and the remaining 130 validation examples for calibration/diagnosis. Selection sorts IDs within four layout × three quality strata. The twelve common qualification IDs are a subset of the 60 model-selection examples. All IDs, image bytes and raw label strings are hash-pinned. No official source-test invoice enters these groups.

This is development evidence, including known validation examples from prior source-visibility inspection. It is not an independently audited or unseen real-invoice corpus. The official 197-image test was inspected in the previous baseline and its new score is explicitly reported as a re-score. The labels do not provide authoritative company PO/approval history or catalog identity labels.
