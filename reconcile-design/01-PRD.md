# 01: Product requirements: Reconcile

Names, states, routes and numbers come from `03-CONTRACTS.md`. Requirement and acceptance IDs (G-, U-, AC-) are traced in `00-START-HERE.md` §4.

---

## 1. What we are building, in one paragraph

An AP specialist uploads a vendor invoice PDF. Reconcile shows the original document beside each processing stage as it runs. It reads the invoice, digital or scanned, finds the vendor and purchase order, matches each billed line to a PO line, and runs deterministic money checks. It then recommends one of three outcomes:

- **Ready for approval**
- **On hold**: a confirmed problem
- **Needs review**: a question only a person can answer

Every recommendation comes with evidence and a next action. An approver approves against the **current** PO balance, and the approval is atomic. Every reading, correction, decision and approval is kept and viewable in history. Reconcile never pays anyone.

**Product hypothesis** (stated as a hypothesis, not a claim): a procurement-specific line matcher with deterministic checks clears clean invoices automatically. It also makes holds that a total-only check would miss, such as offsetting price errors. Reconcile is evaluated on realistic invoice variations; see `04`.

---

## 2. Process map

This is the map the guide asks for before build (G-14, guide p. 6 "Map the process on paper before you build anything").

```
INPUT: invoice PDF (digital or scanned), uploaded by an AP specialist
       + vendor master + open POs with approved balances + versioned AP policy
  │
  ├─ 1. Intake ── D1: Is it a PDF ≤ 10 MB and ≤ 10 pages, not encrypted?
  │                   no → rejected at upload with a reason (nothing stored)
  ├─ 2. Read text ── D2: Does each page have a text layer?  no → 3. OCR that page
  ├─ 4. Extract fields + lines, each with page/box evidence
  │                   D3: Are invoice no., date, total and lines found?  no → open question
  ├─ 5. Normalise: decimals, dates, units, pack sizes, tax-inclusive prices
  ├─ 6. Vendor ── D4: Known? Approved?   unknown → question · blocked/mismatch → hold
  ├─ 7. PO ────── D5: PO printed? Same vendor? Open?  missing → infer if unambiguous
  ├─ 8. Lines ─── D6: Which PO line is each row? Same spec? Unit conversion evidenced?
  ├─ 9. Checks: price tolerance · quantity & amount vs remaining · arithmetic · tax · totals · duplicates
  ├─ 10. Decide ─ D7: any blocker → On hold; else any open question → Needs review; else Ready
  └─ 11. Save decision v1 + show it
OUTPUT: recommendation + findings with evidence + next action
  │
HUMAN: answer questions / correct readings → re-check (new decision version)
       approve → D8: still valid against the CURRENT PO balance?
                 yes → allocate (ledger updated) · no → On hold, nothing allocated
       or reject (with reason)
```

---

## 3. People, current workflow and bottlenecks

| Person | Goal | Today (manual) | Bottleneck | What Reconcile changes |
|---|---|---|---|---|
| **AP specialist** (role `clerk`) | Turn each invoice into a correct "pay / don't pay / ask" in minutes | Opens the emailed PDF, searches the PO spreadsheet, re-keys numbers, eyeballs totals, emails the vendor | Re-keying, PO lookup, unit conversions and tired-eye errors (guide p. 3: "a tired person on a Friday afternoon makes expensive mistakes") | Readings with evidence, PO candidates, line-by-line checks, explicit questions |
| **AP approver / finance controller** (role `approver`) | Approve only what the PO still authorises; never double-pay | Trusts the specialist's spreadsheet; no live balance | Two invoices against one PO approved the same day; duplicates | Approval re-checks the current balance atomically; duplicate holds |
| **Evaluator** (Zamp interviewer) | See that the process runs, handles messy inputs and is explained clearly | — | — | A live hosted run view, a dashboard and prepared edge cases (G-05…G-09) |

---

## 4. Key concepts, with one worked example

This is the SafeHands example (contracts §5.2).

