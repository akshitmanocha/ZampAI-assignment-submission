"""Three business buckets, based on verified structured evidence.

This is recommendation routing, not payment or the database rejection action.
A low model score alone never establishes a confirmed invoice discrepancy.
"""
from dataclasses import dataclass
from typing import Literal
from reconcile.matching_review import MatchRoute

REQUIRED_RULES=frozenset({'scope','vendor_identity','vendor_status','purchase_order',
    'product_specification','unit_conversion','unit_price','remaining_quantity',
    'arithmetic','duplicate','required_fields'})

@dataclass(frozen=True)
class Finding:
    rule_id: str
    status: Literal['pass','fail','unknown']
    evidence_verified: bool
    blocking: bool = True

    def __post_init__(self):
        if self.status not in ('pass','fail','unknown'):
            raise ValueError('Invalid finding status')

@dataclass(frozen=True)
class InvoiceRoute:
    bucket: Literal['accept','human_review','reject']
    reasons: tuple[str,...]
    unresolved_rules: tuple[str,...]
    executes_payment: bool = False
    # Accept means ready for the separately authorized approval action.
    consumes_order_balance: bool = False


def route_invoice(findings,match: MatchRoute):
    """Inputs aggregate all lines per rule; every mandatory rule must pass.

    Upstream code must independently check source evidence. A model score or a
    populated extracted field is not itself 'verified'. All final state changes
    still need authenticated, audited, current-state transaction checks.
    """
    findings=tuple(findings)
    if len({f.rule_id for f in findings})!=len(findings):
        raise ValueError('Aggregate line results explicitly; repeated rules are ambiguous')
    by_id={f.rule_id:f for f in findings}
    unresolved=tuple(sorted(rule for rule in REQUIRED_RULES if rule not in by_id or by_id[rule].status=='unknown' or not by_id[rule].evidence_verified))
    blocking=tuple(sorted(f.rule_id for f in findings if f.status=='fail' and f.evidence_verified and f.blocking))
    if blocking:
        return InvoiceRoute('reject',blocking,unresolved)
    if unresolved:
        return InvoiceRoute('human_review',('missing_or_unverified_evidence',),unresolved)
    if match.state!='matched' or match.selected_po_line_id is None:
        return InvoiceRoute('human_review',('product_match_not_confirmed',),())
    if any(by_id[rule].status!='pass' for rule in REQUIRED_RULES):
        return InvoiceRoute('human_review',('required_check_not_passed',),())
    return InvoiceRoute('accept',('all_required_checks_passed',),())
