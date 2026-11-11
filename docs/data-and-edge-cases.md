# How we prepared the data and checked the app

We checked three tasks separately: reading invoices, finding matching products,
and deciding whether an invoice follows the company's order rules.

## How we prepared the data

**Invoice reading:** We used [Divya52's Indian GST dataset](https://huggingface.co/datasets/Divya52/indian-gst-invoices), containing **2,000 synthetic invoices**. Each image already comes with an answer file containing its correct fields and item rows. We kept these publisher answers unchanged; Nemotron did not create the labels.

We selected examples across four layouts and three image conditions: clean,
scanned and photographed. We used **24 training examples to develop parsing
rules**, **60 validation examples to compare readers**, and **130 other validation
examples to examine confidence scores**. We evaluated all **197 publisher test
invoices**. Another 24 adversarial and 40 Hindi/Kannada documents were checked
separately. We did **not fine-tune the live OCR or MiniLM models**.

**Product matching:** We created a fictional catalog of **80 products** and
**36 search queries**. Each query's intended product ID supplied the correct
answer, so we could check whether MiniLM retrieved that product.

**Business decisions:** The public invoices have no verified purchase-order or
approval history. We therefore authored realistic invoice PDFs and company order
records, then wrote expected outcomes from those facts **before running the
checks**. For example, an order for 1,000 items with 400 already approved leaves
600. The model did not choose its own correct answers.

## Results

| Measurement | Result | Meaning |
|---|---|---|
| Five key invoice fields | **90.5% recovered correctly** | 891 correct values out of 985 expected values. |
| Correctness of proposed field values | **98.0%** | 891 correct values out of 909 values the reader supplied. |
| Complete item rows | **85.0% F1** | A combined score that penalizes incorrect, missing and extra rows. |
| Product search pilot | **36/36 queries** | The correct product appeared within the top five suggestions. |

## Edge cases we checked

| Situation | Observed behavior |
|---|---|
| Six boxes, but no items-per-box information | **Human review.** Approval stays blocked until supporting pack information is supplied. |
| One price too high and another too low, leaving the total unchanged | **Hold.** Both item-price errors are caught. |
| Only 600 items remain on an order | **600 passes; 700 is blocked.** Two competing 400-item approvals cannot both succeed. |
| Same invoice resent in a different PDF layout | **Duplicate blocked.** Another supplier's same invoice number is allowed; a changed total goes to revision review. |

**All 11 application checks passed:** nine variants across these four edge cases,
plus a normal invoice and an image-only scan. These ran through actual upload,
processing and saved decisions, with review/approval actions where relevant.

The scan misread `EA/box` as `EAbox` and correctly went to human review. A
simulated reviewer correction recovered the expected result while preserving the
original reading; that correction is not counted as correct OCR.

These are synthetic, known examples. The invoice test was already inspected and
later re-scored. The results do **not** prove 100% future accuracy or 90% automation.

Saved evidence: [invoice scores](../ml/results/indian-gst/baseline-v4-ppocr/metrics.json),
[product search](../ml/results/retrieval/metrics.json),
[edge-case expected and actual results](../ml/results/code-review-v1/submission-edges/report.json).
