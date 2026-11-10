"""Conservative match/review routing; never an invoice approval decision.

Retrieval produces candidates; a cross-encoder reranks them. Scores are not
probabilities. Automation is disabled until thresholds have representative
validation evidence. Human selections must still pass evidence/business checks.
"""
from dataclasses import dataclass
import math
from typing import Literal


@dataclass(frozen=True)
class Candidate:
    po_line_id: str
    description: str
    score: float
    eligible: bool = True
    conflicts: tuple[str, ...] = ()

    def __post_init__(self):
        if not math.isfinite(self.score):
            raise ValueError('Candidate scores must be finite')


@dataclass(frozen=True)
class MatchPolicy:
    auto_enabled: bool = False
    threshold: float | None = None
    min_margin: float | None = None
    validation_revision: str | None = None

    def __post_init__(self):
        if self.auto_enabled and (
            self.threshold is None or self.min_margin is None
            or not math.isfinite(self.threshold) or not math.isfinite(self.min_margin)
            or self.min_margin < 0 or not self.validation_revision
        ):
            raise ValueError('Automation needs finite calibrated thresholds and validation provenance')


@dataclass(frozen=True)
class MatchRoute:
    state: Literal['matched', 'needs_review']
    selected_po_line_id: str | None
    reason: str
    candidates: tuple[Candidate, ...]
    can_choose_none: bool = True
    authorizes_invoice: bool = False


def route_match(candidates, evidence_complete, policy=MatchPolicy(), top_k=5):
    if not 1 <= top_k <= 20:
        raise ValueError('top_k must be between 1 and 20')
    candidates = tuple(candidates)
    if len({c.po_line_id for c in candidates}) != len(candidates):
        raise ValueError('Repeated candidate IDs would distort ambiguity checks')
    # Ineligible candidates must be removed by vendor/current-PO filtering.
    ranked = sorted((c for c in candidates if c.eligible), key=lambda c: (-c.score, c.po_line_id))
    shown = tuple(ranked[:top_k])
    def review(reason):
        return MatchRoute('needs_review', None, reason, shown)
    if not ranked:
        return review('no_eligible_candidates')
    if not evidence_complete:
        return review('missing_required_evidence')
    if not policy.auto_enabled:
        return review('automatic_matching_not_validated')
    first = ranked[0]
    if first.conflicts:
        return review('explicit_product_conflict')
    if first.score < policy.threshold:
        return review('score_below_calibrated_threshold')
    # Compare against the full reranked shortlist before truncating the display.
    if len(ranked) > 1 and first.score - ranked[1].score < policy.min_margin:
        return review('ambiguous_candidates')
    return MatchRoute('matched', first.po_line_id, 'validated_match_policy', shown)


def record_review_choice(route, candidate_id, actor, reason, evidence_complete,
                         expected_version, current_version):
    """Produce an attestation for later persistence/revalidation, not approval.

    None means 'none of these'; never force the reviewer to accept top-k.
    Caller must authorize actor, persist this append-only with source evidence,
    and rerun current rules before any business recommendation/approval.
    """
    if route.state != 'needs_review':
        raise ValueError('This route is not awaiting review')
    if not actor.strip() or not reason.strip():
        raise ValueError('Reviewer and reason are required')
    if expected_version != current_version:
        raise ValueError('Review is stale; reload current evidence and candidates')
    if candidate_id is None:
        return {'state': 'needs_review', 'selected_po_line_id': None,
                'reason': 'none_of_candidates', 'actor': actor,
                'review_reason': reason, 'authorizes_invoice': False}
    candidate = next((c for c in route.candidates if c.po_line_id == candidate_id), None)
    if candidate is None or not candidate.eligible:
        raise ValueError('Selection is outside the eligible displayed candidates')
    if not evidence_complete or candidate.conflicts:
        raise ValueError('Resolve missing evidence or explicit conflicts before confirming a match')
    return {'state': 'human_confirmed_match', 'selected_po_line_id': candidate_id,
            'actor': actor, 'review_reason': reason,
            'decision_version': current_version, 'requires_rule_revalidation': True,
            'authorizes_invoice': False}
