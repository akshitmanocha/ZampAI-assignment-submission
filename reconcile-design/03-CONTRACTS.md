# 03 — Contracts: data, states, API, rules and policy

**This is the canonical reference.** All other documents use these names. Where they disagree, this file wins (see the authority order in `00-START-HERE.md` §2).

| Item | Value |
|---|---|
| Product | Reconcile: invoice PDF → evidence-backed AP decision (Zamp ASA case study PS-1, Finance/AP) |
| Package written | 2026-11-10, Asia/Kolkata (IST) |
| Repository evidence | **None available to the design run.** No Reconcile repository was found (`~/Downloads`, `~` to depth 3, checked 2026-11-10 11:26 IST). All tables, routes and paths below are **proposed defaults**. Task T-00 in `05-CODEX-HANDOFF.md` maps them onto existing code if a repo turns up. Keep verified existing names and record the mapping in §9. |
| Status of every contract | Design verified. **Implementation verification pending.** |

---

## 0. Conventions

### 0.1 Vocabulary (one meaning each)

| Term | Meaning | Not to be confused with |
|---|---|---|
| **Invoice** | One uploaded vendor bill, tracked from upload to approval or rejection. Row in `invoices`. | The PDF bytes (*document*). |
| **Document** | The original PDF bytes, content-addressed by SHA-256. These bytes never change. | — |
| **Run** | One execution of the pipeline for an invoice (`full` or `revalidate`). Runs have `run_state`. | A *job*, which is the queue record that drives a run. |
| **Stage** | One named step inside a run (§2.4). | — |
| **Event** | Append-only, timestamped record of a stage or run transition. | Audit entries, which record human or system actions on business records. |
| **Reading** | A value extracted from the document, with its raw text and evidence. It is never overwritten. | A *correction*. |
| **Evidence** | A pointer to the thing that justifies a value: a document span (page plus bbox), a reviewer attestation, master data or a policy default. | — |
| **Correction** | A reviewer-supplied value for an allowed field path, with a reason. It is stored next to the original reading, never in place of it. | — |
| **Finding** | The outcome of one rule for one subject (the invoice or one line), with expected/actual/delta and evidence. | — |
| **Decision** | A versioned set of findings plus a **recommendation**. | Approval. |
| **Recommendation** | `ready_for_approval` \| `hold` \| `needs_review`. Produced by software. It never moves money or ledger balances. | — |
| **Approval** | A human action. It re-checks against **current** state and atomically creates **allocations**. | — |
| **Allocation** | Quantity and net amount of a PO line consumed by an approved invoice. | — |
| **Remaining** | For a PO line: `ordered_qty − allocated_qty` (quantity) and `ordered_qty × unit_price − allocated_amount` (net amount). Pending, unapproved invoices do **not** reduce it. | — |
| **Base unit** | The PO line's unit of measure (`uom`), e.g. `EA` shown as "glove". | Invoice unit (e.g. `BOX`). |
| **Pack factor** | Base units per invoice unit (e.g. 100 gloves per box). It needs evidence. | — |
| **Net / gross** | Net = before GST. Gross = net + GST (+ round-off). PO prices are **net per base unit**. | — |

### 0.2 Value rules

- **IDs.** UUID strings in the API (`uuid` in the DB). Invoices also get a human `display_ref` `RC-000001`, from a DB sequence.
- **Decimals.** In Python, construct with `Decimal(str)` from the text token. **Never use `float`.** DB columns are `NUMERIC`. The API sends decimal **strings** matching `^-?\d+(\.\d+)?$`. Fixed scales:
  - quantity: 4 dp
  - unit price: 4 dp
  - amount: 2 dp
  - tax rate: a fraction with 4 dp (`0.0900` = 9 %)
- **Rounding.** `ROUND_HALF_UP`, applied only at the checkpoints in §4.3. All tolerance comparisons are **inclusive** (`<=`).
- **Time.**
  - Instants are `timestamptz`, stored in UTC and sent in the API as ISO-8601 with `Z`. The UI shows them in Asia/Kolkata.
  - Invoice and PO dates are calendar `date`s with no zone.
  - "Today" in date rules means the current Asia/Kolkata date.
- **Null.** `null` means "not found" or "not applicable". It is never `""` or `0`. Field status (`found | missing | ambiguous | invalid`) says which. **A missing value stays missing.** No rule may substitute a PO value for a missing invoice value.
- **Identifiers keep their exact printed form.** Invoice numbers, PO numbers, GSTINs and SKUs keep leading zeros and case as printed in `*_raw`/display columns. Lookups use a `*_key` that is uppercased with whitespace and `- / . _` removed. Leading zeros are kept: `000912` ≠ `912`.
- **Versions stamped on every run and decision:**
  - `parser_version` (e.g. `x1-native-0.1.0`)
  - `ocr_engine` (string reported by the Tesseract binary at runtime)
  - `matcher_version` (e.g. `b0-tfidf-charwb35-v1`)
  - `policy_version` (e.g. `2026.11.1`)
  - `code_version` (git SHA, injected at image build)

---

## 1. Data model (PostgreSQL ≥ 15)

Proposed DDL; translate 1:1 into SQLAlchemy 2 models and Alembic revision `0001_initial`. `created_at/updated_at timestamptz NOT NULL DEFAULT now()` on every mutable table (elided below).

### 1.1 Users and sessions

```sql
CREATE TYPE user_role AS ENUM ('clerk','approver','admin');
CREATE TABLE users (
  id uuid PRIMARY KEY,
  email text NOT NULL,
  display_name text NOT NULL,
  role user_role NOT NULL,              -- approver ⊇ clerk permissions; admin = demo ops only
  password_hash text NOT NULL,          -- argon2id, produced by the maintained auth library (02 §9.1)
  is_active boolean NOT NULL DEFAULT true
);
CREATE UNIQUE INDEX uq_users_email ON users (lower(email));
-- Session/token table: whatever the chosen auth library requires (server-side, revocable, 12 h expiry).
```

### 1.2 Vendor master and purchase orders

```sql
CREATE TYPE vendor_status AS ENUM ('approved','pending','blocked');
CREATE TABLE vendors (
  id uuid PRIMARY KEY,
  vendor_code text UNIQUE NOT NULL,                  -- 'VEN-0001'
  legal_name text NOT NULL,
  gstin text UNIQUE NULL
    CHECK (gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'),  -- format only; checksum deferred (D-19)
  state_code char(2) NULL,
  status vendor_status NOT NULL,
  revision int NOT NULL DEFAULT 1                    -- ++ on any change; captured in decisions
);
CREATE TABLE vendor_aliases (
  id uuid PRIMARY KEY,
  vendor_id uuid NOT NULL REFERENCES vendors ON DELETE RESTRICT,
  alias text NOT NULL,
  alias_key text NOT NULL UNIQUE                     -- globally unique: an alias resolves to exactly one vendor
);

CREATE TYPE po_status AS ENUM ('open','closed','cancelled');
CREATE TABLE purchase_orders (
  id uuid PRIMARY KEY,
  po_number text NOT NULL UNIQUE,                    -- exactly as issued, e.g. 'PO-2026-0147'
  po_number_key text NOT NULL UNIQUE,                -- 'PO20260147'
  vendor_id uuid NOT NULL REFERENCES vendors,
  status po_status NOT NULL,
  currency char(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
  price_basis text NOT NULL DEFAULT 'net' CHECK (price_basis = 'net'),
  order_date date NOT NULL,
  revision int NOT NULL DEFAULT 1                    -- ++ on header/line change (not on allocation)
);
CREATE TABLE po_revisions (                          -- immutable snapshot per revision
  id uuid PRIMARY KEY,
  po_id uuid NOT NULL REFERENCES purchase_orders,
  revision int NOT NULL,
  snapshot jsonb NOT NULL,
  reason text NOT NULL,
  UNIQUE (po_id, revision)
);
CREATE TABLE po_lines (
  id uuid PRIMARY KEY,
  po_id uuid NOT NULL REFERENCES purchase_orders,
  line_no int NOT NULL,
  item_code text NOT NULL,                           -- buyer item code, e.g. 'GLV-NIT-M-PF'
  description text NOT NULL,
  attributes jsonb NOT NULL DEFAULT '{}',            -- {"material":"nitrile","size":"medium",...} (02 §5.4)
  uom text NOT NULL,                                 -- canonical unit code: EA, BOX, REAM, RACK, ...
  uom_label text NOT NULL,                           -- display noun: 'glove', 'ream'
  ordered_qty numeric(18,4) NOT NULL CHECK (ordered_qty > 0),
  unit_price numeric(18,4) NOT NULL CHECK (unit_price >= 0),   -- NET per uom
  tax_rate numeric(7,4) NULL,                        -- total GST fraction expected, e.g. 0.1800
  allocated_qty numeric(18,4) NOT NULL DEFAULT 0,
  allocated_amount numeric(18,2) NOT NULL DEFAULT 0,
  allocations_version int NOT NULL DEFAULT 0,        -- ++ on every allocation; drives staleness
  UNIQUE (po_id, line_no),
  CONSTRAINT ck_po_line_not_overallocated CHECK (allocated_qty <= ordered_qty)  -- race backstop (policy qty tolerance = 0)
);
```

### 1.3 Documents, invoices, runs, jobs

```sql
CREATE TABLE stored_objects (                        -- immutable
  sha256 char(64) PRIMARY KEY,
  byte_size bigint NOT NULL CHECK (byte_size > 0),
  content_type text NOT NULL CHECK (content_type = 'application/pdf'),
  backend text NOT NULL CHECK (backend IN ('postgres','local','s3')),
  storage_key text NOT NULL
);
CREATE TABLE object_blobs (                          -- only for backend='postgres' (hosted default, 02 §8)
  sha256 char(64) PRIMARY KEY REFERENCES stored_objects,
  bytes bytea NOT NULL
);

CREATE TYPE review_state   AS ENUM ('open','approved','rejected');
CREATE TYPE recommendation AS ENUM ('ready_for_approval','hold','needs_review');
CREATE SEQUENCE invoice_display_seq;
CREATE TABLE invoices (
  id uuid PRIMARY KEY,
  display_ref text NOT NULL UNIQUE,                  -- 'RC-' || lpad(nextval,6,'0')
  document_sha256 char(64) NOT NULL REFERENCES stored_objects,
  original_filename text NOT NULL,                   -- display only. NEVER read by pipeline logic (AC-27)
  source text NOT NULL DEFAULT 'upload' CHECK (source IN ('upload','seed')),
  uploaded_by uuid NOT NULL REFERENCES users,
  uploaded_at timestamptz NOT NULL,
  review_state review_state NOT NULL DEFAULT 'open',
  latest_run_id uuid NULL,                           -- FK added after runs exists (see ALTER below)
  current_decision_id uuid NULL,                     -- FK added after decisions exists (see ALTER below)
  -- denormalised from the current decision, for list/filter only (never used as rule input):
  vendor_id uuid NULL REFERENCES vendors,
  po_id uuid NULL REFERENCES purchase_orders,
  invoice_number text NULL,
  invoice_number_key text NULL,
  invoice_date date NULL,
  net_total numeric(18,2) NULL,
  gross_total numeric(18,2) NULL,
  recommendation recommendation NULL,
  row_version int NOT NULL DEFAULT 1                 -- ++ on every update (optimistic UI refresh)
);
CREATE UNIQUE INDEX uq_invoices_approved_business_key
  ON invoices (vendor_id, invoice_number_key) WHERE review_state = 'approved';   -- DB backstop vs double-paying
CREATE INDEX ix_invoices_list   ON invoices (uploaded_at DESC, id DESC);
CREATE INDEX ix_invoices_dupkey ON invoices (vendor_id, invoice_number_key) WHERE review_state <> 'rejected';
CREATE INDEX ix_invoices_sha    ON invoices (document_sha256) WHERE review_state <> 'rejected';

CREATE TYPE run_state AS ENUM ('queued','running','completed','processing_failed');
CREATE TYPE run_kind  AS ENUM ('full','revalidate');
CREATE TABLE runs (
  id uuid PRIMARY KEY,
  invoice_id uuid NOT NULL REFERENCES invoices,
  run_no int NOT NULL,                               -- 1,2,3… per invoice
  kind run_kind NOT NULL,
  trigger text NOT NULL CHECK (trigger IN ('upload','correction','retry','master_data_changed','seed')),
  base_run_id uuid NULL REFERENCES runs,             -- revalidate: readings come from here
  state run_state NOT NULL DEFAULT 'queued',
  attempt int NOT NULL DEFAULT 0,                    -- mirrors jobs.attempts
  queued_at timestamptz NOT NULL,
  started_at timestamptz NULL,
  finished_at timestamptz NULL,
  error_code text NULL,                              -- §3.7 run error codes
  error_message text NULL,                           -- redacted, user-safe
  parser_version text NULL,
  ocr_engine text NULL,
  matcher_version text NULL,
  policy_version text NULL,
  code_version text NOT NULL,
  UNIQUE (invoice_id, run_no)
);
CREATE UNIQUE INDEX uq_runs_one_active ON runs (invoice_id) WHERE state IN ('queued','running');

CREATE TABLE run_events (                            -- append-only
  id bigserial PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES runs,
  seq int NOT NULL,                                  -- assigned inside the fenced write txn
  attempt int NOT NULL,
  at timestamptz NOT NULL,
  stage text NULL,                                   -- §2.4 stage id
  type text NOT NULL,                                -- §2.5
  summary text NULL,                                 -- user-facing one-liner
  data jsonb NOT NULL DEFAULT '{}',                  -- counts, durations, error_code; never document text dumps or secrets
  UNIQUE (run_id, seq)
);

CREATE TYPE job_state AS ENUM ('queued','leased','done','dead');
CREATE TABLE jobs (
  id uuid PRIMARY KEY,
  run_id uuid NOT NULL UNIQUE REFERENCES runs,       -- exactly one job per run
  state job_state NOT NULL DEFAULT 'queued',
  attempts int NOT NULL DEFAULT 0,
  max_attempts int NOT NULL DEFAULT 3,
  available_at timestamptz NOT NULL DEFAULT now(),
  lease_owner text NULL,
  lease_expires_at timestamptz NULL,
  fencing_token bigint NOT NULL DEFAULT 0,           -- ++ on every claim
  last_error_code text NULL
);
CREATE INDEX ix_jobs_ready  ON jobs (available_at)     WHERE state = 'queued';
CREATE INDEX ix_jobs_leased ON jobs (lease_expires_at) WHERE state = 'leased';
CREATE TABLE worker_heartbeats (
  worker_id text PRIMARY KEY,
  pid int NOT NULL,
  code_version text NOT NULL,
  started_at timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL
);
```