| Concept | Plain meaning | Example |
|---|---|---|
| **Purchase order (PO)** | The buyer's prior authorisation to buy specific items at agreed prices | PO-2026-0147 line 1: 1,000 medium powder-free nitrile gloves at ₹5.00 each (net of GST) = ₹5,000.00 |
| **Invoice** | The vendor's bill | SafeHands SH/2526/0912: 6 boxes, "Box of 100 gloves", ₹500.00/box = ₹3,000.00 + GST ₹540.00 = ₹3,540.00 |
| **Remaining authorised balance** | What is left on the PO line after earlier **approved** invoices | 400 gloves already approved ⇒ 600 gloves / ₹3,000.00 remain |
| **Recommendation** | Reconcile's suggestion. It changes no balance. | 6 × 100 = 600 gloves at ₹5.00 ≤ 600 remaining ⇒ **Ready for approval** |
| **Human approval** | An approver commits the invoice. The system re-checks the *current* balance and reserves it in one step. | Approve ⇒ PO line 1 approved 400 → 1,000; remaining 0 |
| Counter-examples | | 7 boxes = 700 gloves ⇒ **On hold** ("exceeds remaining by 100"). No pack size printed ⇒ **Needs review** ("How many gloves per box?"). "Latex" instead of nitrile ⇒ **On hold** (specification conflict). |

---

## 5. Scope

### 5.1 Release (must ship)

- Upload one PDF at a time.
- Native text extraction, with local OCR fallback per page.
- Header, line and total extraction with page/box evidence.
- Deterministic normalisation.
- Vendor and PO resolution, with inference when unambiguous.
- Line matching (B0 baseline).
- The full rule matrix (contracts §4.1) and the three-way recommendation.
- A versioned decision history.
- Controlled corrections that trigger a re-check.
- Atomic approval with stale detection.
- Reject.
- Retry after a technical failure.
- Dashboard and history.
- Invoice detail (evidence, findings, line matches, ledger, runs, audit).
- PO ledger panel.
- Role-based access.
- Hosted at a $0 URL.
- Demo reset.

### 5.2 Conditional (ship only if its gate passes)

| Item | Gate |
|---|---|
| E1 fine-tuned matcher in the live app | Wins on validation per `04` §3.6 **and** hosted memory/latency check passes by ML adoption cutoff (Wed 11 Nov 15:00 IST) |
| E2 focused re-read of low-confidence fields | Bake-off shows critical-field gain on scans with no increase in false fills |
| Benchmarks page (saved results) | Evaluation artefacts exist by Wed 11 Nov 16:00 IST |
| Separate PO ledger page | Time remains after the gate set in `05` (otherwise ledger lives in the invoice detail) |

### 5.3 Deferred (explicitly out)

- Email/mailbox ingestion. Upload stands in for the AP mailbox (A-01).
- Payment execution and ERP posting.
- Three-way match with goods receipts.
- Multi-PO invoices.
- Credit notes.
- Hold overrides.
- Approval reversal/void.
- Segregation-of-duties enforcement.
- Master-data unit conversions.
- GSTIN checksum validation.
- Multi-currency, multi-entity and multi-tenant setups.
- Non-English documents.
- Freight and discount allocation.

### 5.4 Input conditions: what happens to each

