> Historical milestone. The local application now integrates upload, retrieval, review and approval; see [current implementation](local-application.md). Scores and limitations below describe the original experiment.

# OCR stage: first actual PDF reader

The 90%-coverage matching comparison is documented separately in coverage90.md. OCR work has now started.

`backend/reconcile/document_text.py` reads PDF bytes, validates basic PDF size/page limits, and returns page-level words with bounding boxes. Native text is used on sufficiently populated text-only pages. Sparse or image-bearing pages are rendered at 200 DPI and processed with actual Tesseract OCR, preserving source coordinates. Native words have no invented confidence; OCR words retain the engine's score, which is not a correctness probability. Pages without readable OCR are marked with a warning.

Four initial tests passed: real native PDF reading, real OCR of a generated scanned PDF, invalid/oversized inputs, and page limits. These are functional smoke tests on one fictional invoice layout, not an extraction-accuracy benchmark. The PDF reader is not exposed through an upload endpoint and must later run in the planned resource-limited worker subprocess for untrusted files.

The image-bearing-page rule is intentionally conservative: it OCRs even pages containing only a logo plus native text. Improve the layout/image-area policy only after measuring correctness and latency on mixed pages. Extraction/field parsing is still a separate task; raw word recovery does not prove correct invoice-field attribution or line-item reconstruction.

Next: audit image-to-label observability for the public dataset, expand clean/faded/bad-scan cases, implement structured fields/rows with source evidence, and report critical-field accuracy and row precision/recall. The original 12-image public OCR smoke scores remain a diagnostic, not the new parser's benchmark.

## Structured extraction and free-model comparison added

See [measured OCR results](ocr-results.md). The parser/CLI now extracts source-linked headers and table rows; an optional OpenRouter Nemotron vision proposal adapter was evaluated on public synthetic data. Baseline, improved development, independent holdout, same-image model comparisons and label-audit findings are saved. This remains a standalone extraction capability, not a completed upload/worker/review workflow.
