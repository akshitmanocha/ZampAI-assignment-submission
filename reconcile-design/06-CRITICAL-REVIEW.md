# 06: Critical review, simulations and residual risks

Review date: Tue 10 Nov 2026 (IST).

**Status marks used below:**
- **DV**: design verified.
- **IVP**: implementation verification pending.
- **BLK**: blocked, with the reason given.

Every resolution marked "resolved in package" has been applied in files 00–05.

---

## 1. Method

1. **Designer self-check.** Fixture arithmetic was re-computed with Python `Decimal`/`ROUND_HALF_UP`. Scripted checks covered ID cross-references (G/U/AC/REG/T/D/R/UA/CP/RG/rule IDs) and section references (`0x §n.m`).
2. **Four independent red-team reviewers** ran in parallel, read-only, and were not shown the designer's conclusions:
   1. A skeptical Zamp evaluator.
   2. A senior AP reviewer and numeric checker.
   3. A cold-start engineer.
   4. An ops/security/budget auditor.

   Together they raised **80 issues** (1 critical, 47 major, 32 minor), which consolidate into the **55** below. Each reviewer also re-computed every fixture value, walked the video and interview sequences against the seed ledger, and swept IDs.
3. **External facts** (hosting tiers, Kaggle limits, licences) were verified against official pages on 2026-11-10 by a separate research pass. That pass **changed the primary host**: Hugging Face Docker Spaces now require PRO (02 §8.4).

---

## 2. Issue log

The 55 consolidated issues are grouped by theme. Severity: **C** critical, **M** major, **m** minor.

### 2.1 Money logic and rules

| ID | Sev | Trigger / counterexample | Affected | Resolution in package | Remaining risk | Proof at build time |
|---|---|---|---|---|---|---|
| CR-01 | **C** | R-PRC-01 and R-AMT-01 gate on R-TAX-03, which sat at Order 84 (after them) and is `not_applicable` on tax-separated invoices. Read literally, price and amount checks were skipped, so **EC-02 cleared**. | 03 §4.1, §4.4; AC-07 | Gate semantics defined: `pass`/`not_applicable` satisfy a gate. R-TAX-03 moved to Order 63. Evaluation is topological, with a unit test that each dependency's Order < its dependent's. Fail-safe row: a required rule left `not_evaluated` with no root cause ⇒ `needs_review`. | Engine bug | `tests/unit/rules` order test; EC-02 e2e = hold |
| CR-02 | M | R-PRC-02 depended on R-PRC-01 and so could never run when R-PRC-01 failed, which meant no offset note on EC-02. | 03 §4.1 | Made a non-gate dependency; amount-delta formula defined | — | EC-02 has a R-PRC-02 `fail/none` finding |
| CR-03 | M | The canonical EC-02 payload showed R-AMT-01 `pass` while the prose said it fails. | 03 §3.6 | Payload corrected (fail/block, delta 200.00); line 2 pass added | — | Contract test fixture |
| CR-04 | M | R-AMT-01's tolerance was based on the remaining amount, so it shrank as the PO was used. A correctly priced final split invoice was false-held: ₹1,000 > ₹985 + ₹9.85. | 03 §4.1, §5.2–5.3; 04 | Made **cumulative**: `allocated + billed ≤ V + max(₹1, 1 % V)`. All worked values re-computed (HP-01 limit ₹5,050; EC-01d, EC-03-B still fail). REG-24 added. | — | REG-24 ready; named fixtures unchanged |
| CR-05 | M | Unit conversion needed the PO line's uom, but normalisation is PO-blind. "96 tips/rack" or "Box of 1000" pins would have been mis-converted. | 03 §1.4, §1.5, §4.3, §6; 02 §4.1, §5.6 | Normalisation records `pack_candidates` only. Conversion happens after assignment and is stored on `line_matches` (`conversion_status`, `qty_base`, `unit_price_base_net`). Same unit ⇒ factor 1. | — | SC-01, EC-04-ctl ready; REG-18 import boundary |
| CR-06 | M | R-TAX-02 was undefined when GST is printed only in the header, so a 28 % GST overcharge with consistent arithmetic **cleared**. | 03 §4.1 | Line rate derived from the sum of header component rates; rule made required, with Unk → review. REG-25 added. | — | REG-25 needs_review |
| CR-07 | M | "taxable" was undefined when no subtotal is printed, so HP-01's tax check was undecidable. | 03 §4.2; 04 §4.1 | taxable := printed taxable value, else printed subtotal, else the derived Σ net. T1 prints "Sub Total". | — | HP-01 e2e |
| CR-08 | m | Tax-inclusive per-line rounding drift held correct invoices with 4 or more lines (₹339.00 vs ₹338.98). | 03 §4.1, §4.7 | R-ART-02 tolerance becomes `max(0.01, 0.005 × n)` when any line is inclusive (policy key) | — | 4-line inclusive unit test |
| CR-09 | m | C6 (compare unrounded) contradicted C2 (store round4), so boundary results could flip. | 03 §4.3 | Compare the stored C2/C3 values; deltas and tolerances are not rounded | — | Boundary table tests |
| CR-10 | m | Bundle detection was undefined (REG-05 rule ambiguity). | 03 §6 | Bundle regex and missing-qty/price rule; R-EXT-04 skips bundles | — | REG-05 asserts R-LINE-03 |
| CR-11 | m | `sort_key` interleaved rules once line numbers reached 10 or more. | 03 §4.4 | ×100000 / ×100 scheme | — | Unit test |
| CR-12 | m | REG-08 and REG-16 were missing their R-AMT-01 block findings. | 04 §4.3 | Added | — | REG-08/16 assertions |