### 1.4 Extraction, evidence, corrections

```sql
CREATE TABLE text_layers (                           -- immutable; cache PER INVOICE (reused only by retry/revalidate runs of the same invoice)
  id uuid PRIMARY KEY,
  invoice_id uuid NOT NULL REFERENCES invoices,      -- a new upload of the same bytes always re-reads (no cross-invoice cache: keeps "live" OCR live after demo-reset)
  document_sha256 char(64) NOT NULL REFERENCES stored_objects,
  method text NOT NULL CHECK (method IN ('native','ocr')),
  engine_version text NOT NULL,
  params_hash char(64) NOT NULL,                     -- sha256 of canonical params (dpi, psm, lang)
  params jsonb NOT NULL,
  pages jsonb NOT NULL,                              -- [{page, width_pt, height_pt, words:[{t,x0,y0,x1,y1,conf}]}]
  UNIQUE (invoice_id, method, engine_version, params_hash)
);

CREATE TABLE evidence (                              -- immutable
  id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES runs,
  kind text NOT NULL CHECK (kind IN ('document_span','reviewer_attestation','master_data','policy_default')),
  page int NULL CHECK (page >= 1),                   -- 1-based PHYSICAL page index in the PDF (not printed page labels)
  bbox numeric(8,2)[] NULL,                          -- [x0,y0,x1,y1] in PDF points, origin TOP-LEFT of the page's CropBox
  text text NULL,                                    -- the span text as read (≤ 300 chars)
  source text NULL CHECK (source IN ('native','ocr')),
  ocr_confidence numeric(5,2) NULL,                  -- 0–100, Tesseract word mean
  correction_id uuid NULL,                           -- for reviewer_attestation
  ref jsonb NULL                                     -- master_data/policy_default: {"table":"po_lines","id":…} or {"policy_key":…}
);

CREATE TYPE field_status AS ENUM ('found','missing','ambiguous','invalid');
CREATE TABLE extracted_fields (                      -- immutable per run
  id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES runs,
  field_path text NOT NULL,                          -- §1.6 grammar
  status field_status NOT NULL,
  raw_text text NULL,                                -- exactly as read
  value text NULL,                                   -- canonical string (decimal string, ISO date, code)
  value_type text NOT NULL CHECK (value_type IN ('text','decimal','date','code','unit','bool','uuid')),
  confidence numeric(5,4) NULL,
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  alternatives jsonb NULL,                           -- ambiguous: [{value, evidence_ids}]
  origin text NOT NULL CHECK (origin IN ('extracted','corrected','reused')),
  correction_id uuid NULL,
  UNIQUE (run_id, field_path)
);

CREATE TABLE invoice_lines (                         -- normalised lines, immutable per run
  id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES runs,
  line_no int NOT NULL,                              -- 1-based, document order
  description text NULL,
  item_code_printed text NULL,
  hsn text NULL,
  qty numeric(18,4) NULL,
  unit_raw text NULL,
  unit text NULL,                                    -- canonical unit code
  unit_price numeric(18,4) NULL,                     -- as printed, on printed basis
  amount numeric(18,2) NULL,                         -- as printed, on printed basis
  price_includes_tax boolean NOT NULL DEFAULT false,
  tax_rate numeric(7,4) NULL,
  unit_price_net numeric(18,4) NULL,                 -- net per INVOICE unit (= unit_price, or round4(unit_price/(1+rate)) if inclusive) — PO-independent
  amount_net numeric(18,2) NULL,                     -- checkpoint C3 — PO-independent
  pack_candidates jsonb NOT NULL DEFAULT '[]',       -- [{factor:"100", outer_unit:"BOX", inner_unit:"EA"|null, inner_text:"gloves", evidence_id}] — recorded, NEVER applied here
  attributes jsonb NOT NULL DEFAULT '{}',
  is_bundle boolean NOT NULL DEFAULT false,
  UNIQUE (run_id, line_no)
);

CREATE TABLE corrections (                           -- append-only
  id uuid PRIMARY KEY,
  invoice_id uuid NOT NULL REFERENCES invoices,
  base_run_id uuid NOT NULL REFERENCES runs,        -- = run of the highest-version decision with origin='run' at correction time
  field_path text NOT NULL,
  previous_value text NULL,                          -- what the base run had (reading or earlier correction)
  new_value text NULL,
  reason text NOT NULL CHECK (char_length(reason) BETWEEN 3 AND 500),
  created_by uuid NOT NULL REFERENCES users,
  applied_in_run_id uuid NULL REFERENCES runs
);
```

### 1.5 Decisions, findings, approvals, allocations, audit, idempotency

```sql
CREATE TABLE decisions (                             -- immutable; one row per version
  id uuid PRIMARY KEY,
  invoice_id uuid NOT NULL REFERENCES invoices,
  version int NOT NULL,                              -- 1,2,3… per invoice
  origin text NOT NULL CHECK (origin IN ('run','approval_check')),
  run_id uuid NULL REFERENCES runs,                  -- NULL when origin='approval_check'
  recommendation recommendation NOT NULL,
  summary text NOT NULL,                             -- one sentence, plain English
  next_action text NOT NULL,
  vendor_id uuid NULL, vendor_revision int NULL,
  po_id uuid NULL,     po_revision int NULL,
  ledger_snapshot jsonb NOT NULL,                    -- {po_line_id: {remaining_qty, remaining_amount, allocations_version}}
  inputs_fingerprint char(64) NOT NULL,              -- sha256(canonical readings+corrections, revisions, ledger snapshot, policy, matcher)
  policy_version text NOT NULL, matcher_version text NOT NULL,
  parser_version text NULL, code_version text NOT NULL,
  UNIQUE (invoice_id, version)
);

CREATE TYPE finding_outcome AS ENUM ('pass','fail','unknown','not_evaluated','not_applicable');
CREATE TYPE finding_effect  AS ENUM ('block','review','none');
CREATE TABLE findings (                              -- immutable
  id uuid PRIMARY KEY,
  decision_id uuid NOT NULL REFERENCES decisions,
  rule_id text NOT NULL, rule_version int NOT NULL,
  subject text NOT NULL,                             -- 'invoice' | 'line:<n>' | 'po_line:<po_number>/<line_no>'
  outcome finding_outcome NOT NULL,
  effect finding_effect NOT NULL,
  message text NOT NULL,
  expected text NULL, actual text NULL, delta text NULL, unit text NULL,   -- decimal strings
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  details jsonb NOT NULL DEFAULT '{}',               -- formula inputs, tolerance used, blocked_by
  sort_key int NOT NULL                              -- §4.4 ordering
);

CREATE TABLE line_matches (                          -- immutable
  id uuid PRIMARY KEY,
  decision_id uuid NOT NULL REFERENCES decisions,
  invoice_line_no int NOT NULL,
  status text NOT NULL CHECK (status IN ('assigned','ambiguous','no_match','conflict','bundle_unsupported')),
  po_line_id uuid NULL REFERENCES po_lines,
  assigned_by text NULL CHECK (assigned_by IN ('matcher','reviewer')),
  score numeric(6,4) NULL, margin numeric(6,4) NULL,
  candidates jsonb NOT NULL,                         -- §3.6 candidate object, best first
  -- unit conversion, decided AFTER assignment (02 §5.6); null unless status='assigned'
  conversion_status text NULL CHECK (conversion_status IN ('same_unit','pack_factor','missing_evidence','incompatible')),
  pack_factor numeric(18,4) NULL,                    -- base units per invoice unit actually applied
  conversion_evidence_id uuid NULL REFERENCES evidence,   -- document_span or reviewer_attestation
  qty_base numeric(18,4) NULL,                       -- qty × pack_factor (exact, C7)
  base_unit text NULL,                               -- = po_line.uom
  unit_price_base_net numeric(18,4) NULL,            -- checkpoint C2
  UNIQUE (decision_id, invoice_line_no)
);

CREATE TABLE approvals (                             -- immutable; one per invoice
  id uuid PRIMARY KEY,
  invoice_id uuid NOT NULL UNIQUE REFERENCES invoices,
  decision_id uuid NOT NULL REFERENCES decisions,    -- the version that was approved
  approved_by uuid NOT NULL REFERENCES users,
  approved_at timestamptz NOT NULL,
  approval_check jsonb NOT NULL,                     -- ledger at approval time + rules re-evaluated
  comment text NULL
);
CREATE TABLE allocations (                           -- immutable (reversal deferred, D-21)
  id uuid PRIMARY KEY,
  approval_id uuid NOT NULL REFERENCES approvals,
  invoice_id uuid NOT NULL REFERENCES invoices,
  po_line_id uuid NOT NULL REFERENCES po_lines,
  qty_base numeric(18,4) NOT NULL CHECK (qty_base > 0),
  amount_net numeric(18,2) NOT NULL CHECK (amount_net >= 0),
  UNIQUE (invoice_id, po_line_id)
);
CREATE TABLE rejections (
  id uuid PRIMARY KEY,
  invoice_id uuid NOT NULL UNIQUE REFERENCES invoices,
  decision_id uuid NULL REFERENCES decisions,
  rejected_by uuid NOT NULL REFERENCES users,
  rejected_at timestamptz NOT NULL,
  reason text NOT NULL
);

CREATE TABLE audit_entries (                         -- append-only
  id bigserial PRIMARY KEY,
  at timestamptz NOT NULL DEFAULT now(),
  actor_kind text NOT NULL CHECK (actor_kind IN ('user','worker','system')),
  actor_id uuid NULL,
  action text NOT NULL,                              -- §1.8
  entity_type text NOT NULL, entity_id uuid NULL,
  request_id text NULL,
  details jsonb NOT NULL DEFAULT '{}'                -- no secrets, no document text
);

CREATE TABLE idempotency_records (
  user_id uuid NOT NULL,
  scope text NOT NULL,                               -- 'POST /api/invoices' | 'POST /api/invoices/{id}/approve:<id>' …
  key text NOT NULL,                                 -- client UUID
  request_hash char(64) NOT NULL,
  response_status int NULL,                          -- NULL only inside the inserting txn; set before COMMIT (never visible as NULL)
  response_body jsonb NULL,
  completed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,                   -- created_at + 24 h
  PRIMARY KEY (user_id, scope, key)
);

CREATE TABLE policy_versions (                       -- written at startup from the YAML file
  version text PRIMARY KEY, sha256 char(64) NOT NULL, content jsonb NOT NULL, loaded_at timestamptz NOT NULL
);
CREATE TABLE demo_marker (id int PRIMARY KEY CHECK (id = 1), seeded_at timestamptz NOT NULL, seed_version text NOT NULL);

-- FK cycle invoices <-> runs/decisions: added after both tables exist (Alembic use_alter=True)
ALTER TABLE invoices
  ADD CONSTRAINT fk_inv_latest_run  FOREIGN KEY (latest_run_id)       REFERENCES runs      DEFERRABLE INITIALLY DEFERRED,
  ADD CONSTRAINT fk_inv_cur_decision FOREIGN KEY (current_decision_id) REFERENCES decisions DEFERRABLE INITIALLY DEFERRED;
```

### 1.6 Field-path grammar (readings and corrections)

`header.<name>` | `header.tax[<k>].<name>` | `lines[<n>].<name>` (n is 1-based `line_no`).

