import pytest
from reconcile.invoice_routing import Finding,REQUIRED_RULES,route_invoice
from reconcile.matching_review import MatchRoute

MATCH=MatchRoute('matched','po-line','test-only verified match',())
REVIEW=MatchRoute('needs_review',None,'ambiguous',())

def findings(**changes):
    return [changes.get(rule,Finding(rule,'pass',True)) for rule in REQUIRED_RULES]

def test_verified_complete_invoice_can_be_accepted_without_moving_money():
    r=route_invoice(findings(),MATCH)
    assert r.bucket=='accept'
    assert not r.executes_payment and not r.consumes_order_balance

@pytest.mark.parametrize('rule',sorted(REQUIRED_RULES))
def test_every_required_check_blocks_acceptance_when_missing(rule):
    r=route_invoice([f for f in findings() if f.rule_id!=rule],MATCH)
    assert r.bucket=='human_review' and rule in r.unresolved_rules

@pytest.mark.parametrize('rule',['unit_price','remaining_quantity','vendor_status','duplicate'])
def test_confirmed_blocking_discrepancies_reject(rule):
    r=route_invoice(findings(**{rule:Finding(rule,'fail',True)}),MATCH)
    assert r.bucket=='reject' and rule in r.reasons

def test_unverified_failure_does_not_automatically_reject():
    assert route_invoice(findings(unit_price=Finding('unit_price','fail',False)),MATCH).bucket=='human_review'

def test_uncertain_match_never_becomes_automatic_rejection():
    assert route_invoice(findings(),REVIEW).bucket=='human_review'

def test_confirmed_blocker_preserves_unresolved_questions():
    r=route_invoice(findings(unit_price=Finding('unit_price','fail',True),unit_conversion=Finding('unit_conversion','unknown',False)),REVIEW)
    assert r.bucket=='reject' and 'unit_conversion' in r.unresolved_rules

def test_repeated_findings_cannot_hide_a_failed_line():
    with pytest.raises(ValueError):route_invoice(findings()+[Finding('unit_price','fail',True)],MATCH)