### 2.2 Workflow and evidence

| ID | Sev | Trigger / counterexample | Affected | Resolution in package | Remaining risk | Proof at build time |
|---|---|---|---|---|---|---|
| CR-13 | M | EC-04: the reviewer's PO-line choice never resolved the PO, so the invoice stayed `needs_review` after both corrections and **F4 could not reach Ready**. | 02 §5.2; 03 §1.6, §4.1, §3.6; 04 §4.2 | `ReviewerSelected` path: all lines assigned to one PO ⇒ R-PO-01 pass `via=reviewer_line_choice`, plus an R-PO-03 note. R-LINE-01 is `not_evaluated` while the PO is ambiguous, but the candidates are kept, so the "2 questions" count is now correct. | — | T-17 acceptance; AC-09 |
| CR-14 | M | EC-04 and EC-04-ctl printed tax amounts without rates, so R-TAX-01 returned unknown and ready was impossible. | 04 §4.1–4.2; 03 §5.3 | T3 prints "CGST @ 9%". Rule: every component prints its rate unless the fixture says "no rate". | — | EC-04-ctl e2e ready |
| CR-15 | M | Symmetric duplicate rules meant a **later copy blocked approval of the original**, with no recovery. | 03 §4.1, §4.6, §3.2; 01 §7.3 | Asymmetric J (approved, or earlier and open). Empty-corrections "Re-check" action. REG-01b added. | — | REG-01b |
| CR-16 | M | Approving was allowed after a failed revalidate run, so the reviewer's correction (qty 6 → 7) was ignored and 600 were allocated. | 03 §2.3; 02 §7.4 | Latest run must be `completed`, else 409 `NOT_APPROVABLE`. REG-23 added. | — | REG-23 |
| CR-17 | M | The content of the approval_check decision v2 was unspecified, so the line table could vanish after a 409. | 03 §4.6; 01 US-11; 04 §5.1 | v2 copies all findings (replacing the re-evaluated ones) and all line_matches. A Decision history list was added. | — | EC-03-B v2 shows the full line table |
| CR-18 | M | The OCR cache was keyed by bytes and survived demo reset, so the interview's "live" scan was a cache hit and latency evidence was invalid. | 03 §1.4, §8; 02 §4.2; 04 §5.4 | The cache is per invoice; reset deletes it and unreferenced blobs; latency is recorded only when `ocr.duration_ms > 0`. | — | Reset → SC-01 ocr duration > 0 |
| CR-19 | M | Pre-running SC-01 and then uploading it live caused an R-DUP hold on the live run. | 04 §5.3 | Rule: never pre-run a fixture that the same session uploads live | — | Rehearsal checklist |
| CR-20 | m | The stale banner did not appear in a pre-opened second tab. | 03 §2.3; 01 §7.2; 04 §5.1 | Re-fetch on focus and every 10 s; ⌘R in the script | — | Video rehearsal |
| CR-21 | m | No way to produce the `processing_failed` state for AC-29. | 03 §7; 04 REG-07c | `RECONCILE_FAULT_INJECT` (refused when `DEMO_MODE=true`) | Misuse locally only | REG-07c |
| CR-22 | m | `display_status` enum, counts keys, OCR progress event and `WORKER_CONCURRENCY` were undefined; pseudocode policy keys didn't match the YAML. | 03 §2.3, §2.5, §3.4, §7; 02 §5 | All defined and aligned | — | Contract tests |

