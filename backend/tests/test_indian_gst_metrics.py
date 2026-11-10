"""Evaluation invariants use small authored answers, never publisher test tuning."""
from copy import deepcopy
from decimal import Decimal
import io,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ml'))
from indian_gst_metrics import equal,score,summarize
from indian_gst_dataset import labels,image_pdf


def cell(value,**extra):return {'value':value,'status':'found' if value is not None else 'missing',**extra}


def example():
    gold={'supplier':{'name':'Test Supplies','gstin':'07TEST'},'invoice_number':'000123','invoice_date':'2026-01-01',
        'totals':{'taxable_value':'10.00','grand_total':'11.80'},'line_items':[
            {'description':'Steel bolt M10','quantity':'2','rate':'5','taxable_value':'10','unit':'PCS'}]}
    prediction={'header':{'vendor_name':cell('Test Supplies'),'invoice_number':cell('000123'),
        'invoice_date':cell('2026-01-01'),'subtotal':cell('10'),'grand_total':cell('11.8')},'lines':[
            {'description':cell('Steel bolt M10'),'qty':cell('2'),'unit_price':cell('5'),'amount':cell('10')}]}
    return {'gold':gold,'prediction':prediction,'technical_error':None}


def test_exact_identifiers_keep_leading_zeros_and_separators():
    assert not equal('invoice_number','123','000123')
    assert not equal('invoice_number','INV123','INV-123')
    assert equal('grand_total','11.80','11.8')
    assert not equal('grand_total','NaN','NaN')


def test_low_source_quality_reduces_coverage_without_hiding_original_value():
    record=example()
    record['prediction']['header']['invoice_number']['requires_source_verification']=True
    result=summarize([record])
    assert result['raw_extracted']['all_five_core_headers']['accuracy']==1
    verified=result['source_verified']
    assert verified['all_five_core_headers']['complete_prediction_coverage']==0
    assert verified['core_headers']['invoice_number']['labelled_non_null']==1
    assert verified['core_headers']['invoice_number']['correct']==0
    assert record['prediction']['header']['invoice_number']['value']=='000123'


def test_proposal_where_publisher_label_is_null_is_false_positive():
    record=example();record['gold']['invoice_number']=None
    result=score([record])['core_header_micro']
    assert result['correct']==4 and result['predicted_found']==5
    assert result['precision_of_found_values']==.8


def test_failed_documents_stay_in_recall_denominator():
    record=example();record['prediction']={'header':{},'lines':[]};record['technical_error']='OCR_FAILED'
    result=score([record])
    assert result['technical_failures']==1
    assert result['core_header_micro']['labelled_non_null']==5
    assert result['core_header_micro']['recall_on_non_null_labels']==0
    assert result['complete_core_rows']['labelled']==1
    assert result['complete_core_rows']['f1']==0


def test_prices_cannot_select_a_more_favourable_gold_alignment():
    record=example();other=deepcopy(record['gold']['line_items'][0]);other.update(description='Steel nut M10',quantity='9',rate='1',taxable_value='9')
    record['gold']['line_items'].append(other)
    predicted=deepcopy(record['prediction']['lines'][0]);predicted['description']=cell('Steel nut M10')
    record['prediction']['lines'].append(predicted)
    record['prediction']['lines'][0].update(qty=cell('9'),unit_price=cell('1'),amount=cell('9'))
    assert score([record])['complete_core_rows']['true_positive']==0


def test_extra_predicted_rows_count_against_precision():
    record=example();record['prediction']['lines'].append(deepcopy(record['prediction']['lines'][0]))
    result=score([record])['complete_core_rows']
    assert result['true_positive']==1 and result['predicted']==2 and result['precision']==.5


def test_unimplemented_gstin_and_unit_targets_are_visible_as_missing():
    result=score([example()])
    assert result['additional_publisher_headers']['supplier_gstin']['labelled_non_null']==1
    assert result['additional_publisher_headers']['supplier_gstin']['recall_on_non_null_labels']==0
    assert result['row_fields']['unit']['labelled_non_null']==1
    assert result['row_fields']['unit']['correct']==0


def test_publisher_decimals_are_loaded_without_binary_float_conversion():
    assert labels({'label':'{"amount":0.29}'})['amount']==Decimal('0.29')


def test_zero_document_score_is_an_error():
    with pytest.raises(RuntimeError,match='zero'):summarize([])


def test_pdf_wrapper_is_deterministic_and_has_no_label_text_layer():
    from PIL import Image
    import pdfplumber
    image=Image.new('RGB',(200,300),'white');b=io.BytesIO();image.save(b,format='PNG');image.close()
    data=image_pdf(b.getvalue());assert image_pdf(b.getvalue())==data
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        assert pdf.pages[0].extract_words()==[]


def test_frozen_external_selection_is_complete_and_does_not_replace_rule_fixtures():
    m=json.loads((ROOT/'ml/data/indian-gst-v1/manifest.json').read_text())
    assert m['dataset']=='Divya52/indian-gst-invoices'
    assert len([r for r in m['records'] if r['config']=='synthetic'])==197
    assert len(m['records'])==261
    assert len({r['key'] for r in m['records']})==261
    assert m['fine_tuning_performed'] is False
    assert (ROOT/'fixtures/workflows/v1/expected/W07.json').exists()


def test_pdf_child_has_bounded_threads_and_no_inherited_database_or_api_secret(monkeypatch):
    from reconcile import worker
    captured={}
    class StopBeforeSpawn(Exception):pass
    def capture(*args,**kwargs):
        captured.update(kwargs)
        raise StopBeforeSpawn()
    monkeypatch.setenv('DATABASE_URL','postgresql://private-test-only')
    monkeypatch.setenv('OPENROUTER_API_KEY','private-test-only')
    monkeypatch.setenv('OMP_THREAD_LIMIT','64')
    monkeypatch.setattr(worker.subprocess,'Popen',capture)
    with pytest.raises(StopBeforeSpawn):worker.extract(b'unused',lambda event:None)
    child=captured['env']
    assert 'DATABASE_URL' not in child and 'OPENROUTER_API_KEY' not in child
    assert child['OMP_THREAD_LIMIT']=='1'
