import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('uncertainty',Path(__file__).resolve().parents[2]/'ml/uncertainty.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)

def test_zero_observed_errors_is_not_zero_future_risk():
    assert u.upper_error_bound(0,2)==pytest.approx(0.77639320225)
    assert u.upper_error_bound(0,100)>0
    assert u.upper_error_bound(0,0)==1

def test_threshold_minimizes_review_without_validation_false_matches():
    rows=[{'score':1,'label':0},{'score':2,'label':1},{'score':3,'label':0},{'score':4,'label':1},{'score':5,'label':1}]
    assert u.choose_match_threshold(rows)==4

def test_new_mistakes_remain_visible_after_threshold_selection():
    rows=[{'score':10,'label':0,'family':'unseen'}]
    d=u.evaluate(rows,5)
    assert d['observed_match_precision']==0
    assert d['wrong_automatic_matches']==1
    assert not d['strict_zero_risk_certified']

def test_no_automation_has_no_defined_precision():
    r=u.evaluate([{'score':1,'label':1,'family':'a'}],100)
    assert r['observed_match_precision'] is None
    assert r['automatic_coverage']==0
