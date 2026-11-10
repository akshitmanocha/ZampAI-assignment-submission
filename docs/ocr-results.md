# OCR and structured invoice extraction: measured first comparison

**Historical report.** The primary invoice benchmark is now [Indian GST invoices](indian-gst-evaluation.md). This document records the earlier InvoiceOCR-Synth experiment and its original scope; it does not describe current application completeness or the new benchmark's results.

Implemented a PDF-to-fields parser and an optional vision proposal adapter. This is not a completed upload-to-approval application. Source locations are retained; a model-proposed box is explicitly unverified.

## Pipeline

1. Validate PDF bytes, size and page limits.
2. Use native text on suitable text-only pages. Render sparse/image-bearing pages at 200 DPI and run Tesseract otherwise.
3. Group positioned words into rows, locate labels/columns, and parse invoice header and line items. Preserve monetary strings with Decimal normalization; no PO/master data is available to this parser.
4. Missing values stay missing; ambiguous dates, currencies and conflicting readings stay unresolved.
5. Optionally request a schema-validated vision proposal. Keep the original extraction and proposal separately. Conflicting header values become ambiguous; a new vision value requires source verification. Never recompute a missing printed value merely to match a PO or label.

The native/scanned reader, deterministic parser, local CLI, vision response schema/normalizer and recovery-merging logic are implemented and tested. The provider adapter is currently used only for the explicitly authorized public-data experiment; no private invoices were sent, and no public upload endpoint was opened.

## Data and independent evaluation

