from copy import deepcopy
from pathlib import Path
import json
import pytest
from reconcile.pipeline import evaluate
from reconcile.tax_validation import read_tax_rate
from reconcile.document_types import PageText, Word
from reconcile.workflows import apply_corrections
from reconcile.errors import AppError

ROOT=Path(__file__).resolve().parents[2]


def ordinary():
    case=json.loads((ROOT/'fixtures/workflows/v1/inputs/W01.json').read_text())
    for po in case['company']['purchase_orders']:
        for line in po['lines']:line['tax_rate']='0'
    return case['document'],case['company']


def with_tax(rate='0.18',total='540.00'):
    doc,company=ordinary()
    doc.update(tax_rate=rate,tax_total=total,grand_total=str(__import__('decimal').Decimal('3000')+__import__('decimal').Decimal(total)))
    company['purchase_orders'][0]['lines'][0]['tax_rate']='0.18'
    return doc,company


def test_live_separated_tax_checks_rate_and_amount():
    doc,company=with_tax()
    assert evaluate(doc,company,'file')['bucket']=='accept'
    doc['tax_total']='500.00';doc['grand_total']='3500.00'
    result=evaluate(doc,company,'file')
    assert result['bucket']=='reject' and 'tax' in result['blocking_rules']
    assert result['findings']['arithmetic']['status']=='pass'


def test_missing_tax_rate_is_not_filled_from_order():
    doc,company=with_tax(rate=None)
    result=evaluate(doc,company,'file')
    assert result['bucket']=='human_review'
    assert result['document']['tax_rate'] is None


def test_tax_classification_difference_requires_review():
    doc,company=with_tax(rate='0.12',total='360')
    assert evaluate(doc,company,'file')['findings']['tax']['status']=='unknown'


def test_unsupported_price_basis_does_not_create_false_arithmetic_rejection():
    doc,company=ordinary()
    doc.update(unsupported_features=['Tax-inclusive pricing needs manual verification'],grand_total='99.00')
    result=evaluate(doc,company,'file')
    assert result['bucket']=='human_review' and 'arithmetic' not in result['blocking_rules']


def test_human_none_of_candidates_overrides_even_an_exact_sku():
    doc,company=ordinary()
    result=evaluate(doc,company,'file',{'1':{'none_of_candidates':True,'reason':'Printed material could not be verified.'}})
    assert result['bucket']=='human_review'


def test_review_cannot_edit_policy_currency_or_ledger_and_keeps_original():
    doc,_=ordinary();original=deepcopy(doc)
    for path in ['policy.quantity_tolerance','header.currency','company.allocations']:
        with pytest.raises(AppError):apply_corrections(doc,{},[{'field_path':path,'value':'999','reason':'Attempt to change trusted policy'}],{})
    assert doc==original


def test_whole_table_repair_clears_previous_identity_attestations():
    doc,_=ordinary()
    repaired,reviews,_=apply_corrections(doc,{'1':{'po_line_id':'old','reason':'Old row identity'}},[
        {'field_path':'lines','value':[{'description':'Replacement row','qty':'1','unit_price':'5','amount':'5'}],
         'reason':'Reconstructed the complete printed table from the source page.'}],{})
    assert repaired['lines'][0]['description']=='Replacement row'
    assert reviews=={} and doc['lines'][0]['description']!='Replacement row'


def test_printed_tax_component_rates_keep_source_evidence_and_conflicts():
    def page(rows):
        return PageText(1,'native',600,800,tuple(Word(t,(i*50,20+n*20,i*50+40,30+n*20)) for n,row in enumerate(rows) for i,t in enumerate(row.split())))
    value=read_tax_rate([page(['CGST @ 9% INR 270','SGST @ 9% INR 270'])])
    assert value['value']=='0.18' and len(value['evidence'])==2
    assert read_tax_rate([page(['GST @ 18% INR 540','GST @ 12% INR 360'])])['status']=='ambiguous'


def test_low_ocr_scores_keep_reading_but_require_source_verification():
    from reconcile.source_quality import assess
    from reconcile.business_validation import from_extraction
    page=PageText(1,'ocr',600,800,(Word('INV-001',(10,10,80,30),45),))
    fields={'header':{'invoice_number':{'value':'INV-001','status':'found','evidence':[
        {'page':1,'method':'ocr','bbox':(10,10,80,30),'text':'INV-001'}]}},'lines':[],'warnings':[]}
    flagged=assess(fields,[page])
    assert flagged['header']['invoice_number']['value']=='INV-001'
    assert from_extraction(flagged)['invoice_number'] is None
    assert 'requires_source_verification' not in fields['header']['invoice_number']


def test_percentages_next_to_tax_amounts_do_not_become_money_candidates():
    from reconcile.invoice_parser import monetary_field, text_rows
    words=tuple(Word(t,(i*50,20,i*50+45,32)) for i,t in enumerate(['Tax','@','18%','INR','540.00']))
    reading=monetary_field(text_rows([PageText(1,'native',600,800,words)]),r'\bTax\b')
    assert reading.status=='found' and reading.value=='540.00'