| Path | Type | Correctable? |
|---|---|---|
| `header.vendor_name`, `header.vendor_gstin` | text/code | Yes |
| `header.vendor_id` (choose a master vendor) | code | Yes (reviewer resolves an unknown vendor). Cannot point at a `blocked` vendor's alias conflict. |
| `header.invoice_number` | code | Yes |
| `header.invoice_date` | date | Yes |
| `header.po_reference` | code | Yes |
| `header.currency` | code | No (scope) |
| `header.subtotal`, `header.taxable_value`, `header.round_off`, `header.grand_total` | decimal | Yes |
| `header.tax[k].kind` (`CGST/SGST/IGST`), `.rate`, `.amount` | code/decimal | Yes |
| `lines[n].description`, `.qty`, `.unit`, `.unit_price`, `.amount`, `.tax_rate` | various | Yes |
| `lines[n].pack_factor` | decimal > 0 | Yes. Creates `reviewer_attestation` evidence; the attested inner unit is the assigned PO line's `uom`. |
| `lines[n].po_line_id` | uuid | Yes, only to a candidate whose status is not `conflict`, that belongs to the invoice's PO, or (PO unresolved) to one of the candidate POs. If every non-bundle line is reviewer-assigned to lines of **one** PO, that PO becomes the resolved PO (R-PO-01 pass, `via=reviewer_line_choice`; 02 §5.2). |
| Anything on vendors, POs, policy or ledger | — | **Never** (422 `CORRECTION_INVALID`) |

### 1.7 Lifecycle, immutability, retention

| Record | Mutable fields | Retention (demo) |
|---|---|---|
| `stored_objects`, `object_blobs` | **None** (insert-only) | Until no invoice references them; `demo-reset` deletes unreferenced ones |
| `text_layers`, `evidence`, `extracted_fields`, `invoice_lines`, `decisions`, `findings`, `line_matches`, `approvals`, `allocations`, `rejections`, `corrections`, `run_events` | **None** (insert-only) | Deleted with their invoice by `demo-reset` |
| `audit_entries` | **None** (append-only) | Kept across `demo-reset` (a `demo.reset` entry records counts) |
| `invoices` | `review_state`, `latest_run_id`, `current_decision_id`, denormalised columns, `row_version` | Until `demo-reset` |
| `runs`, `jobs`, `worker_heartbeats` | state/lease fields | Until `demo-reset` |
| `po_lines` | `allocated_qty`, `allocated_amount`, `allocations_version` (only inside approval txn) | Seed data |
| `vendors`, `purchase_orders` | via revision++ (+ `po_revisions` snapshot) | Seed data |
| `idempotency_records` | `response_status`, `response_body`, `completed_at`: set **only inside the inserting transaction**, before COMMIT | 24 h (purged by worker housekeeping) |
| Sessions | per library | 12 h |

Production would need statutory retention for invoice records (Indian GST law requires multi-year record keeping; confirm the period with finance/legal) and a legal-hold policy. Both are out of scope for the case study (A-11).

**Migrations and backfill.** On a fresh repo, `0001_initial` creates everything. If T-00 finds existing tables:
1. Write an **expand** migration that adds new columns as nullable or defaulted. Never drop or rename in the same release.
2. Backfill existing invoices with `decisions.version=1, origin='run'`, using their current status mapped per §9, and `ledger_snapshot='{}'`.
3. Mark `parser_version='legacy'`.
4. Contract (drop or rename) only after the release is verified.

Every migration must run under `alembic upgrade head` from an empty DB **and** from the previous head (T-03 acceptance).

### 1.8 Audit actions

`auth.login`, `auth.login_failed`, `auth.forbidden`, `invoice.uploaded`, `run.queued`, `run.completed`, `run.failed`, `run.lease_recovered`, `correction.saved`, `decision.created`, `approval.approved`, `approval.stale`, `approval.replayed`, `invoice.rejected`, `demo.reset`, `demo.seeded`.

---

## 2. States and transitions

### 2.1 Run state (`runs.state`)

```
queued ──claim──▶ running ──success──▶ completed
  ▲                 │
  └─retryable error / lease expired (attempts < max)
                    │
                    └─permanent error, or attempts exhausted ──▶ processing_failed
```

| From → To | Trigger | Writer |
|---|---|---|
| (new) → `queued` | Upload txn, correction txn, retry txn, approval txn on master-data change (§4.6) | API |
| `queued` → `running` | Job claimed (`attempts += 1`, fence `+= 1`) | Worker |
| `running` → `queued` | Retryable error (`available_at = now + 10 s × 2^(attempts−1)`), **or** lease expiry detected at claim time | Worker / next claimer |
| `running` → `completed` | Finalize txn (decision written) | Worker (fenced) |
| `running` → `processing_failed` | Permanent error code, or attempt `max_attempts` fails | Worker (fenced) or claimer on expired lease with attempts exhausted |
| `processing_failed` → (terminal) | User *Retry* creates a **new** run (`trigger='retry'`). The failed run is never reused. | API |

Job state mirrors this: `queued`/`leased` while `queued`/`running`, `done` on `completed`, `dead` on `processing_failed`.

### 2.2 Recommendation

A recommendation exists only on a `decision`. It changes only when a **new decision version** is written: after a run completes, or after an approval-time re-check fails (`origin='approval_check'`). `invoices.current_decision_id` always points at the highest version.

### 2.3 Review state (`invoices.review_state`)

