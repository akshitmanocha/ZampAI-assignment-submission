import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('coverage_policy',Path(__file__).resolve().parents[2]/'ml/coverage_policy.py')
import sys
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)

def test_review_band_and_nonmatch_are_not_invoice_rejection():
    policy=m.PairPolicy(-1,1,.9)
    assert policy.classify(-2)=='different_product'
    assert policy.classify(0)=='review'
    assert policy.classify(2)=='same_product'
    assert policy.classify(float('nan'))=='review'

def test_validation_policy_meets_coverage_and_preserves_error_counts():
    rows=[{'score':i,'label':int(i>=10)} for i in range(20)]
    policy=m.fit(rows,.9);report=m.evaluate(rows,policy)
    assert report['automation']>=.9
    assert report['automatic_accuracy']==1
    unseen=m.evaluate([{'score':100,'label':0}],policy)
    assert unseen['wrong_same_product']==1
    assert unseen['automatic_accuracy']==0

def test_90_percent_budget_uses_scores_only_and_reports_actual_errors():
    rows=[{'score':i,'label':int(i>=10)} for i in range(20)]
    policy=m.PairPolicy(8,11,.9)
    report=m.evaluate_at_budget(rows,policy,.9)
    assert report['automatic_pairs']==18
    assert report['review_pairs']==2
    assert report['automatic_accuracy']==1
    reversed_labels=[{**r,'label':1-r['label']} for r in rows]
    changed=m.evaluate_at_budget(reversed_labels,policy,.9)
    assert changed['automatic_pairs']==18
    assert changed['automatic_accuracy']==0
    assert not changed['production_quota_enabled']

def test_invalid_data_or_bounds_do_not_generate_policy():
    import pytest
    with pytest.raises(ValueError):m.PairPolicy(2,1,.9)
    with pytest.raises(ValueError):m.fit([{'score':float('nan'),'label':1}])
