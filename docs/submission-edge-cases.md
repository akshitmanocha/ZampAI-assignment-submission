# Four submission edge cases, checked against the actual application

The candidate guide's PS-1 asks for 2–4 realistic edge cases and a working
PDF-to-decision process. This focused acceptance run covers four families with
nine edge/control variants, plus a happy-path control and an image-only scan:
**11 checks in total**. Expected outcomes were written before running this suite.

The existing fictional invoices and company facts are known development fixtures.
These are application acceptance checks, not a new held-out model benchmark.
The guide PDF stays outside the repository.

## The four cases

| Case | Why a simple solution can fail | Expected and observed behavior |
|---|---|---|
| **Six boxes, no pack size** | A purchase order counts individual gloves; “six boxes” does not say how many gloves there are. | **Human review**, with approval blocked. A simulated reviewer supplies separately verified 100-EA-per-box evidence; a new decision becomes ready. Original extraction stays unchanged. |
| **Correct total, wrong prices** | The order says 200 bolts at ₹12.50 and 200 nuts at ₹4. An invoice bills ₹13.50 and ₹3 instead. Both totals are ₹3,300, so a total-only check misses both errors. | **Reject/hold**. Both line-price errors are identified: +₹1 per bolt and −₹1 per nut. The agreed-price control is ready. |
| **Partial bills consume the same order** | An order contains 1,000 items, of which 400 are already approved. Comparing only with the original 1,000 would wrongly allow a bill for 700. Two bills can also compete for the same remaining balance. | A bill for **600 passes**; **700 is held**, with an excess of 100 and no ledger change. Two simultaneous bills for 400 cannot both approve: one succeeds, the other is blocked and receives a new rejection recommendation. Exactly 200 remain. |
| **Duplicate despite different PDF bytes** | A supplier can resend the same invoice using a different layout; file hashes alone miss it. Conversely, two suppliers can legitimately use the same invoice number. | Same supplier, exact invoice number and total in another PDF layout: **duplicate hold**. Another supplier using the same number: **passes duplicate checking**. Same supplier/number with a changed total: **human review for a possible revision**, rather than treating it as a proven duplicate. |

All nine assertions across these four families passed. The happy path also passed:
six explicitly labelled 100-item boxes normalize to 600 items, and authorized
approval reduces the remaining balance from 600 to zero.

## What happened with a real scan

The image-only control actually used **PP-OCRv5 mobile**, not native text or a mock.
It read the printed `100 EA/box` as `100 EAbox`. The description's minimum word
score was about **52.2**, below the current source-review threshold of 60.

The app preserved that reading and recommended **human review**. A simulated
reviewer restored the exact printed description; revalidation became ready and
the original reading remained unchanged. This test passes because the uncertain
reading was handled appropriately. The correction is **not** counted as correct
OCR or as independently measured human-review accuracy. High-confidence errors
can still occur on other documents.

## How the labels and checks work

- Correct answers come from explicitly authored invoice/order facts and arithmetic,
  not MiniLM, Nemotron, the OCR output or the production recommendation function.
- These tests send actual PDFs through authenticated upload, the durable background
  worker, extraction/source checks and saved decisions. Review and approval actions
  use the authenticated API. The concurrent case checks actual ledger effects.
- Every test starts in its own migrated PostgreSQL schema. Schemas are removed
  afterward; ordinary application documents and balances are untouched.
- Each test checks specific reasons, quantities, price deltas, preserved originals
  or approval results, rather than only checking the final bucket.
- JUnit records expected and observed evidence. The runner also checks that the
  test image's production source files match the checkout before running.

These cases exercise deterministic product identity from printed SKUs; they do
not measure MiniLM semantic-retrieval quality. Nine related edge checks are not
nine independent real-world invoices. **11/11 passing does not establish 100%
production accuracy or a representative automation rate.** No OCR model or policy
threshold was changed to obtain these results.

## Evidence and reproduction

Saved result: [report.json](../ml/results/submission-edges-v1/report.json).
Latest verification after code review:
[reviewed report](../ml/results/code-review-v1/submission-edges/report.json).
Tests: [test_submission_edge_cases.py](../backend/tests/test_submission_edge_cases.py).

With the local database running and a current test image:

```sh
make submission-edge-test
# Or choose an artifact destination:
backend/.venv/bin/python scripts/evaluate_submission_edges.py \
  --output /tmp/reconcile-submission-edges-v1
```

If an image has not been built yet, use `docker compose --profile test build test`
first. The evaluator never builds or resets the ordinary company automatically.
It refuses a mismatched production image, skipped checks, missing evidence or an
incomplete set. Outputs include `report.json`, `junit.xml`, runtime provenance and
`demo-inputs.zip` with fictional PDFs and a short run guide. `run-inputs.json`
freezes original source hashes and the JUnit digest. `--from-junit` requires that
paired metadata and preserves the original run's identity; it never assigns
current source hashes to an old test result.

For the interview, show the happy path first, then one or two of these cases.
Check the current ledger before rehearsing: approval changes balances, and these
tests deliberately isolate their contexts. The downloadable PDFs are not a
single batch that should all be approved in the same company.