### 2.3 Engine, worker and persistence

| ID | Sev | Trigger / counterexample | Affected | Resolution in package | Remaining risk | Proof at build time |
|---|---|---|---|---|---|---|
| CR-23 | M | Idempotency records were NOT NULL but inserted before the outcome was known, and which outcomes are stored was undefined. | 03 §1.5, §1.7, §3.1; 02 §7.4 | Nullable within the inserting txn; stored/rolled-back outcome table; master-data 409 stored; backstop retry is a new txn | — | REG-11, REG-12, REG-15 |
| CR-24 | M | Attempt 2 after a crash past the normalisation commit hit unique violations, so the run failed instead of recovering. | 02 §4.2 | Attempt > 1 reuses committed readings; REG-07b | — | REG-07b |
| CR-25 | M | The claim SQL lost the previous lease owner, and the heartbeat added an int to a timestamptz. | 02 §7.3 | CTE claim returns `prev_*`; `make_interval` in the heartbeat | — | REG-07 event assertion |
| CR-26 | M | The readiness check needed a heartbeat < 45 s but `worker_heartbeats` refreshed every 10 min, so ready was 503 about 92 % of the time. | 02 §7.3, §11.4 | Heartbeat thread upserts every 15 s | — | `/health/ready` stable |
| CR-27 | M | Sandbox rlimits via `preexec_fn` are unsafe in a threaded process; RLIMIT_AS plus OpenMP threads on 0.1 CPU; fixed timeouts. | 02 §4.3, §8.2; 03 §7; 05 T-01 | Sandbox sets its own limits; env pins OMP=1 and MALLOC_ARENA_MAX=2; timeouts are env-driven and set from the T-01 measurement; async validate; lifespan worker | Render perf unknown | T-01 spike numbers |
| CR-28 | m | Seed needed a run for evidence; seed ran before users; the FK cycle was comment-only; `uuid` was missing from value_type. | 03 §1.3–1.5, §5.1; 02 §8.2 | `trigger='seed'`; order migrations → users → seed; ALTER FKs DEFERRABLE; delete order specified | — | Fresh-DB boot test |
| CR-29 | m | Approved invoice + wrong version: 02 and 03 disagreed (`INVOICE_CLOSED` vs `DECISION_VERSION_CONFLICT`). | 02 §7.4 | 02 now matches 03 | — | Contract test |
| CR-30 | m | Retry of a failed revalidate dropped corrections; `base_run_id` was undefined after an approval_check. | 03 §3.2, §1.4 | Retry keeps the kind and corrections; base defined | — | Unit test |

### 2.4 Hosting, release and security

