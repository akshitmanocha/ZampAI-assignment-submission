import io
from decimal import Decimal
import shutil
import pytest
from reportlab.pdfgen import canvas
import pypdfium2
from reconcile.document_text import extract_document
from reconcile.invoice_parser import parse_invoice,decimal_string


def invoice_pdf(po=True,extra_total=None):
    out=io.BytesIO();c=canvas.Canvas(out,pagesize=(595,842))
    c.drawString(45,790,'SafeHands Supplies')
    c.drawString(45,755,'Invoice No: INV-000123')
    c.drawString(350,755,'Date: 2026-11-10')
    if po:c.drawString(45,730,'PO: PO-2026-0147')
    for x,text in [(45,'DESCRIPTION'),(325,'QTY'),(400,'UNIT PRICE'),(510,'AMOUNT')]:c.drawString(x,670,text)
    for x,text in [(45,'Medium nitrile gloves'),(325,'600'),(420,'5.00'),(510,'3000.00')]:c.drawString(x,640,text)
    c.drawString(360,570,'Subtotal INR 3000.00')
    c.drawString(360,540,'Grand Total INR 3000.00')
    if extra_total:c.drawString(360,510,'Grand Total INR '+extra_total)
    c.save();return out.getvalue()


def test_actual_native_invoice_fields_rows_and_evidence():
    result=parse_invoice(extract_document(invoice_pdf()))
    h=result['header']
    assert h['vendor_name']['value']=='SafeHands Supplies'
    assert h['invoice_number']['value']=='INV-000123'
    assert h['po_reference']['value']=='PO-2026-0147'
    assert h['invoice_date']['value']=='2026-11-10'
    assert h['currency']['value']=='INR'
    assert Decimal(h['grand_total']['value'])==Decimal('3000')
    assert len(result['lines'])==1
    assert result['lines'][0]['description']['value']=='Medium nitrile gloves'
    assert Decimal(result['lines'][0]['qty']['value'])==600
    assert Decimal(result['lines'][0]['unit_price']['value'])==5
    assert h['grand_total']['evidence'][0]['page']==1
    assert h['invoice_number']['evidence'][0]['method']=='native'


def test_missing_po_is_not_invented_from_other_fields():
    h=parse_invoice(extract_document(invoice_pdf(po=False)))['header']
    assert h['po_reference']['value'] is None
    assert h['po_reference']['status']=='missing'


def test_conflicting_totals_remain_ambiguous():
    r=parse_invoice(extract_document(invoice_pdf(extra_total='3100.00')))
    assert r['header']['grand_total']['status']=='ambiguous'
    assert set(r['header']['grand_total']['alternatives'])=={'3000.00','3100.00'}

@pytest.mark.skipif(not shutil.which('tesseract'),reason='real Tesseract required')
def test_actual_scanned_invoice_uses_same_parser():
    doc=pypdfium2.PdfDocument(invoice_pdf());page=doc[0];bitmap=page.render(scale=200/72)
    image=bitmap.to_pil().convert('RGB');out=io.BytesIO();image.save(out,format='PDF',resolution=200)
    image.close();bitmap.close();page.close();doc.close()
    result=parse_invoice(extract_document(out.getvalue()))
    assert result['header']['invoice_number']['value']=='INV-000123'
    assert result['header']['grand_total']['value']=='3000.00'
    assert result['header']['grand_total']['evidence'][0]['method']=='ocr'
    assert len(result['lines'])==1

@pytest.mark.parametrize('printed,expected',[('INR 1,23,456.78','123456.78'),('C$2331.00','2331.00'),('12,50',None),('NaN',None),('1,234.50','1234.50')])
def test_decimal_parser_preserves_monetary_meaning(printed,expected):
    assert decimal_string(printed)==expected

def test_powder_is_not_a_purchase_order_reference():
    from reconcile.document_types import PageText,Word
    page=PageText(1,'native',600,800,(Word('Powder-free',(10,10,80,20)),Word('gloves',(85,10,120,20)),Word('600',(130,10,150,20))))
    assert parse_invoice([page])['header']['po_reference']['status']=='missing'

def test_invoice_total_is_not_an_invoice_identifier():
    from reconcile.document_types import PageText,Word
    page=PageText(1,'native',600,800,(Word('Invoice',(10,10,50,20)),Word('total',(55,10,80,20)),Word('3000.00',(85,10,135,20))))
    assert parse_invoice([page])['header']['invoice_number']['status']=='missing'

