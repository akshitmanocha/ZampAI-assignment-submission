"""Authored regression inputs, independent of publisher evaluation answers."""
from copy import deepcopy
from dataclasses import asdict
import pytest
from reconcile.document_types import PageText,Word
from reconcile.invoice_parser import parse_invoice,Row
from reconcile.source_quality import assess


def page(rows,method='native'):
    words=[]
    for y,cells in rows:
        for x,text in cells:
            words.append(Word(text,(x,y,x+max(8,len(text)*7),y+16)))
    return PageText(1,method,1200,1700,tuple(words))


def gst_page():
    return page([
        (50,[(60,'Example'),(125,'Agencies'),(900,'TAX'),(940,'INVOICE')]),
        (100,[(60,'GSTIN:'),(150,'27ABCDE1234F1ZA')]),
        (180,[(60,'Bill'),(95,'To:'),(500,'Invoice'),(570,'No.:'),(620,'000123')]),
        (210,[(60,'Buyer'),(110,'Corporation')]),
        (300,[(100,'Description'),(370,'HSN/SAC'),(500,'Qty'),(550,'Unit'),(680,'Rate'),(800,'Taxable'),(900,'GST%'),(1000,'CGST'),(1100,'SGST')]),
        (340,[(65,'1'),(100,'Steel'),(145,'bolt'),(370,'7318'),(515,'6'),(550,'BOX'),(680,'100.00'),(810,'600.00'),(915,'18'),(1000,'54.00'),(1100,'54.00')]),
        (440,[(760,'Taxable'),(825,'Value'),(1000,'600.00')]),
        (480,[(760,'CGST'),(1000,'54.00')]),
        (520,[(760,'SGST'),(1000,'54.00')]),
        (560,[(760,'Grand'),(810,'Total'),(1000,'708.00')]),
    ])


def test_gst_columns_keep_net_amount_and_do_not_invent_pack_size():
    result=parse_invoice([gst_page()])
    line=result['lines'][0]
    assert line['description']['value']=='Steel bolt'
    assert line['qty']['value']=='6' and line['unit']['value']=='BOX'
    assert line['unit_price']['value']=='100.00'
    assert line['amount']['value']=='600.00'
    assert line['cgst_amount']['value']=='54.00'
    assert 'pack_factor' not in line
    assert result['header']['subtotal']['value']=='600.00'
    assert result['header']['grand_total']['value']=='708.00'


@pytest.mark.parametrize('scale',[.36,1,2])
def test_column_assignment_is_invariant_to_pixels_or_pdf_point_units(scale):
    original=gst_page()
    scaled=PageText(1,'native',original.width*scale,original.height*scale,
        tuple(Word(w.text,tuple(c*scale for c in w.bbox)) for w in original.words))
    result=parse_invoice([scaled])
    assert result['lines'][0]['description']['value']=='Steel bolt'
    assert result['lines'][0]['qty']['value']=='6'
    assert result['lines'][0]['amount']['value']=='600.00'


def test_customer_is_never_used_as_gst_supplier_when_seller_is_unreadable():
    original=gst_page()
    missing=PageText(1,'native',1200,1700,tuple(w for w in original.words if w.bbox[1]!=50))
    assert parse_invoice([missing])['header']['vendor_name']['value'] is None
    assert parse_invoice([original])['header']['vendor_name']['value']=='Example Agencies'


def receipt(date='18/05/2026',amount='600.00'):
    return page([(40,[(60,'Example'),(125,'Agencies')]),(90,[(60,'GSTIN:'),(150,'27ABCDE1234F1ZA')]),
        (150,[(60,'Bill:'),(100,'000123'),(250,date)]),
        (250,[(60,'Steel'),(110,'bolt')]),
        (280,[(60,'6'),(90,'BOX'),(140,'x'),(180,'100.00'),(300,amount)]),
        (310,[(60,'HSN'),(110,'7318'),(220,'GST'),(260,'18%')]),
        (400,[(60,'Taxable'),(130,'Value'),(300,'600.00')]),
        (440,[(60,'TOTAL'),(300,'708.00')])])


def test_receipt_items_require_printed_amount_and_preserve_identifier_zeros():
    result=parse_invoice([receipt()])
    assert result['header']['invoice_number']['value']=='000123'
    assert result['header']['invoice_date']['value']=='2026-05-18'
    assert result['lines'][0]['amount']['value']=='600.00'
    assert result['lines'][0]['hsn_sac']['value']=='7318'
    assert not parse_invoice([receipt(amount='?')])['lines']


def test_ambiguous_numeric_dates_stay_for_review_even_on_indian_gst_receipt():
    result=parse_invoice([receipt('03/04/2026')])
    assert result['header']['invoice_date']['status']=='ambiguous'
    assert result['header']['invoice_date']['value'] is None


def test_deskewed_layout_evidence_and_quality_use_original_source_coordinates():
    word=Word('000123',(500,500,550,520),45,(50,50,100,70))
    evidence=Row(1,'ocr',(word,)).evidence()
    assert evidence.bbox==(50,50,100,70)
    extraction={'header':{'invoice_number':{'value':'000123','status':'found','evidence':[asdict(evidence)]}},'lines':[],'warnings':[]}
    result=assess(extraction,[PageText(1,'ocr',1200,1700,(word,))])
    assert result['header']['invoice_number']['requires_source_verification']
    assert result['header']['invoice_number']['minimum_ocr_score']==45


def test_missing_or_modified_ocr_weights_fail_before_inference(tmp_path):
    from reconcile.ocr_models import verify
    with pytest.raises(RuntimeError,match='Missing or invalid'):verify(tmp_path,'mobile')
    (tmp_path/'ch_PP-OCRv5_det_mobile.onnx').write_bytes(b'not the pinned weights')
    with pytest.raises(RuntimeError,match='Missing or invalid'):verify(tmp_path,'mobile')