| ID | Sev | Trigger / counterexample | Affected | Resolution in package | Remaining risk | Proof at build time |
|---|---|---|---|---|---|---|
| CR-31 | M | Render gives `postgresql://`, but SQLAlchemy then looks for psycopg2, so the container crash-loops. | 03 §7; 05 UA-05 | Scheme rewrite in one engine factory; paste the URL verbatim | — | T-01 `/spike/db` via the factory |
| CR-32 | M | `MIGRATE_ON_START` broke rollback: the old build sees an unknown revision. | 02 §11.1, §11.4, §11.6 | "DB ahead" ⇒ skip, healthy; rehearse a rollback across a migration | — | T-25 rollback rehearsal |
| CR-33 | M | The work branch and deploy branch differed (stale deploy). | 02 §8.2, §11.6; 05 T-00 | Render branch `main`; ff-merge; `git init -b main`; deploy SHA check | — | RG-H |
| CR-34 | M | The $0 / no-card audit was in no gate, and "no card" was overstated. | 02 §8.2; 05 RG-H, D-02; 00 AC-21 | Wording is "partially verified"; RG-H billing screenshots; card-free workspace rule | Render policy change | RG-H screenshots |
| CR-35 | M | The secret-scan regex matched variable names (`KAGGLE_PROXY`, `sk-` in "task-") yet missed real tokenised URLs. | 02 §9.2 | Value-matching regex plus an exact-value check against the proxy file | — | RG-L |
| CR-36 | M | The proxy URL could leak through exception or HTTP-library logs, or via `read -rs` in Codex's non-TTY shell. | 02 §10.2, §10.6; 03 §7; 05 UA-16 | The candidate writes a 0600 file in their own terminal; filter + excepthook; library loggers at WARNING; leak test | Human error | T-21 leak test |
| CR-37 | M | Evaluators had no input PDFs, and the assumptions link pointed into a private repo. | 01 §7.1; 03 §3.2; 04 §5.7 | In-app Sample invoices (`/api/samples`) and an About page; 3 PDFs attached; assumptions inline in the email | Shared demo state | §5.6 link check |
| CR-38 | M | The FB-A fallback could become the submitted link with no uptime plan or security check. | 02 §8.3; 05 UA-03, T-25, R-19 | Runbook: Tailscale mandatory, `--bg`, restart policy, `caffeinate`, FB-A smoke in RG-H, availability note | Laptop availability | FB-A smoke |
| CR-39 | M | The DB-expiry trigger was wrong ("not scheduled"), and recreating the DB was unplanned. | 02 §8.2; 05 UA-10 | "Not taken place by 5 Dec" + an 8-step runbook | Missed reminder | Calendar (UA-10) |
| CR-40 | m | Secrets passed in argv (`pg_dump`, `psql`, curl login); PG major mismatch; CGNAT /32. | 02 §11.5; 04 §5.3; 05 UA-05 | `.pgpass` + dockerised pg_dump 16; PG 16 chosen; ≤ 10-min IP window with removal check; stdin login | — | Backup evidence |
| CR-41 | m | Quota paths were incomplete (shared hours, build minutes, GPU quota, HF download, Loom cap, upload flood). | 02 §8.5 | Rows added, incl. a global 600 MB upload cap (507) | — | Diagnostics |
| CR-42 | m | The rollback target was the unauthenticated spike. | 05 T-15, T-01 | Fix forward; spike routes deleted before T-15 | — | AC-28 route enumeration |
| CR-43 | m | Render spin-down could hit during interview Q&A. | 02 §11.8; 04 §5.4 | Keep-warm loop from T−30 to the end of the call | — | Interview checklist |
| CR-44 | m | A least-privilege DB role is impossible on Render Free with migrate-on-start. | 02 §2 | Accepted risk, stated; private networking mitigates it | Owner-role compromise | — |
| CR-45 | m | Memory budget on 512 MB: argon2 at 64 MiB per login; no Render value for the sandbox limit. | 02 §9.1; 03 §7 | argon2 m = 19 MiB; sandbox limit from VmPeak + 30 % | OOM | T-01 / T-25 RSS |

### 2.5 Kaggle and ML

| ID | Sev | Trigger / counterexample | Affected | Resolution in package | Remaining risk | Proof at build time |
|---|---|---|---|---|---|---|
| CR-46 | M | Checkpoint validation compared against metrics that don't exist mid-epoch, at a 1e-4 tolerance an fp16 run can't meet. | 02 §10.4 | fp32 probe set stored in each bundle; ≤ 1e-3; ranking; step check | — | T-21 resume test |
| CR-47 | m | The heartbeat treated a finished trainer as dead and resumed it. | 02 §10.3 | `status.json` states | — | T-22 log |
| CR-48 | m | Export volume (~2.2 GB) could exhaust the tunnel; the export path was untested. | 02 §10.1 | 100 MB round-trip test; lean intermediate bundles; ≤ 1 GB budget | Unknown proxy cap | T-22 log |
| CR-49 | m | `T_no_new` conflicted with the optional-work cutoff; `T_hard` was undefined for a replacement URL. | 02 §10.2, §10.5; 05 §1 | `min(...)`; the same session keeps `T_hard` | — | `session_log.md` |
| CR-50 | M | The B0 fit corpus was excluded from the image, so the deployed B0 ≠ the evaluated B0. | 04 §3.3; 05 T-20 | B0 fitted once on the train split; committed joblib, sha-pinned | — | Hash check at worker start |

### 2.6 Schedule, demo and package

| ID | Sev | Trigger / counterexample | Affected | Resolution in package | Remaining risk | Proof at build time |
|---|---|---|---|---|---|---|
| CR-51 | M | The schedule was pinned to 11:26, so H0 had already passed at handoff and FB-A would be forced. | 00 §1, §3; 05 §4, §6, §9 | K-relative Tuesday; remaining time recomputed at K; capacity table; R-18 overnight dependency | **Tight**: overnight work needed | Progress-log K entry |
| CR-52 | M | T-16 needed T-17 but was ordered before it, so CP-2 failed artificially and the 3-case cut fired. | 05 §3, §6.1 | Dependencies inverted correctly; T-11a/b split rebalanced; CP-2 redefined | — | CP-2 log |
| CR-53 | M | Extraction was underspecified, which invited per-template parsing that fails on the interviewer's own PDF. | 02 §4.1; 04 §5.8 | Layout-agnostic label lexicon; no template branching (grep); T5 hold-out reported | Unseen layouts → review | T5 metrics |
| CR-54 | m | The video overclaimed AI ("AI matches descriptions" when B0 is TF-IDF), omitted AI-for-build, and never showed Needs review. | 04 §5.1, §5.8 | Narration variants tied to the actual result; build-AI talking point; EC-04 saved run shown | — | Rehearsal |
| CR-55 | M | 06 was missing but referenced in four places. | 00, 05 | This file | — | — |

