from copy import deepcopy
from reconcile.extraction_recovery import combine_header_readings


def result(value,status='found'):
    return {'header':{'grand_total':{'value':value,'status':status,'evidence':[],'alternatives':[]}},'lines':[],'warnings':[]}

def test_conflicting_readings_are_not_silently_repaired():
    local=result('3000.00');before=deepcopy(local)
    merged=combine_header_readings(local,result('3100.00'))
    assert merged['header']['grand_total']['status']=='ambiguous'
    assert merged['header']['grand_total']['value'] is None
    assert local==before
    assert merged['original_extraction']==before

def test_new_vision_value_is_marked_unverified():
    merged=combine_header_readings(result(None,'missing'),result('3000.00'))
    assert merged['header']['grand_total']['requires_source_verification']
    assert len(merged['header']['grand_total']['readings'])==2

def test_agreement_does_not_invent_verification_or_overwrite_evidence():
    local=result('3000.00')
    merged=combine_header_readings(local,result('3000'))
    assert merged['header']['grand_total']['value']=='3000.00'
    assert 'verified' not in merged['header']['grand_total']

def test_missing_vision_value_does_not_remove_original():
    merged=combine_header_readings(result('3000.00'),result(None,'missing'))
    assert merged['header']['grand_total']['value']=='3000.00'
