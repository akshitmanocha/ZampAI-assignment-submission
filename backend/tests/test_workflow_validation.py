from copy import deepcopy
from pathlib import Path
import json,sys
import pytest
from reconcile.business_validation import validate as validate_at_date

def validate(document,company,fingerprint):
    return validate_at_date(document,company,fingerprint,today="2026-11-10")

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ml'))
from evaluate_workflows import check_hashes,compare,context_for,extraction_errors
from curate_workflows import curate
DATA=ROOT/'fixtures/workflows/v1'

@pytest.mark.parametrize('case_id',[f'W{i:02}' for i in range(1,26)])
def test_frozen_authored_business_expectations(case_id):
    check_hashes(DATA)
    c=json.loads((DATA/'inputs'/f'{case_id}.json').read_text());a=json.loads((DATA/'expected'/f'{case_id}.json').read_text())
    company=context_for(c,'test-document');before=deepcopy(company)
    result=validate(c['document'],company,'test-document')
    assert compare(result,a)==[]
    assert company==before


def test_curator_reproduces_frozen_labels_without_production_engine(tmp_path):
    out=tmp_path/'dataset';curate(out)
    assert (out/'manifest.json').read_bytes()==(DATA/'manifest.json').read_bytes()
    with pytest.raises(RuntimeError):curate(out)


def test_expected_answer_cannot_override_runtime_decision():
    c=json.loads((DATA/'inputs/W07.json').read_text())
    d=deepcopy(c['document']);d['expected_bucket']='accept'
    assert validate(d,c['company'],'test')['bucket']=='reject'


def test_one_uncertain_row_cannot_erase_a_confirmed_price_failure():
    c=json.loads((DATA/'inputs/W01.json').read_text());d=deepcopy(c['document'])
    d['lines'][0]['unit_price']='600.00';d['lines'][0]['amount']='3600.00'
    other=deepcopy(d['lines'][0]);other['description']='GLV-M Nitrile gloves medium [BOX]';d['lines'].append(other)
    d.update(subtotal='7200.00',grand_total='7200.00')
    r=validate(d,c['company'],'test')
    assert r['bucket']=='reject' and 'unit_price' in r['blocking_rules']
    assert 'unit_conversion' in r['unknown_rules']


def test_matching_bucket_with_wrong_invoice_identifier_is_not_full_pass():
    c=json.loads((DATA/'inputs/W01.json').read_text());d=deepcopy(c['document']);d['invoice_number']='WRONG'
    assert 'extraction:invoice_number' in extraction_errors(d,c['document'])

def test_empty_extraction_is_uncertainty_not_an_arithmetic_rejection():
    c=json.loads((DATA/'inputs/W01.json').read_text());d=deepcopy(c['document']);d['lines']=[]
    r=validate(d,c['company'],'test')
    assert r['bucket']=='human_review'
    assert r['findings']['arithmetic']['status']=='unknown'


def test_missing_master_attributes_do_not_prove_product_conflict():
    c=json.loads((DATA/'inputs/W01.json').read_text());c['company']['purchase_orders'][0]['lines'][0]['material']=None
    r=validate(c['document'],c['company'],'test')
    assert r['bucket']=='human_review'
    assert r['findings']['product_specification']['status']=='unknown'

def test_rescanned_duplicate_does_not_depend_on_equal_file_hash():
    c=json.loads((DATA/'inputs/W12.json').read_text())
    c['company']['invoice_history'][0]['document_sha256']='prior-different-file'
    assert 'duplicate' in validate(c['document'],c['company'],'new-scan-file')['blocking_rules']


def test_identical_file_is_detected_even_if_supplied_identity_differs():
    c=json.loads((DATA/'inputs/W01.json').read_text())
    c['company']['invoice_history']=[{'vendor_id':'v2','invoice_number':'OTHER-1','gross_total':'1.00','document_sha256':'same-file','review_state':'approved'}]
    assert 'duplicate' in validate(c['document'],c['company'],'same-file')['blocking_rules']


def test_normalized_identifier_collision_requires_review_not_duplicate_proof():
    c=json.loads((DATA/'inputs/W01.json').read_text())
    c['company']['invoice_history']=[{'vendor_id':'v1','invoice_number':'SH000123','gross_total':'3000.00','document_sha256':'other-file','review_state':'approved'}]
    r=validate(c['document'],c['company'],'current-file')
    assert r['bucket']=='human_review'
    assert r['findings']['duplicate']['status']=='unknown'

def test_empty_pdf_benchmark_cannot_be_reported_as_passed(tmp_path):
    from evaluate_workflows import run
    pdfs=tmp_path/'pdfs';pdfs.mkdir()
    (pdfs/'manifest.json').write_text(json.dumps({'variants':[],'artifacts':[]}))
    with pytest.raises(RuntimeError,match='zero-test'):
        run(DATA,pdfs,tmp_path/'results')

def test_offsetting_prices_reports_both_errors_not_only_wrong_bucket():
    c=json.loads((DATA/'inputs/W05.json').read_text())
    r=validate(c['document'],c['company'],'test')
    checks=r['findings']['unit_price']['line_checks']
    assert [(row['source_line'],row['status']) for row in checks]==[(1,'fail'),(2,'fail')]
    from decimal import Decimal
    assert [Decimal(row['delta']) for row in checks]==[Decimal('1'),Decimal('-1')]

def test_printed_sku_matching_is_generic_not_fixture_specific():
    c=json.loads((DATA/'inputs/W01.json').read_text())
    c['document']['lines'][0]['description']=c['document']['lines'][0]['description'].replace('GLV-M','ABCXYZ')
    c['company']['purchase_orders'][0]['lines'][0]['sku']='ABCXYZ'
    assert validate(c['document'],c['company'],'test')['bucket']=='accept'


def test_business_date_is_injected_not_hardcoded_in_the_validator():
    c=json.loads((DATA/'inputs/W01.json').read_text());c['document']['invoice_date']='2026-11-11'
    assert validate_at_date(c['document'],c['company'],'test',today='2026-11-10')['bucket']=='human_review'
    assert validate_at_date(c['document'],c['company'],'test',today='2026-11-12')['bucket']=='accept'