**Reviewed and found correct** (all four lenses agree):
- All fixture arithmetic.
- GSTIN formats and IGST/CGST consistency.
- No unintended R-DUP-02 collisions in the demo sets.
- The lock order has no cycle.
- Finalize is crash-safe.
- All IDs are defined.
- Guide citations match the PDF.
- Remaining-time arithmetic and weekdays.
- No CI/CD; manual deploy.
- The private datastore in the primary topology.
- Auth works as a fail-closed release gate.
- The Kaggle 12 h / heartbeat / checkpoint structure.

---

## 3. Required simulations (after fixes)

### 3.1 Happy path: HP-01, seed ledger

**Input.** Native PDF, 1 page, so OCR is skipped. Readings:
- `SH/2526/0912`, dated 2026-11-06 (≤ today + 1; ≥ PO date 2026-10-20).
- PO `PO-2026-0147`.
- Seller GSTIN 27AAJCS4821K1Z3 (≠ buyer).
- Line: 6 BOX @ 500.00 = 3,000.00, pack candidate {100, BOX→EA, "gloves"}.
- Sub Total 3,000.00; CGST 9 % 270.00; SGST 9 % 270.00; Total 3,540.00.

**Resolution and conversion.**
- Vendor: GSTIN exact match → VEN-0001, approved.
- PO: explicit, same vendor, open.
- Lines: line 1 assigned. Line 2 is vetoed (size large ≠ medium); line 3 scores low.
- Conversion: BOX ≠ EA, and the candidate's inner unit EA equals the PO uom, so factor 100. `qty_base` = 600; `unit_price_base_net` = round4(500.0000 / 100) = **5.0000**.

**Checks.**

| Rule | Computation | Result |
|---|---|---|
| R-PRC-01 | \|5.0000 − 5.0000\| = 0 ≤ max(0.05, 0.05) | ✓ |
| R-QTY-01 | 600 ≤ 1000 − 400 = 600 (inclusive) | ✓ |
| R-AMT-01 | 2,000.00 + 3,000.00 = 5,000.00 ≤ 5,000.00 + 50.00 | ✓ |
| R-ART-01 | 6 × 500.00 = 3,000.00 | ✓ |
| R-ART-02 | 3,000.00 = 3,000.00 | ✓ |
| R-TAX-01 | round2(3,000 × 0.09) = 270.00, ×2 | ✓ |
| R-TAX-02 | 0.09 + 0.09 = 0.18 = PO rate | ✓ |
| R-ART-03 | 3,000 + 540 = 3,540.00 | ✓ |
| R-DUP-01/02/03 | — | ✓ |
| R-TAX-03 | — | n/a |

**Result:** `ready_for_approval`.

**Approve.** Locks are taken in order: invoice → vendor (share) → PO-0147 → lines by id. The re-check passes. The allocation is 600 / ₹3,000.00, so the line moves from 400 / ₹2,000.00 to **1,000 / ₹5,000.00**. The CHECK constraint holds (1000 ≤ 1000). **DV**, IVP (AC-02/05).

### 3.2 Difficult invoice: EC-02, correct total, wrong lines (false-clearance challenge)

**The trap.** Header net is ₹3,550.00, exactly the PO's net value. A total-only matcher would clear it.

**Line prices** (units Nos → EA, same unit, so factor 1):

| Line | Billed | PO | Diff | Tolerance | R-PRC-01 |
|---|---|---|---|---|---|
| 1 (bolts) | 13.5000 | 12.5000 | 1.00 | max(0.05, 0.125) = 0.125 | ✗ block |
| 2 (nuts) | 3.0000 | 4.0000 | 1.00 | max(0.05, 0.04) = 0.05 | ✗ block |
| 3 (washers) | 1.2500 | 1.2500 | 0 | — | ✓ |