| From → To | Allowed when | Route |
|---|---|---|
| `open` → `approved` | Caller is `approver`; no active run; **latest run `completed`** (a failed revalidate run means the reviewer's latest correction was never evaluated → 409 `NOT_APPROVABLE`, `details.reason="latest_run_failed"`); `expected_decision_version` = current; current recommendation `ready_for_approval`; the approval-time re-check (§4.6) is still `ready_for_approval` | `POST …/approve` |
| `open` → `rejected` | Caller is `clerk` or `approver`; no active run | `POST …/reject` |
| `approved` / `rejected` | Terminal (reversal/void deferred, D-21) | — |

**Displayed status** (one pill, derived, never stored):
1. `approved` → **Approved**
2. `rejected` → **Rejected**
3. Latest run `queued`/`running` → **Processing**
4. Latest run `processing_failed` → **Processing failed** (if an earlier decision exists, it is shown greyed with "latest re-check failed")
5. Otherwise the recommendation label: **Ready for approval** / **On hold** / **Needs review**

API enum `display_status` ∈ {`processing`, `processing_failed`, `ready_for_approval`, `hold`, `needs_review`, `approved`, `rejected`}. The `status` filter and the `counts{}` keys of `GET /api/invoices` use exactly these values.

**Stale flag** (`is_stale`, computed on read): true when the current recommendation is `ready_for_approval` and any of these has changed since the decision:
- `vendor.revision` ≠ snapshot
- `po.revision` ≠ snapshot
- any assigned PO line's `allocations_version` ≠ snapshot

UI copy: *"The PO balance changed after this check. Approving will re-check against the current balance."* The invoice detail page re-fetches `GET /api/invoices/{id}` on window focus/`visibilitychange` and every 10 s while `display_status=ready_for_approval`, so a second tab shows the banner without a manual reload.

### 2.4 Stages (fixed order; IDs are API values)

| # | `stage` | Full run | Revalidate run |
|---|---|---|---|
| 1 | `intake` | Verify stored bytes (sha256), PDF metadata | `skipped` — "Reused document" |
| 2 | `text_layer` | Native words + bboxes per page | `skipped` — "Reused run #n" |
| 3 | `ocr` | Pages lacking native text only; else `skipped` "Not needed" | `skipped` |
| 4 | `field_extraction` | Header, lines, totals → readings + evidence | `done` — "Reused run #n readings + k corrections" |
| 5 | `normalization` | Decimal, dates, units, pack **candidates** (recorded, not applied), net basis, bundle flag | ✔ |
| 6 | `vendor_match` | §02-5.1 | ✔ |
| 7 | `po_match` | §02-5.2 | ✔ |
| 8 | `line_match` | §02-5.3 identity, then §02-5.6 unit conversion per assigned line | ✔ (reviewer assignments honoured) |
| 9 | `policy_checks` | Rule matrix §4 | ✔ |
| 10 | `decision` | Disposition §4.5 | ✔ |
| 11 | `finalize` | Persist decision, update invoice pointers | ✔ |

Stage status: `pending → running → done | skipped | failed`.

### 2.5 Event types

`run.queued`, `run.claimed` {attempt, worker_id}, `run.lease_recovered` {previous_owner, previous_attempt}, `stage.started`, `stage.completed` {duration_ms, summary, counts}, `stage.skipped` {reason}, `stage.progress` {page, pages} (OCR, one per page), `stage.failed` {error_code, retryable}, `run.retry_scheduled` {available_at, attempt}, `run.completed` {decision_version, recommendation}, `run.failed` {error_code}.

---

## 3. HTTP API

### 3.1 Common rules

- **Same origin.** The React build is served by the API process. No CORS headers are sent, so cross-origin calls fail.
- **Auth.** HttpOnly + Secure + SameSite=Lax session cookie, issued by the auth library. Every `/api/*` route except `POST /api/auth/login` requires a valid session. Otherwise it returns **401** `UNAUTHENTICATED` with `WWW-Authenticate: Session realm="reconcile"`; this header identifies *our* gate in smoke tests (02 §9.6).
- **CSRF.** Unsafe methods require header `X-Reconcile-Client: web`. Without it: 403 `CSRF_HEADER_MISSING`.
- **Role matrix:**

| Route group | clerk | approver | admin |
|---|---|---|---|
| Read invoices, runs, documents, POs, benchmarks | ✔ | ✔ | ✔ |
| Upload, review/correct, reject, retry | ✔ | ✔ | ✘ |
| Approve | ✘ (403 `FORBIDDEN`) | ✔ | ✘ |
| `/api/admin/*` (demo reset, diagnostics) | ✘ | ✘ | ✔ |

`admin` is reserved for demo operations; its password is **never** shared with evaluators. Single tenant; every authenticated user sees all invoices (record authorization = role-based).

- **Idempotency.** `Idempotency-Key: <uuid>` is **required** on `POST /api/invoices`, `…/review`, `…/approve`, `…/reject` and `…/retry`. Scope = (user, method + route + resource id). Semantics:
  - **Same key, same request hash, completed:** replay the stored status and body, with header `Idempotent-Replayed: true`.
  - **Same key, different hash:** 422 `IDEMPOTENCY_KEY_REUSED`.
  - **Same key while the first is still in flight:** the second request blocks on the PK insert inside the business transaction (lock_timeout 5 s). It then replays, or returns 409 `IDEMPOTENCY_IN_PROGRESS` (retryable).
  - The record is inserted **in the same DB transaction as the business effect**. Either both commit or neither does.
  - Request hash = sha256(method, path, canonical JSON body). For uploads: file sha256 plus filename.
  - **Which outcomes are stored** (so a same-key retry replays them):

    | Outcome | Record |
    |---|---|
    | 2xx | Stored and committed with the effect |
    | 409 `APPROVAL_STALE` (both reasons), `DECISION_VERSION_CONFLICT`, `NOT_APPROVABLE`, `INVOICE_CLOSED`; 422 `CORRECTION_INVALID` | Stored and committed |
    | `RUN_IN_PROGRESS`, `IDEMPOTENCY_IN_PROGRESS`, 429, 5xx, lock timeouts, upload validation errors (413/415/422 PDF_*) | **Rolled back**: no record, so a later retry with the same key is evaluated fresh |
- **Error envelope:**

```json
{"error": {"code": "PDF_ENCRYPTED", "message": "This PDF is password-protected. Upload an unprotected copy.",
           "retryable": false, "request_id": "req_7Hq2c9", "details": {}}}
```

- **Pagination.** `?limit=` (default 25, max 100) and `?cursor=` (opaque base64url of `{uploaded_at, id}`). Order is `uploaded_at DESC, id DESC`. The response carries `next_cursor` (null at the end).
- **Upload limits.** `MAX_UPLOAD_BYTES=10485760` (10 MiB), `MAX_PAGES=10`, single file per request, field name `file`. The server checks magic bytes and content type; the extension is ignored. Rate limit: 60 uploads/hour/user and 10 login attempts/15 min/IP+email (429 `RATE_LIMITED` with `Retry-After`).

### 3.2 Routes

| Method & path | Roles | Request | Success | Errors |
|---|---|---|---|---|
| `POST /api/auth/login` | public | `{"email","password"}` | 204 + cookie | 401 `INVALID_CREDENTIALS`, 429 |
| `POST /api/auth/logout` | any | — | 204 | — |
| `GET /api/auth/me` | any | — | 200 `{id,email,display_name,role}` | 401 |
| `POST /api/invoices` | clerk, approver | multipart `file` + `Idempotency-Key` | **202** §3.3 | 400 `IDEMPOTENCY_KEY_REQUIRED`, 413 `PDF_TOO_LARGE`, 415 `UNSUPPORTED_MEDIA_TYPE`, 422 `PDF_INVALID`/`PDF_ENCRYPTED`/`PDF_TOO_MANY_PAGES`/`PDF_EMPTY`/`IDEMPOTENCY_KEY_REUSED`, 409 `IDEMPOTENCY_IN_PROGRESS`, 429, 503 |
| `GET /api/runs/{id}?after_seq=` | all | — | 200 §3.4 | 404 |
| `GET /api/invoices` | all | `status, vendor_id, po_number, q, from, to, limit, cursor` | 200 `{items[], next_cursor, counts{}}` | 422 |
| `GET /api/invoices/{id}` | all | — | 200 §3.5 | 404 |
| `GET /api/invoices/{id}/document` | all | — | 200 `application/pdf`, `Content-Disposition: inline`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff` | 404 |
| `POST /api/invoices/{id}/review` | clerk, approver | `{"expected_decision_version", "corrections":[{field_path,value,reason}]}`. `corrections` may be **empty**, which means **re-check** with current master data and ledger (e.g. after a duplicate was rejected). | **202** `{run}` (revalidate) | 409 `RUN_IN_PROGRESS`/`DECISION_VERSION_CONFLICT`/`INVOICE_CLOSED`, 422 `CORRECTION_INVALID` |
| `POST /api/invoices/{id}/approve` | approver | `{"expected_decision_version", "comment"?}` | 200 `approved` or `already_approved` §3.6 | 409 `APPROVAL_STALE`/`DECISION_VERSION_CONFLICT`/`NOT_APPROVABLE`/`RUN_IN_PROGRESS`/`INVOICE_CLOSED`, 403 |
| `POST /api/invoices/{id}/reject` | clerk, approver | `{"reason", "expected_decision_version"?}` | 200 | 409 `INVOICE_CLOSED`/`RUN_IN_PROGRESS` |
| `POST /api/invoices/{id}/retry` | clerk, approver | — | **202** `{run}`: same `kind` and `base_run_id` as the failed run; a revalidate retry re-applies the corrections whose `applied_in_run_id` is the failed run | 409 `RETRY_NOT_ALLOWED` (latest run not `processing_failed`) |
| `GET /api/purchase-orders?vendor_id=` | all | — | 200 list | — |
| `GET /api/purchase-orders/{id}` | all | — | 200 ledger (§3.6 `ledger`) | 404 |
| `GET /api/benchmarks` | all | — | 200 saved evaluation JSON (`source:"saved"`, `generated_at`, versions) | — |
| `GET /api/samples` | all | — | 200 `[{name, vendor, note}]`: six committed sample invoices (HP-01, EC-01b, EC-02, EC-02-ctl, EC-04, SC-01), with static UI notes ("expected in the seeded state"). Notes are display copy; the pipeline never reads them. | — |
| `GET /api/samples/{name}` | all | — | 200 `application/pdf` (same headers as `/document`) | 404 |
| `POST /api/admin/demo-reset` | **admin** | `{"confirm": "RESET DEMO DATA"}` + `Idempotency-Key` | 200 `{before:{…counts}, after:{…counts}}` | 403, 409 `NOT_DEMO_MODE`, 422 |
| `GET /api/admin/diagnostics` | **admin** | — | 200 `{verify_db:{…}, latency:{p50,p95 per stage}, db_size_bytes, worker:{…}}` | 403 |
| `GET /health/live` | public | — | 200 `{"status":"ok"}` (no dependency checks; used as the platform health check) | — |
| `GET /health/ready` | public | — | 200/503 `{"db":"ok","migrations":"at_head","worker_heartbeat_age_s":4,"ocr":"ok","blob_store":"ok","code_version":"a1b2c3d"}` | 503 with failing key; no secrets, hostnames or stack traces |

### 3.3 Upload: `202 Accepted`

```http
POST /api/invoices
Idempotency-Key: 3f0b8c52-1d6e-4b7a-9e21-6a0c4d8f2b17
X-Reconcile-Client: web
Content-Type: multipart/form-data; boundary=…   (file=SafeHands_SH-2526-0912.pdf)
```
```json
{
  "invoice": {"id": "9d2f6c1a-3b7e-4f0a-8c51-2e4b7a9d0f13", "display_ref": "RC-000004",
              "review_state": "open", "original_filename": "SafeHands_SH-2526-0912.pdf",
              "document_sha256": "5e1c…(64 hex)", "uploaded_at": "2026-11-10T09:02:11.204Z"},
  "run": {"id": "c4a1e8b2-6f3d-4a97-b2e0-5d8c1f7a3e20", "run_no": 1, "kind": "full", "state": "queued",
          "queue_position": 1},
  "notices": [],
  "links": {"run": "/api/runs/c4a1e8b2-6f3d-4a97-b2e0-5d8c1f7a3e20",
            "invoice": "/api/invoices/9d2f6c1a-3b7e-4f0a-8c51-2e4b7a9d0f13"}
}
```

If the bytes match an existing non-rejected invoice, `notices` contains `{"code":"SAME_FILE_SEEN","invoice_display_ref":"RC-000004"}`. The upload is **still accepted**, and rule R-DUP-03 holds it (§4). Byte-level dedupe changes storage only: one blob, two invoices.

### 3.4 Run: running, then terminal

Running, with an OCR fallback in progress (SC-01):

```json
{
  "id": "1b7e…", "invoice_id": "…", "display_ref": "RC-000009", "run_no": 1, "kind": "full", "trigger": "upload",
  "state": "running", "attempt": 1, "queued_at": "2026-11-10T09:10:00.012Z", "started_at": "2026-11-10T09:10:00.410Z",
  "finished_at": null, "current_stage": "ocr",
  "stages": [
    {"stage": "intake", "status": "done", "duration_ms": 44, "summary": "PDF 1.4 · 1 page · 412 KB · not encrypted"},
    {"stage": "text_layer", "status": "done", "duration_ms": 61, "summary": "No usable text on page 1 (0 characters) — will OCR"},
    {"stage": "ocr", "status": "running", "summary": "Reading page 1 of 1 at 300 DPI"},
    {"stage": "field_extraction", "status": "pending"}, {"stage": "normalization", "status": "pending"},
    {"stage": "vendor_match", "status": "pending"}, {"stage": "po_match", "status": "pending"},
    {"stage": "line_match", "status": "pending"}, {"stage": "policy_checks", "status": "pending"},
    {"stage": "decision", "status": "pending"}, {"stage": "finalize", "status": "pending"}
  ],
  "events": [{"seq": 1, "at": "2026-11-10T09:10:00.012Z", "type": "run.queued"},
             {"seq": 2, "at": "2026-11-10T09:10:00.410Z", "type": "run.claimed", "data": {"attempt": 1}}],
  "result": null
}
```

Terminal: HP-01. Scores and durations are **illustrative** until they are measured.

```json
{
  "id": "c4a1e8b2-…", "state": "completed", "attempt": 1,
  "timings_ms": {"queue_wait": 527, "run": 4171},
  "versions": {"parser": "x1-native-0.1.0", "ocr_engine": null, "matcher": "b0-tfidf-charwb35-v1",
               "policy": "2026.11.1", "code": "a1b2c3d"},
  "stages": [
    {"stage": "normalization", "status": "done",
     "summary": "Line 1: 6 Box × 100 gloves/box = 600 gloves; ₹500.00/box = ₹5.0000/glove (net)"},
    {"stage": "vendor_match", "status": "done", "summary": "SafeHands Supplies Pvt. Ltd. — GSTIN exact match — approved"},
    {"stage": "po_match", "status": "done", "summary": "PO-2026-0147 printed on invoice — open"},
    {"stage": "line_match", "status": "done", "summary": "Line 1 → PO line 1 (medium nitrile, powder-free)"},
    {"stage": "policy_checks", "status": "done", "summary": "All required checks passed"},
    {"stage": "decision", "status": "done", "summary": "Ready for approval"}
  ],
  "result": {"decision_id": "e7b3a9d1-…", "decision_version": 1, "recommendation": "ready_for_approval",
             "summary": "Matches PO-2026-0147 line 1: 600 gloves at ₹5.00 each, within the 600 remaining.",
             "next_action": "Approve. Approval re-checks the current PO balance before reserving 600 gloves.",
             "counts": {"block": 0, "review": 0, "none": 0}}
}
```

### 3.5 Invoice detail (shape)

```json
{
  "invoice": {"id": "…", "display_ref": "RC-000004", "review_state": "open", "display_status": "ready_for_approval",
              "is_stale": false, "row_version": 3, "document_url": "/api/invoices/…/document"},
  "current_decision": {"version": 1, "recommendation": "ready_for_approval", "summary": "…", "next_action": "…",
                       "findings": ["…§3.6 finding objects…"], "line_matches": ["…"], "ledger": ["…"]},
  "readings": [{"field_path": "header.invoice_number", "status": "found", "raw_text": "SH/2526/0912",
                "value": "SH/2526/0912", "origin": "extracted",
                "evidence": [{"id": "…", "kind": "document_span", "page": 1,
                              "bbox": ["402.10", "96.40", "488.75", "108.20"], "source": "native",
                              "text": "SH/2526/0912"}]}],
  "lines": [{"line_no": 1, "description": "Nitrile Examination Gloves, Medium, Powder-Free, Blue — Box of 100 gloves",
             "qty": "6.0000", "unit": "BOX", "unit_price": "500.0000", "amount": "3000.00",
             "unit_price_net": "500.0000", "amount_net": "3000.00",
             "pack_candidates": [{"factor": "100", "outer_unit": "BOX", "inner_unit": "EA", "inner_text": "gloves",
                                  "evidence_id": "ev-pack-1"}],
             "match": {"status": "assigned", "po_number": "PO-2026-0147", "po_line_no": 1,
                       "conversion_status": "pack_factor", "pack_factor": "100.0000", "qty_base": "600.0000",
                       "base_unit": "EA", "unit_price_base_net": "5.0000", "conversion_evidence_id": "ev-pack-1"}}],
  "corrections": [], "runs": [{"run_no": 1, "kind": "full", "state": "completed", "finished_at": "…"}],
  "audit": [{"at": "…", "action": "invoice.uploaded", "actor": "AP Clerk (demo)"}],
  "allowed_actions": ["approve", "reject"]
}
```

`allowed_actions` is computed server-side from role and state (the UI hides buttons, but **the server enforces**).

### 3.6 Decision payloads

**Finding object:** `{rule_id, rule_version, subject, outcome, effect, message, expected, actual, delta, unit, evidence_ids[], details{}}`.

**Line-match candidate object:** `{po_line_id, po_number, line_no, item_code, description, score, sku_exact, agreements:[attr], conflicts:[{attr, invoice, po}], viable}`.

**Hold: EC-02, offsetting price variances.** The PO totals match; two lines do not.

```json
{
  "recommendation": "hold", "decision_version": 1,
  "summary": "Two line prices differ from PO-2026-0152. The totals match only because the differences cancel out.",
  "next_action": "Do not approve. Ask Kaveri Industrial Traders for a corrected invoice at PO prices.",
  "findings": [
    {"rule_id": "R-PRC-01", "subject": "line:1", "outcome": "fail", "effect": "block",
     "message": "Hex bolt M10×50: billed ₹13.50/EA, PO price ₹12.50 (+₹1.00; tolerance ₹0.125).",
     "expected": "12.5000", "actual": "13.5000", "delta": "1.0000", "unit": "INR/EA",
     "evidence_ids": ["ev-l1-rate", "ev-l1-desc"], "details": {"tolerance": "0.1250", "rule": "max(0.05, 1% × 12.50)"}},
    {"rule_id": "R-PRC-01", "subject": "line:2", "outcome": "fail", "effect": "block",
     "message": "Hex nut M10: billed ₹3.00/EA, PO price ₹4.00 (−₹1.00; tolerance ₹0.05).",
     "expected": "4.0000", "actual": "3.0000", "delta": "-1.0000", "unit": "INR/EA",
     "details": {"tolerance": "0.0500"}},
    {"rule_id": "R-PRC-02", "subject": "invoice", "outcome": "fail", "effect": "none",
     "message": "Line variances offset: +₹200.00 on line 1 and −₹200.00 on line 2. Net difference ₹0.00, so a total-only check would pass this invoice.",
     "details": {"line_amount_deltas": {"1": "200.00", "2": "-200.00"}, "sum": "0.00"}},
    {"rule_id": "R-AMT-01", "subject": "po_line:PO-2026-0152/1", "outcome": "fail", "effect": "block",
     "message": "Billed ₹2,700.00 net; ₹2,500.00 remains (tolerance ₹25.00).",
     "expected": "2500.00", "actual": "2700.00", "delta": "200.00", "unit": "INR"},
    {"rule_id": "R-AMT-01", "subject": "po_line:PO-2026-0152/2", "outcome": "pass", "effect": "none",
     "message": "Billed ₹600.00 net; ₹800.00 remains.", "expected": "800.00", "actual": "600.00"}
  ]
}
```

This example is truncated: the real payload contains **every** finding, including the passes for line 3, the arithmetic rules and the tax rules. The full worked values are in §5.3.

**Needs review: EC-04.** The invoice number is missing, there is no PO reference, and the line is ambiguous.

```json
{
  "recommendation": "needs_review", "decision_version": 1,
  "summary": "2 questions need an answer: the invoice number is missing, and it is unclear which PO this invoice is for.",
  "next_action": "Enter the invoice number and choose the PO line (200 µL or 1000 µL tips), then re-check.",
  "findings": [
    {"rule_id": "R-EXT-01", "subject": "invoice", "outcome": "unknown", "effect": "review",
     "message": "No invoice number found on the document."},
    {"rule_id": "R-PO-01", "subject": "invoice", "outcome": "unknown", "effect": "review",
     "message": "No PO number printed. Two open Meridian POs fit equally well: PO-2026-0155 (200 µL tips) and PO-2026-0158 (1000 µL tips). The invoice does not state the tip volume."},
    {"rule_id": "R-LINE-01", "subject": "line:1", "outcome": "not_evaluated", "effect": "none",
     "message": "Waiting for the PO to be chosen. Candidates: 1000 µL (PO-2026-0158) or 200 µL (PO-2026-0155) tips.",
     "details": {"blocked_by": ["R-PO-01"]}},
    {"rule_id": "R-PRC-01", "subject": "line:1", "outcome": "not_evaluated", "effect": "none",
     "message": "Waiting for the PO line to be chosen.", "details": {"blocked_by": ["R-LINE-01"]}},
    {"rule_id": "R-DUP-01", "subject": "invoice", "outcome": "not_evaluated", "effect": "none",
     "message": "Duplicate check needs an invoice number.", "details": {"blocked_by": ["R-EXT-01"]}}
  ],
  "line_matches": [{"invoice_line_no": 1, "status": "ambiguous", "po_line_id": null, "margin": "0.0100",
    "candidates": [
      {"po_number": "PO-2026-0158", "line_no": 1, "description": "Pipette tips 1000 µL, sterile, racked, 96 per rack",
       "score": "0.8420", "conflicts": [], "agreements": ["sterility", "pack:96/rack"], "viable": true},
      {"po_number": "PO-2026-0155", "line_no": 1, "description": "Pipette tips 200 µL, sterile, racked, 96 per rack",
       "score": "0.8320", "conflicts": [], "agreements": ["sterility", "pack:96/rack"], "viable": true}]}]
}
```

Scores are illustrative. The contract is PO-level margin `< po_reference.inference_min_margin` (0.10).

The `line_matches` row keeps the cross-PO candidates from inference (status `ambiguous`), so the UI's PO-line chooser can render them. The reviewer answers both questions with `header.invoice_number` and `lines[1].po_line_id`; the second also resolves the PO (§1.6, R-PO-01).

**Stale approval conflict: EC-03 step 2.**

```http
POST /api/invoices/5c1d…/approve
Idempotency-Key: 0b6f…   X-Reconcile-Client: web
{"expected_decision_version": 1}
```
```http
HTTP/1.1 409 Conflict
```
```json
{"error": {"code": "APPROVAL_STALE", "retryable": false, "request_id": "req_Q81mZ",
  "message": "Not approved. The PO balance changed after this invoice was checked; the re-check now says On hold.",
  "details": {
    "previous_decision_version": 1, "new_decision_version": 2, "recommendation": "hold",
    "findings": [
      {"rule_id": "R-QTY-01", "subject": "po_line:PO-2026-0149/1", "outcome": "fail", "effect": "block",
       "message": "Billed 300 gloves; only 200 remain on PO-2026-0149 line 1 (exceeds by 100).",
       "expected": "200.0000", "actual": "300.0000", "delta": "100.0000", "unit": "EA"},
      {"rule_id": "R-AMT-01", "subject": "po_line:PO-2026-0149/1", "outcome": "fail", "effect": "block",
       "message": "Billed ₹1,500.00 net; ₹1,000.00 remains (tolerance ₹50.00).",
       "expected": "1000.00", "actual": "1500.00", "delta": "500.00", "unit": "INR"}],
    "ledger": {"po_number": "PO-2026-0149", "line_no": 1, "ordered_qty": "1000.0000",
               "allocated_qty": "800.0000", "remaining_qty": "200.0000", "remaining_amount": "1000.00",
               "changed_by": [{"display_ref": "RC-000007", "invoice_number": "SH/2526/0931",
                               "approved_at": "2026-11-10T09:40:12.551Z"}]}}}}
```

Decision v2 (`origin='approval_check'`) is **committed** with the 409. The invoice now shows **On hold**, and an `approval.stale` audit entry is written. No allocation is made.

**Repeated successful approval.** The client retries after losing the response.
- **Same `Idempotency-Key`:** byte-identical replay of the first 200, with `Idempotent-Replayed: true`.
- **New key**, `expected_decision_version` equal to the approved version:

```json
{"result": "already_approved", "approval": {"id": "…", "decision_version": 1, "approved_by": "AP Approver (demo)",
 "approved_at": "2026-11-10T09:05:40.019Z"},
 "allocations": [{"po_number": "PO-2026-0147", "line_no": 1, "qty_base": "600.0000", "amount_net": "3000.00"}]}
```

No second allocation is made. If the version differs: 409 `DECISION_VERSION_CONFLICT`.

**First successful approval (HP-01):**

```json
{"result": "approved", "approval": {"id": "…", "decision_version": 1, "approved_at": "…"},
 "allocations": [{"po_number": "PO-2026-0147", "line_no": 1, "qty_base": "600.0000", "amount_net": "3000.00"}],
 "ledger": [{"po_number": "PO-2026-0147", "line_no": 1, "ordered_qty": "1000.0000",
             "allocated_qty_before": "400.0000", "allocated_qty_after": "1000.0000", "remaining_qty_after": "0.0000"}]}
```

### 3.7 Error codes

| Code | HTTP | Retryable | Meaning / UI copy |
|---|---|---|---|
| `UNAUTHENTICATED` | 401 | no | "Please sign in." |
| `INVALID_CREDENTIALS` | 401 | no | "Email or password is incorrect." |
| `FORBIDDEN` | 403 | no | "Your role (AP clerk) can't approve invoices. Ask an approver." |
| `CSRF_HEADER_MISSING` | 403 | no | Client bug |
| `NOT_FOUND` | 404 | no | — |
| `VALIDATION_ERROR` | 422 | no | Body schema violation |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | no | Client bug |
| `IDEMPOTENCY_KEY_REUSED` | 422 | no | Client bug |
| `IDEMPOTENCY_IN_PROGRESS` | 409 | **yes** | "Still working on your previous click…" |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | no | "Only PDF files are accepted." |
| `PDF_TOO_LARGE` | 413 | no | "This file is larger than 10 MB." |
| `PDF_INVALID` | 422 | no | "This file isn't a readable PDF." |
| `PDF_ENCRYPTED` | 422 | no | "This PDF is password-protected. Upload an unprotected copy." |
| `PDF_TOO_MANY_PAGES` | 422 | no | "This PDF has 14 pages; the limit is 10." |
| `PDF_EMPTY` | 422 | no | "This PDF has no pages." |
| `RUN_IN_PROGRESS` | 409 | yes | "Wait for the current check to finish." |
| `INVOICE_CLOSED` | 409 | no | "This invoice is already approved/rejected." |
| `DECISION_VERSION_CONFLICT` | 409 | no | "This invoice changed while you were looking. Refreshed." |
| `NOT_APPROVABLE` | 409 | no | "Only invoices that are Ready for approval can be approved." |
| `APPROVAL_STALE` | 409 | no | See §3.6 |
| `CORRECTION_INVALID` | 422 | no | Field-specific message |
| `RETRY_NOT_ALLOWED` | 409 | no | — |
| `NOT_DEMO_MODE` | 409 | no | Demo reset refused: `DEMO_MODE` is not `true` or `demo_marker` is missing |
| `RATE_LIMITED` | 429 | yes | "Too many requests. Try again in N seconds." |
| `SERVICE_UNAVAILABLE` | 503 | yes | "Reconcile can't reach its database right now. Your work is saved; try again shortly." |
| `INTERNAL` | 500 | yes | Generic message plus `request_id` |

**Run error codes** (`runs.error_code`, also on `stage.failed`):

| Code | Class | Notes |
|---|---|---|
| `PDF_PARSE_FAILED` | permanent | Validated at upload, but the worker parser failed |
| `EXTRACTION_SANDBOX_KILLED` | retryable once, then permanent | Memory or CPU limit hit |
| `OCR_TIMEOUT` | retryable | The retry uses `ocr_retry_dpi` |
| `OCR_ENGINE_UNAVAILABLE` | retryable | Binary missing ⇒ readiness is red too |
| `DB_UNAVAILABLE` | retryable | — |
| `MATCHER_UNAVAILABLE` | retryable | Model load failed; the B0 fallback is a config change, not automatic |
| `INTERNAL_ERROR` | retryable | — |
| `ATTEMPTS_EXHAUSTED` | terminal | Set when the last attempt fails |

An unreadable document (blank scan, OCR finds nothing) is **not** a technical failure. The run completes, the fields are `missing`, and the decision is `needs_review`.

---

## 4. Rules, disposition and policy

### 4.1 Rule matrix (policy `2026.11.1`, every rule `rule_version` 1)

Columns:
- **Req**: required. A required rule's `unknown` outcome forces `needs_review`.
- **Fail→** / **Unk→**: the finding effect for those outcomes. A `pass` always has effect `none`.
- **Dependency semantics.** A dependency marked **†** is a *gate*: it produces an input the rule needs (vendor, PO, assignment, conversion, field value). A rule is `not_evaluated` (effect `none`, `details.blocked_by=[…]`) when:
  - any gate dependency's outcome is `fail`, `unknown` or `not_evaluated`, **or**
  - any non-gate dependency is `unknown` or `not_evaluated`.

  `pass` and `not_applicable` let dependents run. A non-gate dependency that **failed** still lets the rule run: R-PRC-02 runs *because* R-PRC-01 failed. The root cause carries the effect, so not_evaluated rules never add one.

| Order | Rule | Depends on | Req | Condition (pass when…) | Units / tolerance | Fail→ | Unk→ | Evidence | Message (template) |
|---|---|---|---|---|---|---|---|---|---|
| 10 | R-SCOPE-01 | — | Y | Printed currency is INR (₹, Rs., INR). If none is printed: INR per `currency.default_when_absent`, with a note | — | review | — | Currency span or policy_default | "Invoice is in {cur}. This release handles INR only — process manually." |
| 11 | R-SCOPE-02 | — | Y | ≤ 1 distinct `po_number_key` printed | — | review | — | PO spans | "Invoice cites {n} POs ({list}). Multi-PO invoices aren't supported — split or process manually." |
| 12 | R-SCOPE-03 | — | Y | ≤ `limits.max_lines` lines; no credit-note markers ("Credit Note", negative grand total) | — | review | — | Title span | "This looks like a credit note / has {n} lines. Not supported in this release." |
| 20 | R-EXT-01 | — | Y | `header.invoice_number` found (or corrected) | — | — | review | Span | "No invoice number found on the document." |
| 21 | R-EXT-02 | — | Y | Date found, valid, and `≤ today_IST + dates.max_future_days` | days | review | review | Span | "Invoice date {d} is in the future." / "No invoice date found." |
| 22 | R-EXT-03 | — | Y | `header.grand_total` found | — | — | review | Span | "No invoice total found." |
| 23 | R-EXT-04 | — | Y | Each non-bundle line has qty, unit, unit_price and amount | — | — | review | Spans | "Line {n}: {field} not found." |
| 30 | R-VEN-01 | — | Y | Vendor resolved (02 §5.1) | — | **block** (GSTIN on invoice ≠ master GSTIN for the name-matched vendor) | review | GSTIN/name spans, master_data | "GSTIN {g} on the invoice doesn't match {vendor}'s registered GSTIN." / "Vendor not found in the vendor master." |
| 31 | R-VEN-02 | R-VEN-01† | Y | `vendor.status = approved` | — | **block** | — | master_data | "{vendor} is {status} in the vendor master. Payments are not allowed." |
| 40 | R-PO-01 | R-SCOPE-02†; R-VEN-01† (inference / reviewer path only) | Y | One of: (a) an explicit PO is found **and** belongs to the same vendor; (b) no PO is printed and a unique PO is inferred (02 §5.2); (c) no PO is printed and **every non-bundle line is reviewer-assigned to lines of one PO of this vendor** (`details.via="reviewer_line_choice"`). Reviewer assignments spanning more than one PO → R-SCOPE-02 review. | Inference margin ≥ `po_reference.inference_min_margin` | **block** (PO belongs to another vendor; vendor has no open PO) | review (PO not found; ambiguous) | PO span, master_data, reviewer_attestation | "PO {po} belongs to {other_vendor}, not {vendor}." / "PO {po} not found." / "No PO printed; {n} open POs fit: {list}." |
| 41 | R-PO-02 | R-PO-01† | Y | `po.status = open` | — | **block** | — | master_data | "PO {po} is {status}." |
| 42 | R-PO-03 | R-PO-01† | N | PO was printed on the invoice | — | none (info). **review** if `po_reference.require_on_invoice` | — | — | "PO {po} inferred from line items (not printed on the invoice)." / "PO {po} chosen by reviewer ({user}: {reason})." |
| 43 | R-DATE-01 | R-EXT-02†, R-PO-01† | Y | `invoice_date ≥ po.order_date` | days | review | — | Spans, master_data | "Invoice dated {d} is before PO date {po_d}." |
| 50 | R-DUP-01 | R-VEN-01†, R-EXT-01† | Y | No invoice J with the same `(vendor_id, invoice_number_key)`, where J ≠ this invoice, and J is `approved` **or** (`review_state = open` **and** `(J.uploaded_at, J.id) < (this.uploaded_at, this.id)`). A *later* copy never blocks the original. | — | **block** | — | Span + other invoice ref | "Duplicate of {ref} ({number}, uploaded {when}, {status})." |
| 51 | R-DUP-02 | R-VEN-01†, R-EXT-02†, R-EXT-03† | N | No invoice J (same definition as R-DUP-01) with the same vendor, `invoice_date` and `gross_total` and a different number | — | review | — | Other ref | "Looks like {ref}: same vendor, date and total, but a different number. Confirm it isn't a re-issue." |
| 52 | R-DUP-03 | — | Y | No invoice J (same definition as R-DUP-01) with the same `document_sha256` | — | **block** | — | sha256 | "This exact file was already uploaded as {ref}." |
| 60 | R-LINE-01 | R-PO-01† | Y | Every line `assigned` (matcher or reviewer). If R-PO-01 is ambiguous, R-LINE-01 is `not_evaluated`, but `line_matches` still keeps the cross-PO candidates for the reviewer's chooser. | calibrated thresholds | **block** (`conflict`) | review (`ambiguous`, `no_match`) | Description span, candidates | "Billed '{desc}' conflicts with PO line {k} on {attr} ({inv} ≠ {po})." / "Couldn't tell which PO line this is." |
| 61 | R-LINE-02 | R-LINE-01† | Y | `unit == po_line.uom`, or a pack factor with evidence converts unit → uom | Factor 4 dp | — | review | Pack span or attestation | "Billed in {unit}; the PO is per {uom_label}. The invoice doesn't say how many {uom_label}s are in a {unit}." |
| 62 | R-LINE-03 | — | Y | Line is not a bundle and maps to ≤ 1 PO line | — | — | review | Span | "Line {n} bundles several items ('{desc}'). Ask for an itemised invoice or split manually." |
| 63 | R-TAX-03 | — | Y | If prices are tax-inclusive: an inclusive statement **and** a rate are evidenced (net derived per §4.3). If not inclusive: `not_applicable`. **Order 63** (evaluated before its dependents R-PRC-01/R-AMT-01). | — | — | review | Spans | "Prices say 'inclusive of GST' but no rate is shown, so the net price can't be derived." |
| 70 | R-PRC-01 | R-LINE-01†, R-LINE-02†, R-TAX-03† | Y | `|p − e| ≤ max(tol.unit_price.absolute, |e| × tol.unit_price.relative)`, where p = `unit_price_base_net` and e = `po_line.unit_price` | INR per uom, 4 dp | **block** | — | Rate span | "{desc}: billed ₹{p}/{uom}, PO price ₹{e} ({±d}; tolerance ₹{t})." |
| 71 | R-PRC-02 | R-PRC-01 (non-gate; needs R-PRC-01 `pass` or `fail` on every assigned line) | N | NOT (≥ 2 lines fail R-PRC-01 with opposite-sign amount deltas **and** `|Σ deltas| ≤ max(tol.po_amount.absolute, Σ expected × tol.po_amount.relative)`). Amount delta per line = `qty_base × (unit_price_base_net − po_line.unit_price)`, rounded to 2 dp. Σ expected = Σ `qty_base × po_line.unit_price` over the failing lines. | INR | none (info) | — | — | "Line variances offset: {list}. Net difference ₹{s}, so a total-only check would pass this invoice." |
| 72 | R-QTY-01 | R-LINE-01†, R-LINE-02† | Y | Per PO line: `Σ qty_base(this invoice) ≤ remaining_qty + tol.quantity.absolute` | uom, 4 dp, inclusive | **block** | — | master_data (ledger) | "Billed {q} {uom_label}s; only {r} remain on {po} line {k} (exceeds by {q−r})." |
| 73 | R-AMT-01 | R-LINE-01†, R-LINE-02†, R-TAX-03† | Y | Per PO line, **cumulative**: `allocated_amount + Σ amount_net(this invoice) ≤ V + max(tol.po_amount.absolute, V × tol.po_amount.relative)`, with `V = ordered_qty × unit_price` (the line's authorised value). The tolerance is fixed per line, so it never shrinks as the PO is consumed. | INR 2 dp | **block** | — | Ledger | "Billed ₹{a} net; ₹{r} remains (tolerance ₹{t})." (r = V − allocated_amount) |
| 80 | R-ART-01 | R-EXT-04† (per line) | Y | `|round2(qty × unit_price) − amount| ≤ tol.line_amount.absolute` (printed basis) | INR | **block** | — | Spans | "Line {n}: {qty} × ₹{rate} = ₹{calc}, but the invoice says ₹{amt}." |
| 81 | R-ART-02 | R-ART-01 (non-gate) | Y | `|Σ amount_net + charges − header_discount − printed_taxable| ≤ tol` with printed_taxable = `taxable_value`, else `subtotal`. If neither is printed: `not_applicable`. `tol = tol.taxable_value.absolute`, or `max(that, 0.005 × n_lines)` when any line is tax-inclusive (per-line rounding drift). | INR | **block** | — | Spans | "Line amounts add up to ₹{calc}; the invoice's taxable value says ₹{p}." |
| 82 | R-TAX-01 | R-ART-02 (non-gate) | Y | Each printed tax component: `|round2(taxable × rate) − amount| ≤ tol.tax_component.absolute`, with **taxable** as defined in §4.2 | INR | **block** | review (rate missing) | Spans | "{kind} @ {rate}: expected ₹{calc}, invoice says ₹{amt}." |
| 83 | R-TAX-02 | R-LINE-01†, R-TAX-01 (non-gate) | Y | Line GST rate equals `po_line.tax_rate` (when the PO has one). Line rate = `invoice_lines.tax_rate` if printed per line; else, when header components apply to the whole taxable value, Σ header component rates (CGST 0.09 + SGST 0.09 = 0.18; IGST 0.18); else unknown. | fraction | review | review | Spans, master_data | "Invoice charges GST {r1}; the PO expects {r2}. Check the tax classification." |
| 85 | R-ART-03 | R-EXT-03† | Y | `|taxable + Σ tax + round_off − grand_total| ≤ tol.invoice_total.absolute` and `|round_off| ≤ tol.round_off_max` (taxable per §4.2) | INR | **block** | — | Spans | "Taxable ₹{t} + tax ₹{x} + round-off ₹{r} = ₹{calc}, but the total says ₹{g}." |
| 90 | R-CHG-01 | — | Y | No freight / packing / other charge lines | — | review | — | Span | "Freight ₹{f} isn't on the PO. Confirm it was agreed." |
| 91 | R-CHG-02 | — | Y | No header-level discount | — | review | — | Span | "Invoice-level discount ₹{d} can't be allocated to PO lines in this release." |

"—" in the Fail→ or Unk→ column means the outcome cannot occur. If it does, the engine raises `INTERNAL_ERROR`; it never silently treats it as `none`.

**Identity never depends on price or remaining quantity.** R-LINE-01 is computed by the matcher from description, SKU and attributes only (02 §5.3). Price and balance appear only in R-PRC-*, R-QTY-01 and R-AMT-01.

### 4.2 Amount bases

| Quantity | Basis | Source |
|---|---|---|
| `po_line.unit_price` | Net, per `uom` | PO |
| `unit_price_base_net` | Net, per PO `uom` | Invoice (normalised) |
| `amount_net` | Net | Invoice (normalised) |
| `remaining_amount` | Net = `ordered_qty × unit_price − allocated_amount` | Ledger |
| `allocations.amount_net` | Net billed (not the PO price) | Approval |
| `taxable_value`, `subtotal` | Net, as printed | Invoice |
| **taxable** (used by R-TAX-01, R-ART-03) | Net. Printed `taxable_value`, else printed `subtotal`, else `round2(Σ amount_net)` (marked `derived` in `details`) | Invoice |
| `grand_total` | Gross | Invoice |

**Supported paths:**
- Tax separated: CGST + SGST, or IGST.
- Tax inclusive, with a stated rate.
- Round-off line up to ±₹0.50.
- **Not supported (review):** freight or other charges (R-CHG-01), header discounts (R-CHG-02), line-discount columns (detected → R-CHG-02 message variant), cess, TDS/TCS lines, credit notes.

### 4.3 Rounding checkpoints

| # | Where | Rule |
|---|---|---|
| C1 | Parse | Exact Decimal from the text token. No rounding. Indian grouping `1,00,000.00` is accepted. European `3.000,00` is `invalid`. |
| C2 | Price per base unit (computed **after** line assignment, 02 §5.6; stored on `line_matches`) | `unit_price_base_net = round4(unit_price_net / pack_factor)` (pack factor 1 when units are equal). `unit_price_net` (stored on `invoice_lines`) = `unit_price`, or when inclusive `round4(unit_price / (1 + rate))`. |
| C3 | Line net amount | `amount_net = amount` or, when inclusive, `round2(amount / (1 + rate))`. |
| C4 | Line arithmetic | `round2(qty × unit_price)` on the printed basis. |
| C5 | Tax component | `round2(taxable × rate)` |
| C6 | Tolerances | Compare the **stored** C2 (4 dp) and C3 (2 dp) values against tolerance. Do not round the delta or the tolerance. `<=` is inclusive. The displayed `actual` is therefore exactly the value compared. |
| C7 | Quantities | `qty_base = qty × pack_factor`, exact to 4 dp (no rounding; a result needing more than 4 dp is `invalid`). |
| C8 | Allocation | Store `amount_net` (2 dp) and `qty_base` (4 dp), aggregated per PO line across invoice rows. |

**Boundary tests** (policy `unit_price` abs 0.05 / rel 0.01; expected 5.0000 ⇒ tolerance 0.0500):

| Actual | Diff | Result |
|---|---|---|
| 5.0500 | 0.0500 | **pass** |
| 5.0501 | 0.0501 | **fail** |
| 4.9500 | 0.0500 | **pass** |
| 4.9499 | 0.0501 | **fail** |

Expected 12.5000 ⇒ tolerance 0.1250:

| Actual | Result |
|---|---|
| 12.6250 | **pass** |
| 12.6251 | **fail** |

### 4.4 Ordering when findings coexist

Rules are evaluated in a **topological order of *Depends on***, with ties broken by Order. A unit test asserts that every dependency's Order is less than its dependent's Order. Arithmetic rules (R-ART-*, R-TAX-01) need no PO and **always run when their inputs exist**. An invoice can therefore be held for arithmetic errors even when its vendor is unknown.

Every finding is retained, `pass` included.

Display `sort_key` = effect rank (block 0, review 1, none 2) × 100000 + Order × 100 + subject rank (≤ 99). Subject rank: invoice 0, then `line:n` and `po_line` sorted by n.

### 4.5 Disposition truth table (deterministic precedence)

| Technical failure? | Any finding effect = block? | Any finding effect = review? | Run state | Recommendation |
|---|---|---|---|---|
| yes | — | — | `processing_failed` | *(none; no decision written)* |
| no | yes | any | `completed` | `hold` |
| no | no | yes | `completed` | `needs_review` |
| no | no | no (all mandatory rules `pass` or `not_applicable`) | `completed` | `ready_for_approval` |

**Fail-safe row.** No technical failure and no block/review effect, but any **required** rule is `not_evaluated` with no root cause carrying an effect ⇒ `needs_review` with an `R-ENGINE` note: "An internal check could not run." This should never happen, and a unit test asserts it on a synthetic case.

Precedence: `processing_failed` > `hold` > `needs_review` > `ready_for_approval`. A hold still lists its review questions, so the reviewer sees everything at once.

**Summary sentence:**
- Hold: a composed sentence naming the blocking problems, e.g. "Two line prices differ from PO-2026-0152 …". Default: the top block finding's message.
- Needs review: "{n} questions need an answer: …"
- Ready: "Matches {po} …"

**Next action:**
- Hold → "Do not approve. {vendor-facing ask}." Reject is available.
- Needs review → "Answer the questions, then re-check."
- Ready → "Approve. Approval re-checks the current PO balance."

### 4.6 Approval-time re-check (inside the approval transaction)

1. Load the current decision's readings, corrections and line matches, including conversions. **No OCR and no matcher re-run.**
2. If `vendor.revision` or `po.revision` changed since the snapshot: the identity inputs may have changed. Write **no** new decision. Return 409 `APPROVAL_STALE` with `details.reason="master_data_changed"` and enqueue a `revalidate` run (`trigger='master_data_changed'`, actor `system`).
3. Otherwise re-evaluate R-VEN-02, R-PO-02, R-DUP-01, R-DUP-03 (with the R-DUP-01 definition of J, so a later copy never blocks), R-QTY-01 and R-AMT-01 against **current, locked** rows.
4. All pass ⇒ approve. Otherwise write decision v+1 (`origin='approval_check'`, `run_id NULL`):
   - copy **every** finding of v, replacing those for the re-evaluated (rule, subject) pairs with the new results;
   - copy **all** `line_matches` rows of v;
   - recompute recommendation, summary and next_action per §4.5;
   - `ledger_snapshot` = the locked rows; compute a new `inputs_fingerprint`.

   Then return 409 `APPROVAL_STALE`. The UI shows the version in a **Decision history** list. Approval-check versions have no run, so they appear there rather than on the Runs tab.

### 4.7 Policy file `policies/demo-ap-policy-2026.11.1.yaml` (demo policy, not tax advice)

```yaml
policy_id: reconcile-demo-ap
version: "2026.11.1"
buyer: {legal_name: "Vaanya Healthcare Pvt. Ltd.", gstin: "27AAHCV5521Q1Z6", state_code: "27"}
locale: en-IN                       # DD/MM/YYYY for numeric dates
currency: {supported: [INR], default_when_absent: INR}
price_basis: net
rounding: {mode: ROUND_HALF_UP, amount_dp: 2, unit_price_dp: 4, quantity_dp: 4}
tolerances:
  unit_price:    {absolute: "0.05", relative: "0.01"}   # INR per PO uom, net
  po_amount:     {absolute: "1.00", relative: "0.01"}   # vs remaining amount per PO line
  line_amount:   {absolute: "0.01"}
  taxable_value: {absolute: "0.01", inclusive_per_line: "0.005"}   # R-ART-02: max(absolute, per_line × n_lines) when any line is tax-inclusive
  tax_component: {absolute: "0.10"}
  invoice_total: {absolute: "0.50"}
  round_off_max: "0.50"
  quantity:      {absolute: "0"}                        # MUST be 0 in this release (DB CHECK ck_po_line_not_overallocated)
dates: {max_future_days: 1}
po_reference: {require_on_invoice: false, inference_min_margin: "0.10"}
matching:
  matcher: b0                       # b0 | b1 | e1 — selected per 04 §3.6
  accept_threshold: "0.55"          # PLACEHOLDER — replaced by calibration (T-20); fixture outcomes must not change
  min_margin: "0.08"                # PLACEHOLDER
  conflict_attributes: [material, size, powder, sterility, volume, thread, length, grade, gsm, sheet_size]
extraction: {min_field_confidence: "0.60"}   # below → field status 'ambiguous' (business-relevant). OCR DPI etc. are parser config (§7), not policy.
duplicates: {soft_key: [vendor_id, invoice_date, gross_total]}
limits: {max_lines: 50}
approval: {require_different_approver: false}   # SoD deferred (D-22)
```

The policy loader validates the file against a Pydantic schema, rejects unknown keys and computes `sha256`. A new `version` **requires a new file**: never edit a released version in place.

---

## 5. Seed data and worked values (must match `04` fixtures exactly)

### 5.1 Seed (synthetic; `reconcile.cli seed --demo`)

**Buyer:** Vaanya Healthcare Pvt. Ltd., Pune, Maharashtra (state 27), GSTIN `27AAHCV5521Q1Z6`.

**Users.** Passwords come from secrets (02 §9.2):

| Email | Role |
|---|---|
| `clerk@reconcile.demo` | clerk |
| `approver@reconcile.demo` | approver |
| `admin@reconcile.demo` | admin |

**Vendors:**

| Code | Legal name | GSTIN | State | Status | Aliases |
|---|---|---|---|---|---|
| VEN-0001 | SafeHands Supplies Pvt. Ltd. | 27AAJCS4821K1Z3 | 27 | approved | "SafeHands Supplies", "Safe Hands Supplies Pvt Ltd" |
| VEN-0002 | Kaveri Industrial Traders | 29AAGFK6612H1Z9 | 29 | approved | "Kaveri Industrial" |
| VEN-0003 | Brightline Office Solutions LLP | 27AAQFB7390M1Z2 | 27 | approved | "Brightline Office Solutions" |
| VEN-0004 | Meridian Lab Supplies Pvt. Ltd. | 27AAKCM3307P1Z4 | 27 | approved | "Meridian Lab Supplies" |
| VEN-0005 | Apex Facility Services | 27AAXFA9054R1Z1 | 27 | **blocked** | "Apex Facility" |

All GSTINs and companies are fictional and only format-valid.

**Purchase orders.** All INR, net prices, revision 1. "Allocated (seed)" comes from seeded, approved invoices.

| PO | Vendor | Date | Status | Line | Item code | Description | uom (label) | Ordered | Unit price | Tax | Allocated (seed) | Remaining qty / ₹ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PO-2026-0147 | VEN-0001 | 2026-10-20 | open | 1 | GLV-NIT-M-PF | Nitrile examination gloves, medium, powder-free, blue | EA (glove) | 1000 | 5.0000 | 0.18 | 400 / 2000.00 | 600 / 3000.00 |
| | | | | 2 | GLV-NIT-L-PF | Nitrile examination gloves, large, powder-free, blue | EA (glove) | 500 | 5.0000 | 0.18 | 0 | 500 / 2500.00 |
| | | | | 3 | SAN-GEL-500 | Hand sanitizer gel, 500 ml bottle | EA (bottle) | 40 | 120.0000 | 0.18 | 0 | 40 / 4800.00 |
| PO-2026-0149 | VEN-0001 | 2026-10-22 | open | 1 | GLV-NIT-S-PF | Nitrile examination gloves, small, powder-free, blue | EA (glove) | 1000 | 5.0000 | 0.18 | 500 / 2500.00 | 500 / 2500.00 |
| PO-2026-0152 | VEN-0002 | 2026-10-25 | open | 1 | FST-HB-M10X50 | Hex bolt M10 x 50 mm, zinc plated, grade 8.8 | EA (piece) | 200 | 12.5000 | 0.18 | 0 | 200 / 2500.00 |
| | | | | 2 | FST-HN-M10 | Hex nut M10, zinc plated, grade 8 | EA (piece) | 200 | 4.0000 | 0.18 | 0 | 200 / 800.00 |
| | | | | 3 | FST-FW-M10 | Flat washer M10, zinc plated | EA (piece) | 200 | 1.2500 | 0.18 | 0 | 200 / 250.00 |
| PO-2026-0155 | VEN-0004 | 2026-10-26 | open | 1 | LAB-TIP-200-ST | Pipette tips 200 µL, sterile, racked, 96 per rack | RACK (rack) | 50 | 210.0000 | 0.18 | 0 | 50 / 10500.00 |
| PO-2026-0158 | VEN-0004 | 2026-10-30 | open | 1 | LAB-TIP-1000-ST | Pipette tips 1000 µL, sterile, racked, 96 per rack | RACK (rack) | 50 | 210.0000 | 0.18 | 0 | 50 / 10500.00 |
| PO-2026-0160 | VEN-0003 | 2026-10-28 | open | 1 | OFF-PAP-A4-75 | Copier paper A4, 75 GSM, 500 sheets per ream | REAM (ream) | 50 | 245.0000 | 0.18 | 0 | 50 / 12250.00 |
| | | | | 2 | OFF-STP-10 | Stapler pins No. 10, box of 1000 | BOX (box) | 20 | 18.0000 | 0.18 | 5 / 90.00 | 15 / 270.00 |
| PO-2026-0133 | VEN-0005 | 2026-09-15 | **closed** | 1 | SVC-HK-MONTH | Housekeeping services, monthly | EA (month) | 3 | 45000.0000 | 0.18 | 3 / 135000.00 | 0 / 0.00 |

**Seeded approved invoices** (`source='seed'`). Each has a decision v1 with `ready_for_approval`, an approval and allocations:

| Number | Vendor | Date | PO / line | Qty | Net | Gross |
|---|---|---|---|---|---|---|
| SH/2526/0871 | VEN-0001 | 2026-10-24 | 0147 / 1 | 4 Box = 400 EA | 2000.00 | 2360.00 |
| SH/2526/0880 | VEN-0001 | 2026-10-27 | 0149 / 1 | 5 Box = 500 EA | 2500.00 | 2950.00 |
| INV-0042 | VEN-0003 | 2026-10-30 | 0160 / 2 | 5 BOX | 90.00 | 106.20 |
| AFS/2026/290 | VEN-0005 | 2026-10-01 | 0133 / 1 | 3 EA | 135000.00 | 159300.00 |

Each seeded invoice has run #1 (`kind=full`, `trigger=seed`, `state=completed`, no job) that owns its `ev-seed` `master_data` evidence. Seed rows have **no document PDF**. A tiny placeholder PDF, stamped "SEED RECORD — NO SOURCE DOCUMENT", is stored so the FK holds. The UI labels these rows **Seeded history**.

### 5.2 Worked example: SafeHands gloves (teaching example and HP-01)

PO-2026-0147 line 1 authorises 1,000 medium powder-free nitrile gloves at ₹5.00 net per glove. 400 are already approved, so 600 gloves (₹3,000.00 net) remain.

| Case | Printed line | Normalised | Checks | Recommendation |
|---|---|---|---|---|
| **HP-01** | 6 Box "Box of 100 gloves" @ ₹500.00 = ₹3,000.00 | 600 EA @ 5.0000 | price diff 0.0000 ≤ 0.0500 ✓; qty 600 ≤ 600 ✓ (inclusive); amount (cumulative) 2000.00 + 3000.00 = 5000.00 ≤ 5000.00 + max(1.00, 50.00) = 5050.00 ✓; tax 3000.00 × 0.09 = 270.00 ×2 ✓; total 3000.00 + 540.00 = 3540.00 ✓ | `ready_for_approval` → approve → allocated 400 → 1000, remaining 0 |
| EC-01d | 7 Box (Box of 100) @ ₹500.00 = ₹3,500.00 | 700 EA @ 5.0000 | R-QTY-01: 700 > 600, **exceeds by 100** ✗; R-AMT-01: 2000.00 + 3500.00 = 5500.00 > 5050.00 ✗ | `hold` |
| EC-01b | 3 Box, **no pack size**, large gloves @ ₹500.00 = ₹1,500.00 (PO line 2) | qty_base unknown | R-LINE-02 unknown ⇒ R-PRC-01/R-QTY-01/R-AMT-01 `not_evaluated` | `needs_review` → correction `lines[1].pack_factor=100` → 300 EA @ 5.0000 ✓, 300 ≤ 500 ✓ → `ready_for_approval` |
| EC-01c | 6 Box **Latex** gloves medium (Box of 100) @ ₹500.00 | — | R-LINE-01 conflict: material latex ≠ nitrile (lines 1, 2) | `hold` |

### 5.3 Worked values for every fixture

Expected values are written **independently** of the implementation. 04 §4 holds the rendering specs. Tolerances follow the formulas in §4.1.

| Fixture | Lines (printed) | Subtotal / taxable | Tax | Grand total | Key computations | Expected recommendation |
|---|---|---|---|---|---|---|
| HP-01 SH/2526/0912 | 6 Box @ 500.00 = 3,000.00 | 3,000.00 | CGST 9 % 270.00 + SGST 9 % 270.00 | 3,540.00 | §5.2 | ready_for_approval |
| EC-01b SH/2526/0913 | 3 Box @ 500.00 = 1,500.00 (large; no pack) | 1,500.00 | 135.00 + 135.00 | 1,770.00 | Pack factor unknown | needs_review (→ ready after correction) |
| EC-01b-ctl SH/2526/0917 | Same line **with** "Box of 100 gloves" | 1,500.00 | 135.00 + 135.00 | 1,770.00 | 300 EA ≤ 500 | ready_for_approval |
| EC-01c SH/2526/0914 | 6 Box Latex (Box of 100) @ 500.00 = 3,000.00 | 3,000.00 | 270.00 + 270.00 | 3,540.00 | Material conflict | hold |
| EC-01d SH/2526/0915 | 7 Box @ 500.00 = 3,500.00 | 3,500.00 | 315.00 + 315.00 | 4,130.00 | 700 > 600 by 100; cumulative ₹5,500 > ₹5,050 | hold (in seed state) |
| EC-02 KIT-2026-1187 | 200 @ 13.50 = 2,700.00; 200 @ 3.00 = 600.00; 200 @ 1.25 = 250.00 | 3,550.00 | IGST 18 % 639.00 | 4,189.00 | L1: \|13.50−12.50\| = 1.00 > max(0.05, 0.125) ✗. L2: \|3.00−4.00\| = 1.00 > max(0.05, 0.04) = 0.05 ✗. L3 pass. R-AMT-01 L1: 2700.00 > 2500.00 + max(1.00, 25.00) ✗. L2/L3 pass. R-PRC-02: deltas +200.00/−200.00, sum 0.00 ⇒ info. Header net 3,550.00 equals the PO net total. | hold |
| EC-02-ctl KIT-2026-1188 | 200 @ 12.50 = 2,500.00; 200 @ 4.00 = 800.00; 200 @ 1.25 = 250.00 | 3,550.00 | 639.00 | 4,189.00 | All pass | ready_for_approval |
| EC-03-A SH/2526/0931 | 3 Box (Box of 100) small @ 500.00 = 1,500.00 (PO-0149) | 1,500.00 | 135.00 + 135.00 | 1,770.00 | 300 ≤ 500 | ready → **approved** (allocated 500 → 800) |
| EC-03-B SH/2526/0932 | Same as A, dated 09/11/2026 | 1,500.00 | 135.00 + 135.00 | 1,770.00 | At upload 300 ≤ 500 ⇒ ready. At approval after A (allocated 800 / ₹4,000.00): 300 > 200 by 100 ✗; cumulative ₹4,000 + ₹1,500 = ₹5,500 > ₹5,000 + ₹50 ✗ | ready (v1) → approve ⇒ **409 APPROVAL_STALE**, v2 hold |
| EC-04 (no number) | 10 Rack "Pipette Tips, Sterile, Racked (96 tips/rack)" @ 210.00 = 2,100.00 | 2,100.00 | CGST @ 9 % 189.00 + SGST @ 9 % 189.00 | 2,478.00 | No number, no PO, ambiguous 0155/0158. Corrections: number `MLS-7781`; line 1 → PO-2026-0158/1 ⇒ 10 ≤ 50, 210.00 = 210.00 | needs_review (→ ready after corrections) |
| EC-04-ctl MLS-7790 | 10 Rack "Pipette Tips 1000 µL, Sterile, Racked (96 tips/rack)" @ 210.00 | 2,100.00 | CGST @ 9 % 189.00 + SGST @ 9 % 189.00 | 2,478.00 | PO-0155 vetoed (volume 200 ≠ 1000) ⇒ PO-0158 inferred (R-PO-03 info) | ready_for_approval |
| SC-01 BOS/1146 (scanned) | 20 Ream @ 245.00 = 4,900.00; 10 Box @ 18.00 = 180.00 | 5,080.00 | 457.20 + 457.20 | 5,994.40 | Units equal (no conversion); 20 ≤ 50, 10 ≤ 15 | ready_for_approval |
| REG-02 Kaveri INV-0042 | 50 @ 4.00 = 200.00 (nuts) | 200.00 | IGST 36.00 | 236.00 | Same number as Brightline INV-0042: **not** a duplicate | ready_for_approval |
| REG-03a SH/2526/0951 | 3 Box (100) @ 505.00 = 1,515.00 (large) | 1,515.00 | 136.35 + 136.35 | 1,787.70 | 5.0500: diff 0.0500 ≤ 0.0500 ✓ | ready_for_approval |
| REG-03b SH/2526/0952 | 3 Box (100) @ 505.01 = 1,515.03 | 1,515.03 | 136.35 + 136.35 | 1,787.73 | 5.0501: diff 0.0501 > 0.0500 ✗ | hold |
| REG-08 SH/2526/0961 | 6 Box (100) @ 540.00 = 3,240.00 + injected text | 3,240.00 | 291.60 + 291.60 | 3,823.20 | 5.4000 vs 5.0000 ✗ (the injected text has no effect) | hold |
| REG-10 SH/2526/0941 | 3 Box (100) "Rate incl. GST @18%" 590.00 = 1,770.00 | Taxable 1,500.00 | 135.00 + 135.00 (printed breakup) | 1,770.00 | net/box = round4(590.00/1.18) = 500.0000 ⇒ 5.0000/EA; amount_net = round2(1770.00/1.18) = 1500.00 | ready_for_approval |
| REG-13 SH/2526/0971 | Two rows of medium nitrile (Box of 100): 2 Box @ 500 = 1,000.00 and 4 Box @ 500 = 2,000.00 | 3,000.00 | 270.00 + 270.00 | 3,540.00 | Aggregated 600 ≤ 600 | ready_for_approval |
| REG-24 SH/2526/0953 (after REG-03a approved) | 2 Box large (Box of 100) @ 500.00 = 1,000.00; 02/11/2026 | 1,000.00 | 90.00 + 90.00 | 1,180.00 | 0147/2: allocated 300 / ₹1,515.00. R-QTY-01: 300 + 200 = 500 ≤ 500 ✓. R-AMT-01 (cumulative): ₹1,515.00 + ₹1,000.00 = ₹2,515.00 ≤ ₹2,500.00 + ₹25.00 ✓. This is the tolerance-creep case: a remaining-based tolerance would have held it. | ready_for_approval |
| REG-25 SH/2526/0962 | 6 Box medium (Box of 100) @ 500.00 = 3,000.00 with CGST **@ 14 %** 420.00 + SGST **@ 14 %** 420.00; 31/10/2026 | 3,000.00 | 420.00 + 420.00 | 3,840.00 | Arithmetic consistent (R-TAX-01 ✓, R-ART-03 ✓). R-TAX-02: header rate 0.28 ≠ PO 0.18 → review | needs_review |

Every value above was re-computed with Python `Decimal`/`ROUND_HALF_UP` during design (2026-11-10). Codex re-verifies them through the fixture tests (AC-06…AC-11).

---

## 6. Normalisation contract (deterministic; no PO access)

| Input | Rule |
|---|---|
| Numbers | Strip `₹`, `Rs.`, `Rs`, `INR` and `/-`. Accept `1,234.50` and the Indian `1,23,450.00`. Reject `1.234,50` (→ `invalid`). Parentheses or a trailing `-` make the number negative (→ R-SCOPE-03 if the total is negative). |
| Dates | en-IN: `DD/MM/YYYY`, `DD-MM-YYYY`, `DD.MM.YYYY`, `DD Mon YYYY`, `DD-Mon-YY`. The format used is recorded in `details`. Two-digit years map to 20YY. An impossible date is `invalid`. |
| Units | Canonical codes with synonyms: `EA` ← each, ea, no, nos, no., pc, pcs, piece(s), unit(s), glove(s), bottle(s); `BOX` ← box, boxes, bx; `REAM` ← ream(s), rm; `RACK` ← rack(s); `PACK` ← pack, pkt, packet. Unrecognised units → `unit=null` with `unit_raw` kept (R-EXT-04 unknown). |
| Pack factor | Patterns on the **same line's text only**: `(box\|pack\|rack) of N <inner>`, `N <inner> ?(/\|per) ?(box\|pack\|rack)`, `(N/box)`, `N <inner> per <unit>`. Normalisation **only records** each match in `invoice_lines.pack_candidates` as `{factor, outer_unit, inner_unit (canonical or null), inner_text, evidence_id}`. It **never applies** a conversion, because that needs the PO line's uom. The conversion is decided after assignment (02 §5.6). |
| Bundle | `is_bundle = true` when the row has an amount but no qty or no unit price, **or** its text matches `/(as per (PO\|order)\|lot \d+\|supplies? (for\|as per)\|lump ?sum)/i`. R-EXT-04 skips bundle rows; R-LINE-03 reports them. A PO number inside a bundle row still counts as a PO reference. |
| Tax-inclusive | Detected via "incl(usive)? (of)? GST", "GST inclusive" or "Rate (incl. GST @r%)". The rate comes from the same line, else the header statement, else unknown → R-TAX-03 review. |
| Identifiers | `*_key = upper(remove [\s\-/._])`. The printed value is kept. |
| Text | NFKC. `µ` (U+00B5) and `μ` (U+03BC) normalise to `u`. Lowercase is used for matching only. |
| Buyer vs seller GSTIN | The seller GSTIN is a format-valid GSTIN ≠ `policy.buyer.gstin`, preferably in the top 30 % of page 1 or near the vendor name. Several candidates → `ambiguous`. |

Extraction and normalisation **must not import or query** `procurement` (vendors/POs/ledger). This is enforced by an import-boundary test (AC-27).

---

## 7. Configuration (environment variables)

| Name | Default | Owner | Secret | Notes |
|---|---|---|---|---|
| `DATABASE_URL` | — | Candidate (Render dashboard → Postgres → *Internal* URL) | **yes** | Accepts `postgres://`, `postgresql://` or `postgresql+psycopg://`. The config loader rewrites the scheme to `postgresql+psycopg://` before *any* engine is created (app, Alembic `env.py`, spike). It logs the scheme only and is unit-tested. **Paste Render's Internal URL verbatim.** Hosted: internal URL only; external access disabled (02 §8.2). Local: compose service DNS name. |
| `SESSION_SECRET` | — | Candidate (`python -c "import secrets;print(secrets.token_urlsafe(48))"`) | **yes** | Rotating it invalidates all sessions. |
| `DEMO_CLERK_PASSWORD`, `DEMO_APPROVER_PASSWORD`, `DEMO_ADMIN_PASSWORD` | — | Candidate | **yes** | ≥ 16 chars. Only the approver password goes in the submission email. |
| `APP_HOST` | `127.0.0.1` | Codex | no | The container entrypoint sets `0.0.0.0` explicitly. In the hosted container, the platform's HTTPS proxy is the boundary (02 §9.5). Locally, compose publishes `127.0.0.1:8000` only. |
| `PORT` | `8000` | Platform | no | Render injects `PORT` (default 10000); the entrypoint binds to it |
| `WORKER_MODE` | `separate` | Codex | no | `separate` = own process (local compose). `embedded` = worker loop in a background thread of the API process (Render Free, 512 MB; 02 §8.2). Same queue/lease code either way. |
| `OCR_DPI` / `OCR_RETRY_DPI` | `300` / `200` | Codex | no | Render Free: `200` / `150` (0.1 CPU). Recorded in `text_layers.params`. |
| `MIN_NATIVE_CHARS_PER_PAGE` | `40` | Codex | no | Below this, the page goes to OCR |
| `MIGRATE_ON_START` | `false` | Codex | no | `true` on Render (no shell access). Runs `alembic upgrade head` under a Postgres advisory lock before serving. Expand-only migrations (02 §11.1). |
| `BLOB_BACKEND` | `postgres` | Codex | no | `postgres \| local \| s3` |
| `BLOB_LOCAL_DIR` | `./var/blobs` | Codex | no | |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | — | Codex (local MinIO only) | yes | Optional |
| `POLICY_PATH` | `policies/demo-ap-policy-2026.11.1.yaml` | Codex | no | |
| `MATCHER` | `b0` | Codex | no | Overrides policy `matching.matcher` only if set |
| `MATCHER_MODEL_DIR` | — | Codex | no | Required for `b1`/`e1` |
| `MAX_UPLOAD_BYTES` / `MAX_PAGES` | `10485760` / `10` | Codex | no | |
| `WORKER_ID` | `hostname-pid` | — | no | |
| `LEASE_SECONDS` / `HEARTBEAT_SECONDS` / `MAX_ATTEMPTS` | `60` / `15` / `3` | Codex | no | The worker also upserts `worker_heartbeats` every `HEARTBEAT_SECONDS` (readiness needs age < 3×) |
| `WORKER_CONCURRENCY` | `1` | Codex | no | Jobs processed in parallel per worker |
| `OCR_PAGE_TIMEOUT_S` / `NATIVE_TIMEOUT_S` / `UPLOAD_VALIDATE_TIMEOUT_S` / `RUN_DEADLINE_S` | `30` / `15` / `10` / `360` | Codex | no | Render Free: set from T-01 measurements (start `90` / `45` / `30` / `900`). Rule: one sandbox call per OCR page; `EXTRACT_TIMEOUT_S ≥ OCR_PAGE_TIMEOUT_S`. |
| `RECONCILE_FAULT_INJECT` | unset | Codex (tests/local screenshots only) | no | `<stage>:<error_code>` forces a stage failure, used for the processing-failed state (REG-07c). **The process refuses to start if this is set while `DEMO_MODE=true`.** |
| `EXTRACT_MEM_LIMIT_MB` / `EXTRACT_TIMEOUT_S` | `1024` / `120` | Codex | no | Sandbox limits (02 §4.3). **Render Free: measured VmPeak + 30 % (start `350`) / `120`.** |
| `APP_TIMEZONE` | `Asia/Kolkata` | Codex | no | |
| `DEMO_MODE` | `false` | Codex | no | `true` on the hosted demo: shows the synthetic-data banner and allows `demo-reset` |
| `CODE_VERSION` | build arg | Codex | no | Git SHA |
| `LOG_LEVEL` | `INFO` | — | no | |
| `KAGGLE_PROXY_FILE` | `~/.config/reconcile/kaggle_proxy` | **Candidate writes the file in their own terminal** (02 §10.2) | the *file content* is secret | **Local ML tooling only.** The URL lives only in that 0600 file: never in env exports, argv, the hosted app, the repo or logs (02 §10.6). |

There is deliberately **no** auth-bypass variable. Tests authenticate through fixtures.

---

## 8. Demo operations CLI (not HTTP)

| Command | Effect | Guard |
|---|---|---|
| `python -m reconcile.cli migrate-check` | Exit 1 if the DB is not at Alembic head | — |
| `python -m reconcile.cli seed --demo` | Insert §5.1 seed if `demo_marker` is absent | Refuses unless `DEMO_MODE=true` |
| `python -m reconcile.cli demo-reset --confirm-demo` | In one transaction, delete in this order: allocations, approvals, rejections, findings, line_matches, decisions, corrections, extracted_fields, invoice_lines, evidence, text_layers, run_events, jobs, runs, invoices (all `source='upload'`, plus the seeded rows so they can be re-created). Then delete `object_blobs`/`stored_objects` no remaining invoice references, re-seed the ledgers and seeded invoices, and write a `demo.reset` audit entry. | Requires `DEMO_MODE=true`, the `demo_marker` row and the flag. Prints row counts before and after. |
| `python -m reconcile.cli users --sync` | Upsert the three demo users from the env passwords | — |
| `python -m reconcile.cli latency-report --since 2026-11-10` | p50/p95 queue wait, run time and per-stage durations from `run_events` | Read-only |
| `python -m reconcile.cli verify-db` | Row counts, invariant checks (`allocated_qty == Σ allocations`, no orphan blobs, one active run per invoice) | Read-only |

Paths and module names are proposed. Codex confirms them in T-02 and updates this table.

**Hosted equivalents.** Render Free gives no shell, so the same functions are exposed through code paths that run in the container:
- `migrate-check`/migrations run at start (`MIGRATE_ON_START=true`).
- `seed --demo` and `users --sync` run at start when `DEMO_MODE=true` (idempotent).
- `demo-reset` → `POST /api/admin/demo-reset`.
- `verify-db` and `latency-report` → `GET /api/admin/diagnostics`.

Each code path is shared with its CLI command, so there is one implementation of each.

---

## 9. Mapping to an existing repository (filled by T-00)

| Contract item | Existing equivalent (file:line) | Compatible? | Change needed |
|---|---|---|---|
| *(empty: no repository was available to the design run)* | | | |

Rule: keep any existing name that satisfies the guide. Write the mapping here, and do not rename working public interfaces just to match this document.
