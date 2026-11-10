> Historical milestone. The local application now integrates upload, retrieval, review and approval; see [current implementation](local-application.md). Scores and limitations below describe the original experiment.

# Matching with human review

The target is correct final outcomes with useful automation. Model scores cannot establish 100% correctness. Assuming a perfectly accurate reviewer, a reviewed case can be correct only when the necessary evidence is available and the reviewer can find the true record or declare no match. Missing evidence must remain unresolved rather than forcing a decision.

## Flow

1. SQL restricts candidates to the correct vendor and eligible current purchase orders. Historical orders are context, not authorization.
2. A frozen `sentence-transformers/all-MiniLM-L6-v2` bi-encoder embeds the invoice description and candidate descriptions. Cosine similarity retrieves a shortlist.
3. Our separately trained cross-encoder scores the description pairs more closely and reranks the shortlist. This is a different MiniLM model from the embedding encoder.
4. Matching-review routing checks missing evidence, explicit contradictions, top score and gap to the runner-up. Scores are not probabilities. A representative, independently evaluated policy is required before allowing automatic matches. Default is **review every model match**.
5. The reviewer sees top-k candidates plus source PDF/evidence, units/specifications and PO status. They may select another candidate or choose **none of these**. The latter keeps the case unresolved and should allow wider search or escalation.
6. A human match confirmation must be persisted with actor, reason, source evidence and decision version, then rerun all business checks. It is not invoice approval. Final approval rechecks current balances inside the transaction.

Do not use 'a human clicked approve' as a correctness label. Evaluate against independent expected outcomes, audit reviewed cases, and retain unresolved cases in the denominator. Report model-only, reviewed and combined results separately.

## Implemented now

- `backend/reconcile/matching_review.py`: typed routing and reviewer-choice validation, default review, bounded top-k display, no forced choice, rejection of invalid scores/ineligible selections, missing evidence/conflicts and stale reviews. It produces a review attestation for later persistence; it does not store the review or authorize an invoice.
- Seventeen focused unit cases passed. Existing SQL approval service continues to enforce its current balance/state checks separately.
- `ml/evaluate_retrieval.py`: real frozen-embedding retrieval and selected-cross-encoder reranking diagnostic on Kaggle. Models and data revision are recorded in results.

## Measured retrieval diagnostic

36 matching descriptions, three already-inspected pilot test families, searched against 80 fictional catalog products. Correct item present at ranks 1, 3 and 5 for 36/36 queries with embeddings; cross-encoder reranking also retained 36/36. This is **not a fresh blind test**, all queries have a valid match, and the descriptions use simple templates. It is not evidence of real-world 100% retrieval, review correctness, or invoice safety. No human review was conducted.

## Still required

Staff-authenticated review screen, wider/none-match search, append-only review storage/audit, live embedding/reranking integration after vendor/PO filtering, full business-rule revalidation, and independent representative evaluation. The helper and experiment are not the completed end-to-end review workflow.

Measure:

- Recall@k: how often the correct candidate is available for review; report separately from no-match cases.
- Wrong automatic matches / all automatic matches, plus automation coverage, at separately calibrated thresholds and margins.
- Reviewed-case correctness against independent labels, combined final correctness, and unresolved rate.
- Reviewer time, none-correct/escalation rate, and end-to-end price/quantity/duplicate/approval invariants.

Never lower thresholds or remove hard cases to manufacture 100%. If evidence is insufficient, the correct output is a specific review request, not a guessed match.