**Other checks.**
- **R-PRC-02:** deltas +200.00 / −200.00, Σ 0.00 ≤ max(1.00, 33.00), so it fires as an info note.
- **R-AMT-01:** line 1: 0 + 2,700.00 > 2,525.00 ✗ block. Line 2: 600 ≤ 808 ✓. Line 3: 250 ≤ 252.50 ✓.
- **R-QTY-01:** 200 ≤ 200 on all three lines ✓.
- **Tax and total:** IGST 3,550 × 0.18 = 639.00 ✓; total 4,189.00 ✓.

**Result:** **hold**, with 3 block findings and 1 offset note. **Before CR-01 this cleared; it no longer does.** DV, IVP (AC-07).

### 3.3 Repeated upload

| Step | Action | Outcome |
|---|---|---|
| 1 | Upload HP-01 with key k1 | RC-a created |
| 2 | Retry with k1 | Replays an identical 202 (REG-11); 1 invoice |
| 3 | Upload the same bytes with new key k2 | The blob insert is `ON CONFLICT DO NOTHING`, so there is still one blob. A `SAME_FILE_SEEN` notice is returned and RC-b is created. RC-b's run: R-DUP-03 and R-DUP-01 both find J = RC-a (open and earlier) and block, so RC-b is **hold**. |
| 4 | Approve RC-a | J must be approved or earlier, and RC-b is later and open, so it is excluded. RC-a: **200 approved** (REG-01b). |
| 5 | Two uploads of the same bytes 1 s apart | Only the later one holds |

DV, IVP.

### 3.4 Two approvals racing for PO-2026-0149 line 1 (EC-03 / REG-14)

**State before.** Seed: 500 / ₹2,500.00 allocated of 1,000 / ₹5,000.00. Invoices A and B each bill 300 / ₹1,500.00 and are both `ready` at v1.

| Step | Transaction | What happens |
|---|---|---|
| 1 | T1 (A), T2 (B) | Each locks its own invoice row. Both take the vendor lock `FOR SHARE`, which is compatible. |
| 2 | T1 | Takes the PO-0149 header `FOR UPDATE`. T2 waits. |
| 3 | T1 | Re-check: 300 ≤ 500; 2,500 + 1,500 = 4,000 ≤ 5,050. Allocates; the line becomes **800 / ₹4,000.00**; version + 1; commit → **200**. |
| 4 | T2 | Wakes and re-reads committed rows: 300 > 200 (exceeds by 100); 4,000 + 1,500 = 5,500 > 5,050. Writes decision v2 `hold` (`approval_check`, all findings and line_matches copied) and audit `approval.stale`; stores the 409; commit → **409 `APPROVAL_STALE`**. |

**Invariants.**
- Σ allocations = 500 + 300 = 800 = `allocated_qty` ≤ 1,000.
- No lock cycle: the only exclusive shared lock is the PO header.
- Same invoice double-clicked with different keys: the second request waits on the invoice row, then gets 200 `already_approved`.
- Lost response: the same key gives a byte-identical replay.

DV, IVP (AC-08, REG-14 20/20).

### 3.5 Missing field: EC-04

**v1 (needs_review).**
- Vendor resolved by GSTIN (Meridian, approved).
- R-EXT-01 unknown → review.
- No PO printed. Two open POs (0155, 0158); PO-level margin ≈ 0.005 < 0.10, so R-PO-01 unknown → review.
- R-LINE-01, R-PRC-01, R-QTY-01, R-AMT-01 and R-TAX-02 are `not_evaluated` (gated).
- R-DUP-01 is `not_evaluated` (no number). R-DUP-02 passes.
- Arithmetic: 10 × 210 = 2,100 ✓; CGST @ 9 % 189.00 ✓ ×2; total 2,478.00 ✓.
- Result: no block, 2 review findings ⇒ **needs_review, "2 questions"**.
- The missing number **stays missing**. No value is borrowed from the PO.

**Corrections.** `header.invoice_number = MLS-7781` and `lines[1].po_line_id = 0158/1`, each with a reason. This creates revalidate run #2: stages 1–3 are skipped, and field_extraction reuses the readings with 2 corrections applied.

**v2 checks.**

| Rule | Result |
|---|---|
| R-EXT-01 | pass (value corrected) |
| R-PO-01 | pass via reviewer line choice → PO-0158 (same vendor); R-PO-03 note |
| R-PO-02 | open ✓ |
| R-LINE-01 | assigned by reviewer |
| Conversion | RACK = RACK, factor 1 |
| R-PRC-01 | 210 = 210 ✓ |
| R-QTY-01 | 10 ≤ 50 ✓ |
| R-AMT-01 | 2,100 ≤ 10,605 ✓ |
| R-DUP-01 | no J with key MLS7781 ✓ |
| R-TAX-02 | 0.18 ✓ |
| R-DATE-01 | 09 Nov ≥ 30 Oct ✓ |

