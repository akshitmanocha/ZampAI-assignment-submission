# Submission code review — 11 November 2026

Reviewed the authenticated upload/review workflow, source preservation, supplier
and order matching, duplicate evidence, locked approvals, idempotency, cumulative
balances, evaluation labels/provenance and frontend behavior. This is a focused
engineering review, not an independent security audit or new model benchmark.

## Issues fixed

1. **A compact date could bypass an existing chronology check.** A reviewer could
   submit `20261001`; Python accepted it as a date, but a later string comparison
   did not detect that it preceded `2026-11-01`. Review now requires a real
   `YYYY-MM-DD` date, and chronology compares parsed calendar dates. Six regression
   cases cover canonical, compact, ISO-week and invalid-calendar inputs. The
   requirement for date review has not been removed to increase metrics.
2. **Archived results could be assigned the wrong source identity.** Rebuilding a
   report from older JUnit previously calculated current source hashes. Each run
   now freezes original hashes, runtime provenance and a JUnit digest. Archived
   summaries verify that digest and preserve the original metadata. Missing
   provenance requires a new run; duplicate passing test names cannot replace an
   omitted case. Four regression tests cover these behaviors.
3. **The source-verification launcher used a different user from its tests.** It
   now inherits the same UID/GID as test execution, including when current source
   is mounted read-only with restrictive host permissions.

Added the focused edge suite/reporting commands, made the test scripts available
through a read-only Compose mount, clarified the reader's docstring, and updated
the README with two AI-generated illustrations and accessible explanations.
Image text was checked against the actual implementation and saved metrics.

## Verification

| Check | Observed result |
|---|---|
| Full backend suite with actual PostgreSQL | **221 passed**, zero failures/errors/skips |
| Frontend production build | TypeScript and Vite passed |
| Browser acceptance journey | **1 passed**, including source highlight, staff correction, MiniLM choice, approval, ledger, benchmark view, mobile view and logout |
| Focused submission edge suite after review | **11 passed**, zero failures/skips |
| Archived-report regression checks after launcher fix | **4 passed** |
| Credential-pattern scan | No matching API keys or Kaggle proxy tokens in reviewed files or commits being advanced to main |

Backend verification used current source mounted read-only into the existing
model-equipped test image; the focused evaluator checked runtime source hashes.
Fresh normal Docker builds copy the same source. Each application test uses a
disposable PostgreSQL schema, and the browser fixture was stopped afterward.
Ordinary company documents and balances were preserved.

The image-only control still needs review for the `EA/box` → `EAbox` OCR error;
its explicitly simulated correction is not counted as OCR accuracy. The existing
extraction benchmark was not rerun, and no model was fine-tuned in this review.
The reader docstring clarification changes its source hash without changing its
OCR behavior; existing benchmark artifacts retain their original source hashes.

## Evidence

- [Review summary and source hashes](../ml/results/code-review-v1/summary.json)
- [Full backend output](../ml/results/code-review-v1/backend-tests.txt)
- [Browser result](../ml/results/code-review-v1/browser-results.json)
- [Reviewed edge-case expected/observed results](../ml/results/code-review-v1/submission-edges/report.json)
- [Architecture and label explanations](architecture.md)

Earlier reports remain alongside these results as historical evidence. Neither
this review nor controlled acceptance passes establish 100% future accuracy or
90% automation. Public deployment remains pending.
