"""Ensure evaluation counts abstentions and wrong row amounts as failures."""
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
source=Path(__file__).resolve().parents[2]/'ml/extraction_metrics.py'
spec=importlib.util.spec_from_file_location('extraction_metrics',source)
metrics=importlib.util.module_from_spec(spec);spec.loader.exec_module(metrics)

def test_row_metric_requires_correct_quantity_price_and_amount():
    gold=[{'description':'Nitrile gloves','quantity':600,'unit_price':5,'amount':3000}]
    predicted=[{'description':{'value':'Nitrile gloves'},'qty':{'status':'found','value':'600'},'unit_price':{'status':'found','value':'5'},'amount':{'status':'found','value':'3100'}}]
    assert metrics.line_score(predicted,gold)['tp']==0
    predicted[0]['amount']['value']='3000'
    assert metrics.line_score(predicted,gold)['tp']==1
    predicted[0]['qty']['status']='ambiguous'
    assert metrics.line_score(predicted,gold)['tp']==0

def test_core_row_metric_is_separate_from_full_unit_price_metric():
    gold=[{'description':'Taxi distance charge','quantity':1,'unit_price':40,'amount':40}]
    predicted=[{'description':{'value':'Taxi distance charge'},'qty':{'status':'found','value':'1'},'unit_price':{'status':'missing','value':None},'amount':{'status':'found','value':'40'}}]
    assert metrics.line_score(predicted,gold)['tp']==0
    assert metrics.line_score(predicted,gold,require_unit_price=False)['tp']==1

def test_identifier_metrics_preserve_zeros_and_separators():
    assert not metrics.equal('invoice_number','INV-0001','INV-1')
    assert not metrics.equal('po_reference','PO-12-3','PO-123')
    assert metrics.equal('invoice_number','INV-001','inv-001')

def test_similar_product_description_is_not_counted_as_correct_extraction():
    gold=[{'description':'Blue medical nitrile examination gloves medium','quantity':1,'unit_price':40,'amount':40}]
    predicted=[{'description':{'value':'Blue medical latex examination gloves medium'},'qty':{'status':'found','value':'1'},'unit_price':{'status':'found','value':'40'},'amount':{'status':'found','value':'40'}}]
    assert metrics.line_score(predicted,gold)['tp']==0
