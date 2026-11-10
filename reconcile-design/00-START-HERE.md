# 00: START HERE: Reconcile release brief (Zamp ASA case study · PS-1 Finance/AP)

Written Tue **10 Nov 2026, 11:26 IST** (Asia/Kolkata). This is a documentation-only design run: no code, infrastructure, accounts or messages were created.

## 1. One-page release brief

**What ships.** Reconcile is a hosted web app. An AP user uploads an invoice PDF (native or scanned). They watch the 11 real processing stages run, then get one of three recommendations, with page-level evidence, line-by-line PO checks and a next action:

- **Ready for approval**
- **On hold**: a confirmed blocker
- **Needs review**: unresolved required evidence

A run that breaks for technical reasons is a separate `processing_failed` state. An approver approves against the **current** PO balance; approval is atomic and detects staleness. The dashboard keeps history, statuses and outputs, and the system never executes payment. These are the guide deliverables, p. 2 "Deliverable 1".

**Submission (guide p. 1 Day 7, p. 2).** Two links go to the hiring coordinator:
1. The live, runnable process.
2. A demo video of at most 5 minutes. It must show a live happy path and at least one live edge case, with narration and no slides.

After that, the interview is a live demo: the happy path plus 2–4 prepared edge cases.

**Demo set.**
- **HP-01**: SafeHands, 6 boxes × 100 gloves at ₹5.00 against PO-2026-0147 → Ready → approve.
- Four edge families:
  - **F1** pack evidence vs spec conflict.
  - **F2** offsetting line-price errors with matching totals.
  - **F3** partial billing with stale or concurrent approval.
  - **F4** ambiguous or missing identifiers.
- **SC-01**: a real scanned invoice.

**Constraints.**
- Hard **$0** budget.
- **No CI/CD**: manual deploy only.
- Synthetic data only.
- Kaggle 2×T4 is used for an optional fine-tune, kept off the critical path.

**Key design decisions.**

| Decision | What it means | Detail |
|---|---|---|
| Hosting | Render Free web service plus a **private** Render Free Postgres. Hugging Face Docker Spaces need a paid plan as of 2026-11-10. Fallback FB-A is a local stack on Tailscale Funnel. | 02 §8 |
| Extraction | Local and deterministic: pdfplumber plus Tesseract | — |
| Money checks | `Decimal` arithmetic under a versioned policy | — |
| Matching | B0 (TF-IDF plus attribute rules) is the default. A MiniLM cross-encoder (B1/E1) is adopted only if it wins on held-out data and fits the free host. | 04 §3.6 |

**Deadline.** The user-supplied deadline is **12 Nov 2026**, and the cutoff time is **unknown**. The default **Plan A** therefore submits by **Wed 11 Nov 22:30 IST**:
- From the design start (Tue 11:26): 35 h 04 m. From a kickoff K at Tue 14:00: 32 h 30 m.
- To the earliest reading of the deadline (12 Nov 00:00 IST): 36 h 34 m from the design start; 34 h 00 m from K.
- To 12 Nov 23:59 IST: 60 h 33 m from the design start; 57 h 59 m from K.

Codex recomputes these at K (05 §4.1).

If the coordinator confirms a cutoff of Thu 18:00 IST or later, **Plan B** applies (05 §4.2). The deadline has not passed.

## 2. Reading order and authority

**Reading order for Codex:**

| # | File | Contents |
|---|---|---|
| 1 | 00 | This brief |
| 2 | **05** | Kickoff prompt, backlog and gates; start work from here |
| 3 | **03** | Canonical contracts |
| 4 | 02 | Design |
| 5 | 01 | Product and UX |
| 6 | 04 | Evaluation, fixtures and demo |
| 7 | 06 | Review log and remaining risks |

**Authority when sources conflict:**

