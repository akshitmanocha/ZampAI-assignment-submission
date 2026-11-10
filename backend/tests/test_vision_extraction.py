import pytest
from pydantic import ValidationError
from reconcile.vision_extraction import PrintedField,normalize_field


def test_model_boxes_are_converted_but_not_claimed_verified():
    field=PrintedField(raw_text='3000.00',bbox=[100,200,400,300])
    result=normalize_field('grand_total',field,600,800)
    assert result['value']=='3000.00'
    assert result['evidence'][0]['bbox']==[60,160,240,240]
    assert result['evidence'][0]['verified'] is False


def test_bare_dollar_does_not_become_usd():
    r=normalize_field('currency',PrintedField(raw_text='$',bbox=[0,0,100,100]),600,800)
    assert r['status']=='ambiguous' and r['value'] is None


def test_printed_ambiguous_date_stays_unresolved():
    r=normalize_field('invoice_date',PrintedField(raw_text='05/06/2026',bbox=[0,0,100,100]),600,800)
    assert r['status']=='ambiguous' and r['value'] is None


def test_missing_or_invalid_vision_values_are_not_repaired():
    r=normalize_field('grand_total',PrintedField(raw_text=None,bbox=None),600,800)
    assert r['status']=='missing'
    r=normalize_field('grand_total',PrintedField(raw_text='12,50',bbox=[0,0,100,100]),600,800)
    assert r['status']=='invalid' and r['value'] is None

@pytest.mark.parametrize('bbox',[[0,0,1001,100],[100,0,10,100],None])
def test_invalid_or_absent_source_boxes_reject_present_values(bbox):
    with pytest.raises(ValidationError):PrintedField(raw_text='value',bbox=bbox)


def test_unknown_response_fields_are_rejected():
    with pytest.raises(ValidationError):PrintedField(raw_text='value',bbox=[0,0,100,100],approve=True)

def test_numeric_unit_is_not_accepted_as_unit_of_measure():
    r=normalize_field('unit',PrintedField(raw_text='120.00',bbox=[0,0,100,100]),600,800)
    assert r['status']=='invalid' and r['value'] is None