Source: [InvoiceOCR-Synth](https://huggingface.co/datasets/alamgirqazi/invoice-ocr-synthetic), author Alamgir Qazi, CC BY 4.0, pinned revision in the manifest.

Selected 24 base documents, four from each of six template families, after skipping the first 100 source records to avoid the earlier smoke examples. First two documents per family form development; the next two form holdout. Clean/faded/bad-scan variants stay in their document's split: 36 development images and 36 holdout images. The sample is small and stratified by template, not a representative commercial corpus. There are no INR examples or linked purchase-order histories.

The parser receives actual PDF bytes produced from each public image, not filenames, template IDs, expected fields, or PO data. Labels are used only by the evaluator. No LLM judge is used.

Local baseline was improved using development examples only, then frozen as x2-geometry-baseline-0.4 before its 36-image holdout run. Fixes cover multiline company titles, explicit FROM labels, invoice/PO references, dates below labels, date-vs-due-date columns, tax/net/grand totals, Value amount headings and intervening tax columns. All original benchmark outputs remain saved.

The free OpenRouter `nvidia/nemotron-3.5-super-vl:free` model was compared on a bounded subset: all 12 clean images plus faded/bad-scan versions of the first two selected documents in each split, 16 images per split. Every request contains one image only; a clean copy never helps read a degraded copy. Prompt changes and schema-format diagnosis used development examples; the holdout prompt was frozen before its run. Image preprocessing is JPEG quality 90 with max edge 2000, unlike the local PDF-render route; this compares extraction routes rather than isolating a single variable.

## Same-image holdout comparison

These are the **same 16 images from 12 holdout documents**, scored using unchanged publisher labels:

| Field | Local parser correct / non-null labels | Vision proposal correct / non-null labels |
|---|---:|---:|
| Supplier name | 2/16 | 16/16 |
| Invoice number | 7/9 | 9/9 |
| Invoice date | 8/16 | 15/16 |
| Currency | 12/16 | 12/16 |
| Grand total | 10/16 | 16/16 |
| PO reference | 0/1 | 0/1 |

Important denominator: vision also returned **three IDs on null-labelled invoice-number fields**, all from ticket/receipt templates (document/receipt references). Thus invoice-number proposal precision is **9/12 = 75%**, not 100%. Document-type/scope handling and reference-type verification are required before operational use. Do not turn every order/receipt number into an invoice number.

Currency values with a bare `$` remain ambiguous rather than becoming guessed USD. An ambiguous numeric date remains unresolved. PO-reference reading remains unproven; publisher fields may not be printed, but the heldout PO case has not been visually audited, so do not attribute that failure to the labels without checking.

| Row metric | Local | Vision |
|---|---:|---:|
| Complete description + quantity + amount | 17/28 | 27/28 |
| Complete row including unit price | 17/28 | 20/28 |

Rows are aligned by Hungarian assignment with description similarity >=0.85, but a true-positive row then requires exact normalized description and exact numeric values. Similar descriptions of different products do not count as correct. Identifier scoring preserves leading zeros and separators. Full report includes precision/recall/F1 rather than only correct counts.

On the declared invoice-template-only subset (10 images), vision read 16/16 complete labelled item rows, versus local 13/16. This is a small subset, not overall invoice accuracy. Among seven eligible images with all five header labels present, all five were correct on five images; the local route achieved one. Across all 16 images, seven of nine eligible images had all five critical fields correct under vision. Missing-label cases are reported separately, not counted as automatic successes.

## Label observability and why both row metrics matter

Manual development audits are in `ml/results/ocr-structured/label-audit.json`. A taxi receipt contains Item, Qty and Amount columns, with no separately printed unit price; its labels still supply unit_price. Inferring amount/quantity is not the same as extracting a printed field. Other layouts can truncate descriptions or omit schema fields. Original labels and strict scores are preserved; the description/quantity/amount metric is an additional diagnostic, not a replacement chosen to hide full-row failures. Full corpus and holdout visibility audits remain incomplete.

## Cost, latency and safeguards

- 33 free-model requests: one initial coordinate-format/schema failure, then 16 valid development and 16 valid holdout responses.
- Reported cost was zero for all requests with usage evidence; model catalog prompt/completion prices were zero. No paid model fallback configured.
- Provider access/quota/billing errors stop the experiment. Requests are bounded and credentials read from an external private file; no key committed or printed.
- Holdout median model request time: about 6.5 seconds; p95 about 15.8 seconds. These exclude the runner's pacing delay and are not complete application latency. Local matching-image median is recorded in the comparison JSON.
- Vision boxes are model-proposed, not independently verified bounding boxes. No IoU/grounding-accuracy claim.
- Amount arithmetic checks flag inconsistent proposals but never repair prices/amounts. Agreement between OCR and a model is corroboration, not proof.

## Reproduce and inspect

From repository root, the local path uses the installed application dependencies:

```sh
make install
uv run --project backend python -m reconcile.extract_cli /path/invoice.pdf --output /path/new-output.json
make test
```

Output must be a new file and is created privately. No external model is called by that CLI. The PDF reader must later run inside the resource-limited worker subprocess for untrusted uploads.

Benchmark tools in `ml/` use a separate evaluation environment with datasets/huggingface_hub plus the backend's PDF dependencies. See `evaluate_invoice_extraction.py`, `evaluate_vision.py`, and `compare_extraction.py`. `evaluate_vision.py` requires an explicitly supplied private key-file path and only uses the fixed free model; do not put credentials in commands or Git. Current authorization covers the public synthetic corpus only.

Canonical current results: `ml/results/ocr-structured/comparison-heldout.json`. Earlier raw reports are retained with their original metric definitions; the comparison applies the stricter v2 metrics consistently to both engines. Prompt/schema, source manifest, selected images, usage, predictions, error cases, and code hash are saved.

## Remaining work

Audit source visibility more broadly, add document-type/reference-type verification, evaluate real supported INR layouts, resolve date conventions through explicit business configuration, and test row wrapping/multipage/discount handling. Then integrate extraction, source verification, matching, rules, saved jobs and review screens. Neither 90% invoice automation nor production-safe acceptance follows from this small extraction benchmark. The application remains fail-closed and reports incomplete readiness.
