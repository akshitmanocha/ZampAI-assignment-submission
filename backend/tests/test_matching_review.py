import pytest
from reconcile.matching_review import Candidate, MatchPolicy, route_match, record_review_choice

POLICY=MatchPolicy(auto_enabled=True,threshold=4,min_margin=1,validation_revision='test-only-policy')

def candidate(id,score=10,**kwargs):return Candidate(id,'description',score,**kwargs)

def test_default_requires_review_even_with_high_score():
    r=route_match([candidate('a',100)],True)
    assert r.state=='needs_review'
    assert r.selected_po_line_id is None
    assert not r.authorizes_invoice

def test_top_k_shown_without_forcing_choice():
    r=route_match([candidate(str(i),i) for i in range(10)],True,top_k=3)
    assert [c.po_line_id for c in r.candidates]==['9','8','7']
    assert r.can_choose_none

def test_missing_evidence_cannot_be_bypassed_by_score():
    assert route_match([candidate('a',100)],False,POLICY).reason=='missing_required_evidence'

def test_conflict_cannot_be_bypassed_by_score():
    assert route_match([candidate('a',100,conflicts=('material',))],True,POLICY).state=='needs_review'

def test_ambiguity_uses_hidden_runner_up():
    r=route_match([candidate('a',10),candidate('b',9.5)],True,POLICY,top_k=1)
    assert r.reason=='ambiguous_candidates'

def test_eligible_confident_match_is_still_not_approval():
    r=route_match([candidate('a',10),candidate('b',5)],True,POLICY)
    assert r.state=='matched' and r.selected_po_line_id=='a'
    assert not r.authorizes_invoice

def test_ineligible_candidates_never_displayed():
    r=route_match([candidate('a',100,eligible=False)],True)
    assert r.reason=='no_eligible_candidates' and not r.candidates

def choose(route,id,**overrides):
    args=dict(actor='reviewer',reason='Checked the original invoice and PO',evidence_complete=True,expected_version=1,current_version=1)
    args.update(overrides)
    return record_review_choice(route,id,**args)

def test_human_can_choose_second_candidate_but_rules_must_run_again():
    r=route_match([candidate('a',10),candidate('b',9)],True)
    result=choose(r,'b')
    assert result['selected_po_line_id']=='b'
    assert result['requires_rule_revalidation']
    assert not result['authorizes_invoice']

def test_none_correct_remains_unresolved():
    r=route_match([candidate('a')],True)
    result=choose(r,None)
    assert result['state']=='needs_review' and result['selected_po_line_id'] is None

@pytest.mark.parametrize('override',[{'evidence_complete':False},{'current_version':2},{'actor':''},{'reason':''}])
def test_human_choice_rejects_missing_or_stale_evidence(override):
    r=route_match([candidate('a')],True)
    with pytest.raises(ValueError):choose(r,'a',**override)

def test_human_cannot_force_conflict_or_unknown_candidate():
    r=route_match([candidate('a',conflicts=('material',))],True)
    with pytest.raises(ValueError):choose(r,'a')
    with pytest.raises(ValueError):choose(r,'not-in-candidates')

def test_automation_needs_a_calibrated_policy():
    with pytest.raises(ValueError):MatchPolicy(auto_enabled=True)

@pytest.mark.parametrize('score',[float('nan'),float('inf')])
def test_invalid_scores_rejected(score):
    with pytest.raises(ValueError):candidate('a',score)