| Rank | Source | Governs |
|---|---|---|
| 1 | **Candidate Guide PDF** | Hiring deliverables |
| 2 | **User commitments** (U-IDs below, from the user's brief) | Product and engineering intent |
| 3 | **Verified repository behaviour** | What already exists and works. Keep it if it satisfies the guide. |
| 4 | 03 → 02 → 01 → 04 → 05 → 00 | Remaining questions, in that order |

06 records the red-team review: 4 independent reviewers, 80 raw issues, 55 consolidated. Each resolution listed there as *resolved in package* has been applied in the other files. 06 also holds the $0 audit (§4) and the residual-risk index (§6).

Any conflict goes into 05 §7, with the smallest compatible decision and its impact.

## 3. Current-state confidence, blockers, timeline

| Item | State | Confidence |
|---|---|---|
| Repository | **Missing / inaccessible to this run**: none found in `~/Downloads` or `~` (depth 3) | Unverified. T-00 re-checks on the build machine. |
| Guide requirements | Read in full (7 pp.) and traced below | Verified |
| $0 hosting path | Facts verified from official pages (02 §8.4). Not exercised hands-on. | **Implementation verification pending** (T-01, gate H0 = K + 2 h) |
| Kaggle 2×T4 via proxy | Expected (user); not handed over | Unverified (T-22) |
| Fixture arithmetic | Re-computed with Python `Decimal` during design | Design verified |
| Any test, deployment or benchmark result | None exist yet | — |

**Submission blockers (open):**

| ID | Blocker | Clears when | Owner |
|---|---|---|---|
| B-1 | No running process exists | CP-1 (hosted HP-01) → CP-3 | Codex |
| B-2 | No $0 interviewer-accessible URL proven | H0 → RG-H | Codex + candidate (UA-03, UA-05) |
| B-3 | Cutoff time unknown | UA-01 | Candidate |
| B-4 | Video not recorded | RG-V | Candidate (UA-09) |
| B-5 | PS-1 choice email possibly not sent | UA-02 | Candidate |

These are not blockers: the Kaggle session, E1, and the Benchmarks and PO pages.

**Timeline (Plan A, IST; details and estimates in 05 §3–4):**

| When | Milestone |
|---|---|
| K | Kickoff prompt pasted (expected around Tue 14:00); recorded in the progress log |
| K + 2 h | **H0**: $0 hosted path proven (hard K + 3 h, latest Tue 19:00, then fallback) |
| K + 11 h (cap Wed 02:00) | **CP-1**: hosted HP-01 end-to-end (other-network phone check can wait until Wed 08:00) |
| Overnight | T-04b, T-07b, T-11b (strongly recommended; otherwise R-18 applies) |
| Wed 12:00 | **CP-2**: approval + corrections; F1–F3 green locally |
| Wed 15:00 | **CP-3**: feature freeze; ML adoption decision; optional-work cutoff |
| Wed 19:00 | **CP-4**: RG-H passed, two rehearsals done |
| Wed 22:00 | Video recorded (RG-V) |
| Wed 22:30 | **Submitted** (RG-S) |

**First 30–60 minutes for Codex:**
1. **0–15 min.** Run the T-00 discovery command (05 §11). Create `docs/progress-log.md`. Preserve any WIP on a branch.
2. **15–30 min.** Ask the candidate for UA-01, UA-03 and UA-05. Start T-02 locally (scaffold, compose with 127.0.0.1 binds, Dockerfile on `python:3.12-slim-trixie` with `tesseract-ocr`).
3. **30–60 min.** Once accounts exist, run the T-01 spike: deploy a hello image to Render Free with Auto-Deploy Off, then check `/health/live`, `/spike/db` over the internal URL and `/spike/ocr` from a phone on cellular. Record RSS and timings. Decide H0.

## 4. Traceability matrix

Priority: **P0** guide obligation · **P1** user commitment · **P2** design choice · **S** stretch.

Status: **DV** = design verified · **IP** = implementation verification pending · **UA** = waiting on a user action.

### 4.1 Guide obligations (Candidate Guide PDF; physical page and heading)

| ID | Locator | Pri | Requirement | Design / contract | Task | Acceptance / demo evidence | Status |
|---|---|---|---|---|---|---|---|
| G-01 | p. 1 "What this is — and why we do it this way" | P0 | Build a working automated process for a real operational problem within a week; it is not a whiteboard exercise | 01 §1–2 | All | AC-02 | DV · IP |
| G-02 | p. 1 Schedule "Day 1 — Pick your problem" | P0 | Reply with choice; subject "ASA Case Study — [Your Name] — PS-1" | 05 §9 UA-02 | — | Sent email | UA |
| G-03 | p. 1 "Days 2–6 — Build" | P0 | Handles real inputs end-to-end; happy path and own edge cases tested; "should actually run — not just look like it does" | 02 §4, 04 §4 | T-12, T-16 | AC-02, AC-06…AC-10 | DV · IP |
| G-04 | p. 1 "Day 7 — Submit"; p. 2 header | P0 | Send coordinator (1) a live, runnable process link, (2) a ≤ 5-min demo video link | 04 §5.7 | T-25, T-27 | AC-15, AC-16, AC-17 | DV · IP · UA |
| G-05 | p. 2 "Deliverable 1" | P0 | Actually executes (no mockup); accepts real input (PDF); runs logic; real output | 02 §4, 03 §3 | T-05…T-12 | AC-02, AC-15 | DV · IP |
| G-06 | p. 2 "Deliverable 1" | P0 | UI is graded: intuitive interface with a **live run view showing each stage as it executes** | 01 §7.2, 03 §2.4 | T-13, T-18 | AC-03, AC-29 | DV · IP |
| G-07 | p. 2 "Deliverable 1" | P0 | **Dashboard** showing history, status and outputs across runs | 01 §7, US-11 | T-18 | AC-04 | DV · IP |
| G-08 | p. 2 "Deliverable 2" | P0 | ≤ 5 min (Loom or any recording); happy path live, then at least one edge case live; narrate what, why and how built; no editing, no slides | 04 §5.1 | T-27 | AC-16 | DV · UA |
| G-09 | p. 2 "Live demo — in the follow-up interview"; p. 1 "After submission" | P0 | Run live in the interview: happy path plus prepared edge cases; real time; no slides; explain decisions | 04 §5.2–5.4 | T-26 | AC-18 | DV · IP |
| G-10 | p. 3 PS-1 (boxed) | P0 | Invoice in → clear, reasoned decision out, "with everything that happened in between visible" | 01 §6 US-02…04, 02 §6.2 | T-07…T-13 | AC-03, AC-12 | DV · IP |
| G-11 | p. 3 PS-1 ¶2 | P0 | Messy inputs: native and scanned; itemised and bundled; tax embedded or separated; PO explicit or implied; missing number, date or total | 01 §5.4, 03 §4.1 | T-07a/b, T-11b | AC-10, AC-11 (REG-05, REG-10) | DV · IP |
| G-12 | p. 3 PS-1 ¶3 | P0 | Procurement logic: approved vendors, PO amounts, tolerances, duplicates, split invoices, close-not-exact amounts; decide and explain | 03 §4, 02 §7.4 | T-09…T-14 | AC-07, AC-08, AC-11 | DV · IP |
| G-13 | p. 3 "Edge cases — you define them" | P0 | 2–4 realistic, non-trivial edge cases where behaviour differs | 04 §4.2 (F1–F4) | T-16 | AC-06…AC-09 | DV · IP |
| G-14 | p. 6 Guidance 1 | P0 | Map the process on paper first: input, steps, decision points, output | 01 §2 | — | 01 §2 exists; stages match 03 §2.4 (AC-01) | DV |
| G-15 | p. 6 Guidance 2 | P0 | Happy path first, then edge cases one at a time | 05 §3 order | T-15 → T-16 | CP-1 before CP-2 | DV |
| G-16 | p. 6 Guidance 3 | P0 | Use AI deliberately; explain why each tool is there | 02 §3, 04 §5.8 | — | Talking points; video narration | DV |
| G-17 | p. 6 Guidance 4 | P0 | Prepare and rehearse demo runs; inputs ready; order known | 04 §5.2–5.4 | T-26 | AC-18 | DV · IP |
| G-18 | p. 6 Guidance 5 | P0 | Submit something that runs even if imperfect; be honest about limits | 05 §6.2 | — | Cut table; honest notes | DV |
| G-19 | p. 7 FAQ "Can I ask questions…" | P0 | Make assumptions, note them for the live pitch | 01 §10 | T-18 (About dialog) | AC-24 | DV · IP |
| G-20 | p. 7 FAQ "What tools…" | P0 | Any tools; must run live in the interview; **no Zamp or Pace** | 02 §3 | — | Dependency table has no Zamp/Pace | DV |
| G-21 | p. 7 FAQ "Does the process need to use real data?" | P0 | Own realistic invoice PDFs and PO dataset | 03 §5, 04 §4 | T-04a/b | Fixture manifest | DV · IP |
| G-22 | p. 7 FAQ "Do I need to build a UI?" | P0 | At minimum, show run status and outputs. p. 2 raises the bar. | 01 §7 | T-13, T-18 | AC-03, AC-04 | DV · IP |
| G-23 | p. 7 FAQ "What if I need more time?" | P0 | Email the coordinator before the deadline; submit what works; be honest | 05 §10 | — | UA-14 | DV |
| G-24 | p. 6 "What a strong submission looks like" | P0 | It runs; intuitive UI and dashboard; deliberate edge cases; video explains thinking; fluent live demo | All | All | AC-02…AC-18 | DV · IP |
| G-25 | p. 1 ¶3 | P0 | Graded on whether it works, the judgment behind design choices, and explanation to a **non-technical buyer** | 01 §4, 04 §5.8 | T-27 | Narration copy | DV |

**Observable grading signals.** These are the guide's own words; no rubric has been invented here. Each is listed with the evidence that answers it:

| Signal | Guide reference | Evidence |
|---|---|---|
| "whether your process actually works" | p. 1 | AC-02, AC-15 |
| "the judgment behind your design choices" | p. 1 | 05 §7.2, 04 §5.8 |
| "how you explain it to a non-technical buyer" | p. 1 | 01 §4, video |
| "The UI is part of the grade… live run view… dashboard" | p. 2 | AC-03, AC-04 |
| "The edge cases you choose tell us how well you understand the problem" | p. 3 | AC-06…AC-09 |
| "A demo that goes smoothly shows you know your build" | p. 6 | AC-18 |

### 4.2 User commitments (from the user's brief)

| ID | Locator (brief section) | Pri | Commitment | Design / contract | Task | Acceptance | Status |
|---|---|---|---|---|---|---|---|
| U-01 | Authority ¶1 | P1 | Hard $0 incremental spend; no card-requiring or overage-billing services | 02 §8, 06 §4 | T-01, T-25 | AC-21 | DV · IP |
| U-02 | Authority ¶2 | P1 | No CI/CD; manual release, smoke and rollback | 02 §11.6, 05 §6.3 | T-25 | AC-22 | DV · IP |
| U-03 | Authority ¶4 | P1 | Four demo families by default; a documented 2- or 3-case cut | 04 §4.2, 05 §6.2 | T-16 | AC-06…AC-09 | DV · IP |
| U-04 | Brief ¶1 | P1 | Retain source PDF, readings, corrections, matches, decisions and run history | 03 §1, 02 §6.2 | T-03…T-17 | AC-12 | DV · IP |
| U-05 | Brief ¶1 | P1 | Human approval against the current PO balance (approval consistency) | 02 §7.4, 03 §4.6 | T-14 | AC-08, AC-14 | DV · IP |
| U-06 | Experiment defaults | P1 | Baseline evaluation (B0 TF-IDF; B1 frozen MiniLM) | 04 §3 | T-20, T-23 | AC-19 | DV · IP |
| U-07 | Experiment defaults; Kaggle | P1 | Small genuine fine-tuning experiment (E1) | 04 §3.3, 3.8 | T-21, T-22 | AC-20 | DV · IP |
| U-08 | Authority ¶5 | P1 | Interviewer-accessible $0 live URL, proven early; manual deploy | 02 §8, §11 | T-01, T-15, T-25 | AC-15 | DV · IP |
| U-09 | Business rules | P1 | Decimal/NUMERIC/string money; same unit and net basis; separate quantity and amount checks; missing stays unresolved; disposition vocabulary | 03 §0.2, §4 | T-08, T-11 | AC-06…AC-11 | DV · IP |
| U-10 | Brief ¶1 | P1 | Procurement-specific matcher on realistic variations; improvement treated as a hypothesis | 02 §5, 04 §3 | T-10, T-20 | AC-19 | DV · IP |
| U-11 | Kaggle section | P1 | Heartbeat, checkpoints every ≤ 10 min, export, the 12 h and idle cutoffs, CPU fallback | 02 §10 | T-21, T-22 | AC-30 | DV · IP |
| U-12 | Authority ¶6 | P1 | Secrets and tokenised links kept out of the package, git and logs; PDFs treated as untrusted | 02 §9, §10.6 | T-24 | AC-23, REG-08 | DV · IP |
| U-13 | 01-PRD instructions | P1 | English/INR; one invoice to one PO; two-way match; explicit unit evidence; no payment execution | 01 §5 | — | 01 §5.4 table | DV |
| U-14 | Architecture | P1 | Preserve a working repo; else the FastAPI/worker/React/Postgres defaults | 02 §1 | T-00, T-02 | Contracts §9 mapping | DV · IP |
| U-15 | 04 instructions | P1 | Real native-text happy path **and** a real scanned case | 04 §4.2 | T-04, T-07b | AC-02, AC-10 | DV · IP |
| U-16 | Architecture; 04 instructions | P1 | Extraction separate from comparison; fixture labels, file names and scenario IDs never act as shortcuts | 02 §4, 04 §1, §4.5 | T-07, T-19 | AC-27 | DV · IP |
| U-17 | Header | P1 | Deadline 12 Nov 2026; internal cutoff with buffer | 05 §4 | — | RG-S time | DV · UA |
| U-18 | Worked example | P1 | SafeHands example kept and internally consistent | 03 §5.2 | T-04a | AC-02, AC-06 | DV |

Design choices are D-01…D-24 (05 §7.2). Stretch items are E2 focused re-read, the PO ledger page, the Benchmarks page and the WDC domain-transfer check (01 §5.2, 04 §3.7, §3.9).

### 4.3 Acceptance evidence (AC-IDs)

| ID | Evidence that must exist | Proven by |
|---|---|---|
| AC-01 | 01 §2 process map; UI stage list equals 03 §2.4 | Screenshot + doc |
| AC-02 | HP-01 → `ready_for_approval` with expected findings, locally **and** hosted | `pytest tests/fixtures_e2e -k HP-01`; smoke 02 §11.7 |
| AC-03 | Live run view updates stage by stage from real `run_events` (timestamps increase; OCR skipped vs run) | Screen recording / video |
| AC-04 | Dashboard lists ≥ 8 invoices across all statuses, with filters and outputs | Screenshot after rehearsal |
| AC-05 | Approving HP-01 moves PO-0147/1 from 400 → 1,000; audit entry | e2e test + UI |
| AC-06 | F1: EC-01b needs_review → correction → ready; EC-01b-ctl ready; EC-01c hold; EC-01d hold (exceeds by 100) | fixtures_e2e |
| AC-07 | F2: EC-02 hold (2 × R-PRC-01 + R-PRC-02 note + R-AMT-01); EC-02-ctl ready | fixtures_e2e |
| AC-08 | F3: EC-03 sequence (A approved; B 409 → v2 hold) and REG-14 20/20 | fixtures_e2e + concurrency |
| AC-09 | F4: EC-04 needs_review → 2 corrections → ready; EC-04-ctl ready + R-PO-03 note | fixtures_e2e |
| AC-10 | SC-01: `ocr` stage done → ready_for_approval on the configured host DPI (or a documented R-06 outcome) | fixtures_e2e + hosted timing |
| AC-11 | REG-01…REG-25 pass (incl. 01b, 07b, 07c) | `pytest -q` |
| AC-12 | PDF bytes byte-identical after restart; every reading has evidence; decisions versioned and stamped | Invariant test + smoke step 7 |
| AC-13 | Worker kill mid-run → completes as attempt 2, one decision (REG-07) | Integration test + hosted restart |
| AC-14 | Idempotent upload and approval replay (REG-11, REG-12) | Contract tests |
| AC-15 | HTTPS host URL works from a fresh browser on a separate network; anonymous 401 first; persistence; readiness | `release-evidence/rc-*.md` |
| AC-16 | Video ≤ 5:00; live HP + ≥ 1 live edge; narrated; Public link plays logged out | RG-V checklist |
| AC-17 | Submission email sent with both links before the cutoff | Sent mail (candidate) |
| AC-18 | Two clean hosted rehearsals of 04 §5.2 after demo reset, with timings | Progress log |
| AC-19 | B0 vs B1 (+ E1) on frozen test; selection rule applied; saved results labelled | `eval/REPORT.md` |
| AC-20 | E1 completed per 04 §3.8, or a precise partial/not-run status | `FINAL.json`, report |
| AC-21 | $0 audit: each service, its plan, and "no payment method on file" | 06 §4 table (design) + RG-H screenshots in `release-evidence/rc-*.md` (observed) |
| AC-22 | No `.github/workflows`; Render Auto-Deploy Off | `ls`, screenshot |
| AC-23 | Secret grep clean; logs contain no secrets | 02 §9.2 command output |
| AC-24 | Assumptions log visible in the app (About) and README | Screenshot |
| AC-25 | Keyboard-only upload → approve; axe: 0 serious/critical (target) | Checklist + axe counts |
| AC-26 | Measured ack, queue and run latency for HP-01, EC-02 and SC-01 per host | `latency-report` / diagnostics |
| AC-27 | Import boundary + filename invariance + price-invariance of matches (REG-17, REG-18) | Tests |
| AC-28 | 401/403/CSRF behaviour (REG-06); every route enumerated | Contract test |
| AC-29 | Each PRD §7.5 state demonstrated once | Checklist screenshots |
| AC-30 | Kaggle log: handover time, computed cutoffs, heartbeat JSONL, verified checkpoint checksums | `ml/kaggle/*.log` (no URL) |

## 5. Package index and remaining risks

| File | Purpose |
|---|---|
| `00-START-HERE.md` | This brief, authority, traceability |
| `01-PRD.md` | Users, process map, scope, stories, UX, NFRs, assumptions |
| `02-SYSTEM-DESIGN.md` | Architecture, stages, matching, concurrency, hosting, security, Kaggle |
| `03-CONTRACTS.md` | **Canonical** data model, states, API, rules, policy, seed, worked values |
| `04-EVALUATION-AND-DEMO.md` | Experiments, metrics, fixture manifest, video and interview scripts |
| `05-CODEX-HANDOFF.md` | Kickoff prompt, backlog, schedule, gates, risks/decisions, user actions |
| `06-CRITICAL-REVIEW.md` | Red-team review, simulations, consistency checks, residual risks |

The top remaining risks are listed in 06 §6:
- Render Free capacity at 0.1 CPU / 512 MB (R-01).
- Private DB networking on the Free plan (R-02).
- Cutoff time unknown (R-04).
- OCR exactness on SC-01 at 200 DPI (R-06).
- Postgres expiry around 10 Dec (R-09).