| Guide condition (p. 3) | Release behaviour | Path |
|---|---|---|
| Clean native-text PDF | Automated | — |
| Scanned image PDF | OCR (Tesseract) per page without text. Low-confidence critical fields are `ambiguous`. | Ambiguous → **Needs review** with the image region highlighted |
| Mixed (some pages scanned) | OCR only for pages lacking text | — |
| Itemised lines | Automated | — |
| Bundled/summary line ("Supplies as per PO, lot 2") | Not matchable to PO lines | **Needs review**: "ask for an itemised invoice" (R-LINE-03) |
| Several rows → one PO line | Automated (quantities aggregated) | — |
| One row covering several PO lines | Unsupported | **Needs review** (R-LINE-03) |
| Tax separated (CGST+SGST / IGST) | Automated arithmetic checks | — |
| Tax embedded (inclusive) **with** stated rate | Net derived, with evidence | — |
| Tax embedded **without** rate | Cannot derive net | **Needs review** (R-TAX-03) |
| PO reference explicit | Automated | — |
| PO reference implied/absent | Inferred only if one open PO of that vendor clearly fits; shown as "inferred" | Ambiguous → **Needs review** with ranked candidates |
| PO reference conflicting (another vendor's PO) | Confirmed blocker | **On hold** |
| PO not found | Possibly a typo or OCR error | **Needs review** |
| Several POs referenced | Unsupported | **Needs review** (R-SCOPE-02) |
| Missing invoice number / date / total | The value stays missing; dependent checks are marked "waiting" | **Needs review**, with an input box |
| Vendor not in master | — | **Needs review** (choose a vendor or onboard first) |
| Vendor blocked / GSTIN mismatch | Confirmed blocker | **On hold** |
| Price close but not exact | Tolerance `max(₹0.05, 1 %)` per PO unit, net. Configurable demo policy. | Over tolerance → **On hold** |
| Split invoicing (several invoices per PO) | Ledger allocations. Each approval re-checks the remaining balance. | Exceeds remaining → **On hold** |
| Duplicate (same vendor + number) | Confirmed blocker | **On hold** |
| Same number, different vendor | Not a duplicate | — |
| Same vendor, date and total, different number | Possible re-issue | **Needs review** |
| Same file uploaded twice | Confirmed blocker | **On hold** |
| Pack vs unit ("box of 100" vs per glove) | Converted only with printed evidence or a reviewer attestation | Missing → **Needs review** |
| Non-INR, credit note, > 50 lines, freight, invoice-level discount | Unsupported in release | **Needs review** with "process manually" |
| Encrypted / not a PDF / > 10 MB / > 10 pages / 0 pages | Rejected at upload, with an exact reason; nothing stored | Error message |
| Text in the PDF that tries to instruct the system | Treated as data. No effect on the decision (REG-08). | — |

Tolerances and tax arithmetic are **demo policy** (`policies/demo-ap-policy-2026.11.1.yaml`), not tax advice (A-08).

---

## 6. User stories and acceptance criteria

Each criterion is observable in the UI or API. Fixture IDs come from `04` §4.

| ID | Story | Acceptance criteria |
|---|---|---|
| **US-01 Upload** | As an AP specialist I upload an invoice PDF and immediately see it being processed. | (a) Drag-and-drop or picker, PDF only; limits shown ("PDF, up to 10 MB, 10 pages"). (b) Valid upload returns within 2 s (target) and opens the live run view at **Queued** or a running stage. (c) Invalid files show the exact contracts §3.7 message and create no invoice. (d) A double-click or network retry with the same `Idempotency-Key` creates exactly one invoice. |
| **US-02 Live stages** | I watch each real stage as it runs. | (a) 11 stages in contracts §2.4 order, each showing pending / running / done / skipped / failed, with duration and a one-line summary from real events. (b) No stage shows done before its `stage.completed` event exists. (c) OCR shows "skipped — not needed" for native PDFs and "Reading page k of n" for scans. (d) Queue position is shown while queued. |
| **US-03 Evidence** | I see where every value came from. | (a) Every reading lists raw text, the normalised value and evidence. (b) Clicking a value or finding highlights its box on the original PDF page. (c) Values from a reviewer show "Supplied by {user}, {reason}". (d) Values assumed by policy (e.g. INR when no currency is printed) are labelled "Assumed by policy". |
| **US-04 Decision** | I get a clear recommendation with reasons and a next action. | (a) The banner shows one of three recommendations, the summary sentence and the next action. (b) Findings are grouped **Blocking**, **Needs your input**, **Passed checks** (collapsed, count shown) and **Notes**. (c) Each finding shows expected / actual / difference / tolerance with units. (d) Line table: invoice row ↔ PO line, conversion (e.g. "6 Box × 100 = 600 gloves"), price per PO unit, remaining before/after. |
| **US-05 Confirmed discrepancy** | When something is wrong I know exactly what to tell the vendor. | On hold, the next action names the vendor-facing ask (e.g. "Ask Kaveri for a corrected invoice at PO prices"). Approve is disabled with a reason. Reject is offered with a reason box. |
| **US-06 Missing evidence** | When something is missing I can answer it in place. | Each `review` finding renders a control: a text/date/number box, a pack-size box, a PO-line chooser listing candidates with the differing attribute highlighted, or a vendor chooser. A **reason is required**. "Save & re-check" queues a revalidate run and shows its live stages. |
| **US-07 Controlled correction** | I can correct a misread value without losing the original. | (a) Edit on any reading shows the original struck through, the new value and the reason. (b) The original reading is unchanged in the API. (c) The approval screen shows "n values corrected by …". (d) Vendor/PO/policy data cannot be edited (422). (e) A PO line flagged as a spec **conflict** cannot be chosen. |
| **US-08 Re-run after failure** | If processing fails I can retry without re-uploading. | (a) Processing failed shows error code, attempt count and "Your file is saved". (b) Retry creates run n+1. (c) The failed run stays in history. |
| **US-09 Approval** | As an approver I approve against the current PO balance. | (a) Approve is visible only to approvers and only on **Ready for approval**. (b) The confirmation shows the reservation ("Reserve 600 gloves / ₹3,000.00 on PO-2026-0147 line 1"). (c) On success the ledger panel shows before → after, and the status becomes **Approved**. (d) If the balance changed, the stale banner appears before clicking. On 409 the UI shows the new **On hold** result and that nothing was reserved. (e) A repeat click never double-allocates. |
| **US-10 Unauthorised** | People only do what their role allows. | (a) Signed-out users see the login page, and API calls return 401. (b) A clerk sees no Approve button; a forced call returns 403 with "Your role (AP clerk) can't approve invoices." (c) A session expiry mid-task shows "Session expired — sign in again", and the form state is kept. |
| **US-11 History & dashboard** | I can find any invoice and see what happened. | (a) Tiles: Ready, On hold, Needs review, Processing, Failed, Approved (today / all). (b) Table: ref, vendor, invoice no., date, PO, net, gross, status pill, last run, updated, with filters for status/vendor/date and search by number. (c) Rows with an active run show a live stage indicator. (d) Seeded rows are labelled **Seeded history**. (e) Detail tabs: Decision · Readings · Runs (each run, versions, events) · **Decision history** (every version, including approval-check versions that have no run) · Audit. |
| **US-12 Ledger** | I can see a PO's authorised, approved and remaining amounts. | The ledger panel/page lists each PO line: ordered, approved (with linked invoices), remaining (qty and ₹). Values come from the API, not client maths. |
| **US-13 Reject** | I can reject an invoice with a reason. | The status becomes **Rejected**. A rejected invoice no longer counts for duplicate checks. The reason appears in the audit. |
| **US-14 Saved vs live** | I can tell saved results from live processing. | Benchmarks and seeded history carry a "Saved" label and timestamp. Only the live run view animates. |

---

## 7. Interface specification

### 7.1 Navigation

The top bar shows the **Reconcile** wordmark and four links: **Invoices** (dashboard), **Purchase orders**, **Benchmarks** and **About** (assumptions log A-01…A-12, data notice, how AI is used). **Upload invoice** is the primary button. The upload dialog also offers **Sample invoices**: six committed fixture PDFs, served via `GET /api/samples` and each with a one-line "expected in the seeded state" note. Evaluators can therefore run the link without bringing their own PDFs. The user menu shows name, role badge and sign-out. Where `DEMO_MODE=true`, a slim banner reads: *"Demo environment — synthetic data only. Do not upload real invoices."*

### 7.2 Live run view (`/invoices/{id}`, while the latest run is active)

- **Left (60 %).** The original PDF (pdf.js), with page controls and a zoom of 100–200 %. Evidence boxes are overlaid; hovering a value highlights its box. For scans, a badge reads "Scanned — read by OCR (confidence 87 %)".
- **Right (40 %).** A vertical stage timeline with the 11 stages. Each stage has an icon and text (never colour alone), its duration and a summary. Readings appear progressively as stages finish:
  - field_extraction → the fields table
  - line_match → the line table
- **Header.** `RC-000004 · SafeHands_SH-2526-0912.pdf · Run #1 · started 14:32:11 IST · 00:04 elapsed`.
- **Polling.** `GET /api/runs/{id}?after_seq=` every 1 s while active and every 5 s when the tab is hidden. It stops on a terminal state.
- **Freshness.** The review view re-fetches the invoice on window focus and every 10 s while it is Ready for approval, so the stale banner appears in a second tab without a reload (contracts §2.3).

### 7.3 Review view (same route, run terminal)

- **Decision banner.** Status pill, summary sentence, next action and primary actions:
  - Ready: **Approve** (approver) · **Reject**
  - On hold: **Reject** · **Re-check** (a review with no corrections; useful after a duplicate was rejected or master data changed) · Approve disabled ("Fix the blocking problems first")
  - Needs review: **Save & re-check** (enabled once each question has a value and a reason) · **Reject**
  - Processing failed: **Retry processing**. Approve is disabled even if an older Ready decision exists: "The latest re-check failed; retry first."
- **Findings panel** as in US-04. **Line table** as in US-04. **Ledger panel** shows per assigned PO line: ordered · approved · remaining · this invoice · after approval.
- **Tabs:** Readings (with Edit) · Runs · Audit.

### 7.4 Copy

| Situation | Exact copy |
|---|---|
| Ready | "**Ready for approval.** {summary} — Approving re-checks the current PO balance." |
| On hold | "**On hold — {n} problem(s) must be fixed before this can be paid.** {top message}" |
| Needs review | "**Needs review — {n} question(s) need an answer.**" |
| Stale | "The PO balance changed after this check (another invoice was approved {time}). Approving will re-check against the current balance." |
| 409 stale result | "**Not approved.** Only {r} {unit}s remain on {po} line {k}; this invoice bills {q}. Nothing was reserved. New result: On hold." |
| Queued | "Waiting for the processor — position {k}. You can leave this page; processing continues." |
| Processing failed | "We couldn't finish processing this invoice ({code}, attempt {a} of {max}). Your file and earlier results are saved." |
| Empty dashboard | "No invoices yet. Upload a PDF to see Reconcile check it against your purchase orders." |
| Upload error | Contracts §3.7 message + "Nothing was saved." |
| Network error | "Can't reach Reconcile. Retrying…" (auto-retry with backoff; manual **Retry** after 3 failures) |
| 403 | "Your role ({role}) can't {action}. Ask an approver." |
| 401 | "Your session ended. Sign in again — your changes on this page are kept." |
| Cold start (first load) | Platform-dependent; the submission email warns that "the first load can take about a minute" (02 §8.2) |

### 7.5 States checklist (each demonstrable; AC-29)

loading (skeletons) · queued · running · empty · upload-error · network-error/retry · processing-failed/retry · terminal (3 recommendations) · stale · 409-stale-result · approved · rejected · 401 · 403 · read-only (clerk viewing Ready).

---

## 8. Non-functional acceptance

"Target" means not yet measured. Codex records the observed value in the progress log; see `05` §5.

| Area | Criterion | Target / measure | Evidence |
|---|---|---|---|
| Correctness | All named fixtures produce exactly the expected recommendation and the expected findings (rule, subject, outcome, effect) | 100 % of fixture manifest (`04` §4) | `pytest tests/fixtures_e2e` (AC-06…AC-11) |
| Money safety | No `ready_for_approval` on any fixture whose expected result is hold or needs_review | 0 unsafe clearances on named fixtures; report rate + 95 % upper bound on generated set | `04` §2.4 |
| Ledger | `allocated_qty ≤ ordered_qty` under 20 concurrent approval races; Σ allocations = `allocated_qty` | 20/20 runs | `tests/concurrency` (AC-08) |
| Traceability | Every non-null reading has ≥ 1 evidence; every finding has rule/version/expected/actual; every decision has all versions stamped | 100 % (DB invariant test) | AC-12 |
| Durability | Uploaded PDF, readings, decisions and approvals survive a container restart, byte-identical (sha256) | Pass on hosted | AC-12, AC-15 |
| Recovery | Killing the worker mid-run finishes on attempt 2 with exactly one decision | Pass locally and on hosted | AC-13 |
| Latency (ack) | Upload → 202 | p95 ≤ 2 s local; hosted unmeasured target ≤ 3 s warm | `latency-report` |
| Latency (native) | HP-01 queued → completed | Local target ≤ 5 s; Render Free (0.1 CPU) target ≤ 20 s, **unmeasured** | AC-26 |
| Latency (scan) | SC-01 queued → completed | Local ≤ 20 s; Render Free ≤ 90 s, **unmeasured**. If above, demo SC-01 from saved history and say so. | AC-26 |
| Accessibility | Keyboard-only path upload → approve; visible focus; status by text + icon; `aria-live="polite"` stage updates; contrast ≥ 4.5:1 | WCAG 2.2 AA target; axe DevTools: 0 serious/critical on 4 views (unmeasured) | AC-25 |
| Demo readiness | Hosted run sheet executes twice cleanly after a demo reset; video ≤ 5:00 | 2 clean rehearsals | AC-18, AC-16 |

---

## 9. Acceptance scenarios and owners

**RA-01 (main release acceptance).**
1. Start from a fresh browser on a different network from the build machine.
2. Open the hosted URL and sign in as the approver.
3. Upload `SafeHands_SH-2526-0912.pdf`.
4. Watch all 11 stages complete. OCR shows as skipped.
5. Check that the result is **Ready for approval**, with conversion evidence "Box of 100 gloves" highlighted.
6. Approve. The ledger for PO-2026-0147 line 1 goes from 400 → 1,000 approved, with 0 remaining.
7. Check that the dashboard shows the invoice as Approved, with run #1 and decision v1 in history.
8. Restart the service. All of the above persists.

Owner: Codex (build and evidence), then the candidate (re-run in rehearsal). Evidence: AC-02, AC-03, AC-05, AC-12, AC-15.

| Acceptance ID | Scenario family | Expected visible outcome | Build owner | Demo owner |
|---|---|---|---|---|
| AC-06 | F1 packaging/spec (EC-01b, -01b-ctl, -01c, -01d) | needs_review → after "100 per box" → ready; control ready; latex → hold; 7 boxes → hold (exceeds by 100) | Codex | Candidate |
| AC-07 | F2 offsetting prices (EC-02, -02-ctl) | hold with 2 price findings + offset note, though totals match the PO; control ready | Codex | Candidate |
| AC-08 | F3 partial billing + stale/concurrent approval (EC-03-A/B) | A approved; B → 409 stale → hold "exceeds by 100"; concurrent race → exactly one success | Codex | Candidate |
| AC-09 | F4 ambiguous/missing evidence (EC-04, -04-ctl) | needs_review (no number; PO ambiguous 200 µL vs 1000 µL) → after answers → ready; control ready with "PO inferred" | Codex | Candidate |
| AC-10 | Scanned (SC-01) | OCR stage runs → ready_for_approval | Codex | Candidate |
| AC-11 | Regression REG-01…REG-25 (incl. 01b, 07b, 07c) | per `04` §4.3 | Codex | — |

---

## 10. Assumptions log

This log is for the live pitch (G-19, guide p. 7: "Make an assumption, note it somewhere you can reference in the live pitch"). It is shown in the app's About dialog and in the README.

| ID | Assumption | Why | Revisit if |
|---|---|---|---|
| A-01 | Upload replaces the AP mailbox | One week; ingestion is plumbing, not judgment | Asked about email: a mailbox poller would feed the same `POST /api/invoices` |
| A-02 | Indian GST context: INR, en-IN dates (DD/MM/YYYY), GSTIN as vendor tax ID | Realistic fictional data; one coherent tax model | Multi-country scope |
| A-03 | Two-way match (invoice ↔ PO); no goods receipt | Guide describes PO matching only | Three-way match requested |
| A-04 | PO prices are net of GST, per the PO line's unit | Common practice; makes comparisons explicit | — |
| A-05 | Tolerance: unit price `max(₹0.05, 1 %)`; PO amount `max(₹1, 1 %)`; quantity 0 | Plausible demo policy; configurable | Customer policy differs |
| A-06 | One invoice ↔ one PO | Keeps allocation exact | Multi-PO invoices |
| A-07 | All data is synthetic; companies and GSTINs are fictional | Guide p. 7 allows created inputs; privacy | — |
| A-08 | Tax arithmetic checks printed rates; it does not determine correct GST classification | Not tax advice | — |
| A-09 | Evaluators receive approver credentials in the submission email | Shows the full flow without exposing admin | — |
| A-10 | Submission cutoff time on 12 Nov 2026 is unknown; we plan to submit by Wed 11 Nov 22:30 IST | Avoid the risk of a midnight-start deadline | Coordinator confirms a later time |
| A-11 | Statutory retention and legal hold are out of scope | Demo | Production |
| A-12 | Pending (unapproved) invoices do not reserve PO balance; approval does | Prevents ghost reservations by abandoned invoices; staleness is shown instead | Customer wants soft reservations |