def test_date_below_label_is_read_from_its_own_column():
    from reconcile.document_types import PageText,Word
    words=(Word('DATE',(350,10,390,20)),Word('Address',(10,35,60,45)),Word('1234',(70,35,100,45)),Word('15/07/2023',(350,35,430,45)))
    date=parse_invoice([PageText(1,'native',600,800,words)])['header']['invoice_date']
    assert date['value']=='2023-07-15'
    assert date['evidence'][0]['text']=='15/07/2023'

def test_ambiguous_numeric_date_is_not_guessed():
    from reconcile.document_types import PageText,Word
    words=(Word('Date:',(10,10,40,20)),Word('05/06/2026',(45,10,130,20)))
    date=parse_invoice([PageText(1,'native',600,800,words)])['header']['invoice_date']
    assert date['status']=='ambiguous' and date['value'] is None

def test_net_and_vat_totals_are_not_grand_total():
    from reconcile.document_types import PageText,Word
    words=[]
    for y,label,value in [(10,'NET TOTAL','2970.00'),(40,'VAT TOTAL','87.10'),(70,'EUR TOTAL','3057.10')]:
        for x,text in [(20,label),(200,value)]:words.append(Word(text,(x,y,x+100,y+12)))
    result=parse_invoice([PageText(1,'native',600,800,tuple(words))])
    assert result['header']['grand_total']['value']=='3057.10'

def test_supplier_name_can_span_title_lines():
    from reconcile.document_types import PageText,Word
    words=tuple(Word(text,(20,y,250,y+20)) for y,text in [(10,'Oakwood'),(40,'Residential'),(70,'Ltd')])
    result=parse_invoice([PageText(1,'native',600,800,words)])
    assert result['header']['vendor_name']['value']=='Oakwood Residential Ltd'

def test_explicit_from_label_supports_names_without_legal_suffix():
    from reconcile.document_types import PageText,Word
    words=(Word('FROM',(20,10,60,20)),Word('BILL',(300,10,330,20)),Word('TO',(335,10,350,20)),Word('Sunrise',(20,40,70,50)),Word('Inn',(75,40,90,50)),Word('Customer',(300,40,380,50)))
    result=parse_invoice([PageText(1,'native',600,800,words)])
    assert result['header']['vendor_name']['value']=='Sunrise Inn'

def test_issue_date_is_not_hidden_by_nearby_amount_due_label():
    from reconcile.document_types import PageText,Word
    words=(Word('ISSUE',(150,10,190,20)),Word('DATE',(195,10,230,20)),Word('AMOUNT',(350,10,410,20)),Word('DUE',(415,10,440,20)),Word('15/08/2023',(150,40,230,50)),Word('425.25',(350,40,410,50)))
    assert parse_invoice([PageText(1,'native',600,800,words)])['header']['invoice_date']['value']=='2023-08-15'

def test_po_box_address_does_not_become_purchase_order():
    from reconcile.document_types import PageText,Word
    words=(Word('PO',(20,10,40,20)),Word('BOX',(45,10,70,20)),Word('5678',(75,10,110,20)))
    assert parse_invoice([PageText(1,'native',600,800,words)])['header']['po_reference']['status']=='missing'

def test_alphabetic_invoice_identifier_is_read_only_with_explicit_label():
    from reconcile.document_types import PageText,Word
    words=(Word('Invoice',(20,10,60,20)),Word('No:',(65,10,80,20)),Word('SH-STATE-A',(85,10,180,20)))
    assert parse_invoice([PageText(1,'native',600,800,words)])['header']['invoice_number']['value']=='SH-STATE-A'

def test_missing_invoice_number_does_not_steal_po_reference_below():
    from reconcile.document_types import PageText,Word
    words=(Word('Invoice',(20,10,60,20)),Word('No:',(65,10,80,20)),Word('PO:',(20,40,50,50)),Word('PO-2026-0147',(55,40,180,50)))
    assert parse_invoice([PageText(1,'native',600,800,words)])['header']['invoice_number']['status']=='missing'


def test_explicit_from_anchor_outranks_same_size_stacked_title_guess():
    from reconcile.document_types import PageText, Word
    words=tuple(Word(text,(40,y,200,y+12)) for y,text in [(10,'INVOICE'),(35,'FROM'),(55,'SafeHands Supplies')])
    assert parse_invoice([PageText(1,'native',600,800,words)])['header']['vendor_name']['value']=='SafeHands Supplies'


def test_tax_prefixed_invoice_number_does_not_become_tax_amount():
    from reconcile.document_types import PageText, Word
    words=tuple(Word(text,(40,y,300,y+12)) for y,text in [(10,'Invoice No: TAX-REAL-PDF-1'),(40,'Tax @ 18% INR 540.00')])
    assert parse_invoice([PageText(1,'native',600,800,words)])['header']['tax_total']['value']=='540.00'
