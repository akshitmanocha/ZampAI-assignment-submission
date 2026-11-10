# Local demo and narration

Start with `make local` and the private account file. Use the approver account. These are fictional documents and company facts. The application never moves money.

For a repeatable automated rehearsal without changing the main company's ledger, use `make browser-test`. It starts a disposable company on port 18000, executes the live journey, and removes that schema afterward. The main workspace on port 8000 keeps its history. For a candidate-recorded narrated video, use a fresh demo company and the outline below; the automated test screenshots are validation evidence, not a narrated submission video.

## Five-minute walkthrough outline

1. **Purpose and dashboard, about 30 seconds.** “This workspace checks supplier invoices against orders and previously approved quantities. It explains its recommendation and keeps the source document. Approval is a separate staff action.” Show the invoice activity filters and order ledger.
2. **Happy path, about 60 seconds.** Process the six-box sample. Show the real native-text run, source row highlight, 100 gloves per box, normalized 600 gloves, and the 1,000 ordered minus 400 approved balance. Approve once. Open the ledger: remaining quantity is zero. Explain that retrying approval cannot allocate twice.
3. **Missing packaging evidence, about 75 seconds.** Process missing-pack against PO-0148. Show Needs review and the missing conversion. Enter verified pack factor 100 and a reason referencing supplier evidence. Save and watch revalidation skip OCR while rerunning the rules. Show decision versions and the unchanged original reading. Do not claim the system inferred the missing pack size.
4. **Semantic matching, about 60 seconds.** Process the differently worded gloves sample against PO-0151. Show MiniLM's candidate, its similarity score and the None of these option. Explain that the score retrieves candidates; the reviewer verifies identity, and price/quantity checks still run. Confirm the matching product and recheck.
5. **One confirmed violation and limits, about 45 seconds.** Process the offset-prices sample. Both item prices are wrong despite an unchanged total. Show both deltas. Close by explaining supported scope and that synthetic test success does not guarantee accuracy on unfamiliar invoices.

A scanned sample and competing partial invoices are prepared for follow-up questions. For the partial case, process A and B before approving either. Both initially fit 600 remaining. Approve A (400); B's approval must recheck, produce a new hold decision, and leave 200 remaining. Use PO-0150, separate from the happy path.

Sample PDFs are ordinary inputs. The pipeline never reads their names, scenario descriptions or expected answers. Reusing an already-uploaded PDF is deliberately detected as a duplicate; the sample list warns that results depend on the ledger's current state.