**Result:** `ready_for_approval` at v2. Run #1's reading for the number remains `missing`, and the original is preserved. **Before CR-13 this stayed needs_review.** DV, IVP (AC-09).

### 3.6 Worker crash

**REG-07: SIGKILL during SC-01 OCR.**
1. The lease expires within 60 s.
2. On restart, the claim CTE sees `prev_state=leased`. It writes `run.lease_recovered {previous_owner, previous_attempt: 1}`, sets attempt 2 and fence + 1.
3. OCR re-runs, because the killed page's text layer was never committed.
4. Any write from the old process fails the fence check.
5. Exactly one decision results: `UNIQUE(invoice_id, version)` plus the fingerprint.

**REG-07b: crash after the normalisation commit.** Attempt 2 loads the committed readings and skips stages 2–5, so no duplicate rows are written.

**Crash inside finalize.** The transaction rolls back and attempt 2 finalizes. A crash after commit leaves the job `done`, so it is never reclaimed.

DV, IVP (AC-13).

### 3.7 Deadline failure paths (rehearsed on paper)

| Failure | Trigger | Fallback | Effect on submission | $0? |
|---|---|---|---|---|
| Free hosting inaccessible: card asked, Free not offered, OOM, internal DB unreachable | T-01 at H0 (K + 2 h, hard K + 3 h) | FB-B only with UA-11 consent, else FB-A (Funnel runbook) | Link exists. If FB-A, the email states the uptime caveat and U-08 is partial. | ✓ |
| Host suspended after submission (hours or bandwidth) | Dashboard / diagnostics | FB-A + coordinator email | Temporary outage | ✓ |
| Quotas: DB 1 GB / uploads | `blob_bytes` > 600 MB | 507 cap; demo reset | None | ✓ |
| Quotas: build minutes | Render dashboard | ≤ 6 builds; local image test | Deploy delay | ✓ |
| Quotas: Render PG expiry ≈ 10 Dec | Reminder on 5 Dec | 8-step recreate runbook | None if done | ✓ |
| Quotas: Loom cap | 25 videos | Drive / YouTube Unlisted | None | ✓ |
| OCR / model credentials | — | None needed at runtime: Tesseract is in the image. The HF base model is cached at T-20; a failed download means B0-only | None | ✓ |
| Kaggle idle expiry (20/60 min documented, 40 stated) | 2 failed heartbeats | Resume from the last verified checkpoint (≤ 10 min lost) | None | ✓ |
| Lost proxy | Unreachable | New URL in the file (same `T_hard`). If none by Wed 10:00 → CPU pilot. | None (U-07 may be partial) | ✓ |
| 12 h cutoff during training | `T_no_new` / `T_export_only` | Last verified checkpoint; report partial | None | ✓ |
| Coordinator cutoff earlier than Plan A | UA-01 reply | 2-case cut + cut video; email before the deadline (UA-14) | Reduced scope, disclosed | ✓ |
| Deadline already passed | Not the case (checked 10 Nov 11:26 IST) | Guide p. 7: email the coordinator immediately; submit the working portion with honest status; assume no extension | — | ✓ |

### 3.8 Manual-only check

- There is no `.github/workflows`, and Render Auto-Deploy is Off.
- Deploy, smoke, rollback and backup are all manual steps (02 §11).
- Tests run via `make test` / `pytest`.
- `MIGRATE_ON_START` and the admin endpoints are runtime code paths, not CI/CD.

**DV.**

---

## 4. $0 audit

Design-level audit. RG-H re-checks it by observation.

| Service | Plan used | Card on file? | Over-quota behaviour | Source (checked 2026-11-10) | Status |
|---|---|---|---|---|---|
| Render web service | Free (0.1 CPU / 512 MB) | No card expected; no explicit "no card" sentence found | Suspends Free services when hours or bandwidth run out without a payment method | render.com/docs/free | IVP (RG-H screenshot) |
| Render Postgres | Free (1 GB, expires 30 d) | Same | Expiry, then a 14 d grace period, then deletion | render.com/docs/free | IVP |
| GitHub | Free private repo, no Actions | No | No Actions minutes used | — | DV / IVP |
| Tailscale | Personal (Funnel on all plans) | Not stated | Bandwidth-limited (non-configurable) | tailscale.com/kb/1223/funnel | IVP |
| Loom | Starter (5 min, 25 videos) | Not required for the free plan (verify at signup) | Can't record more at the cap; fallback Drive/YouTube | support.atlassian.com/loom | IVP |
| Kaggle | Free GPU quota (~30 h/week) | No card; phone verification | Session ends / quota exhausted; no billing | kaggle.com/docs | Partially verified |
| Hugging Face Hub | Anonymous model download | No account | Rate limits only | — | DV |
| Neon (FB-B only, with consent) | Free | "No credit card required" | Suspends compute or blocks writes; no overage billing | neon.com/pricing | DV (only if used) |
| OSS libraries | MIT/BSD/Apache-2.0/LGPL (unmodified) | — | — | 02 §3 | DV |
| Domain | None (host-provided URL) | — | — | — | DV |
| **Excluded** | HF Docker Spaces (PRO $9/mo), Fly.io, Koyeb, Railway, Modal, Northflank, Cloud Run, Oracle (card) | — | — | 02 §8.3–8.4 | DV |

---

## 5. Consistency checks

| Check | Mark | Notes |
|---|---|---|
| Requirement IDs: G-01…25, U-01…18, AC-01…30 defined, traced and referenced | **DV** | Scripted sweep; no dangling IDs |
| Section references (`0x §n.m`) resolve | **DV** | Scripted; 06 §4/§6 now exist |
| Route, field and state names consistent across 01–05 | **DV** · IVP | Cold-engineer sweep + fixes CR-22, CR-29 |
| Amount bases: net per PO uom; cumulative PO amount; taxable definition | **DV** · IVP | CR-04, CR-05, CR-07 |
| Expected fixture outcomes (named + REG) recomputed | **DV** · IVP | Decimal recompute by designer + 2 reviewers |
| Release ordering / dependency graph acyclic | **DV** | CR-52 |
| Model fallback (B0 default; adoption gate; artefact parity) | **DV** · IVP | CR-50 |
| Timing assumptions (K-relative, capacity) | **DV** with caveat · IVP | Needs overnight work, else R-18 cut |
| Guide obligations G-01…G-25 have evidence paths | **DV** · IVP | Deliverables exist only after the build |
| Candidate actions UA-01…UA-16 complete | **DV** · IVP | UA-01/02/03/05/15 needed at once |
| Hosting facts | Partially verified · IVP | T-01 hands-on (internal DB reachability, external-access toggle, Singapore Free, rollback UI) |
| Kaggle access | **BLK** (needs the UA-06/16 handover) | Off the critical path; CPU fallback ready |
| Repository state | **BLK** for this run (none accessible) | T-00 maps it if one exists |
| FB-B datastore exposure | **BLK** (needs explicit UA-11 consent, only if triggered) | Builder-security policy |

---

## 6. Remaining implementation and access risks

| Risk | Why it remains | Owner / when |
|---|---|---|
| R-01 Render Free capacity (0.1 CPU / 512 MB) for OCR and memory | Unmeasured until T-01 | Codex / H0 |
| R-02 Free web → internal Postgres reachability; external-access toggle | Not stated on official pages | Codex + candidate / H0 |
| R-04 Cutoff time unknown | Coordinator reply pending | Candidate / K + 1 h |
| R-18 Schedule needs overnight Codex work | Capacity is tight | Candidate / Tue night |
| R-06 SC-01 OCR exactness at 200 DPI | Depends on Tesseract on the host | Codex / CP-2 |
| R-09 Render Postgres expiry ≈ 10 Dec | Platform policy | Candidate / 5 Dec |
| R-19 FB-A uptime if it becomes the link | Personal machine | Candidate / submission |
| Unseen invoice layouts in the interview | Label-based extractor; falls back to Needs review | Candidate (talking point) |
| Evaluators changing shared demo state | By design (live link) | Candidate / reset before interview |

---

## 7. Completion

The package (00–06) is reconciled. A fresh Codex session can start from 05 §1 and §11, plus the repository.

Each release requirement has a stated proof:
- **Guide obligations:** 00 §4.1 → AC-IDs → 05 §3 tasks.
- **Gates:** 05 §6.3 (RG-L / RG-H / RG-V / RG-S).
- **Hosted evidence:** 04 §5.5.

Every number in the fixtures is fixed in 03 §5 and was re-computed independently. Nothing in this package claims an observed test, deployment or benchmark result.
