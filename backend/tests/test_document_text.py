import io
import shutil
import pytest
from reportlab.pdfgen import canvas
import pypdfium2
from reconcile.document_text import extract_document,DocumentError


def native_invoice():
    out=io.BytesIO();c=canvas.Canvas(out)
    for y,text in [(780,'SafeHands Supplies'),(750,'Invoice INV-001 PO-2026-0147'),(720,'Nitrile gloves medium powder free'),(690,'Quantity 600 Unit price 5.00'),(650,'Total INR 3000.00')]:c.drawString(60,y,text)
    c.save();return out.getvalue()

def test_reads_native_pdf_and_preserves_source_coordinates():
    pages=extract_document(native_invoice())
    assert len(pages)==1 and pages[0].method=='native'
    assert 'INV-001' in [w.text for w in pages[0].words]
    assert all(w.confidence is None for w in pages[0].words)
    for w in pages[0].words:
        x0,y0,x1,y1=w.bbox
        assert 0<=x0<x1<=pages[0].width
        assert 0<=y0<y1<=pages[0].height

@pytest.mark.skipif(not shutil.which('tesseract'),reason='real Tesseract required')
def test_reads_scanned_pdf_using_real_ocr():
    doc=pypdfium2.PdfDocument(native_invoice());page=doc[0];bitmap=page.render(scale=200/72)
    image=bitmap.to_pil().convert('RGB');out=io.BytesIO();image.save(out,format='PDF',resolution=200)
    image.close();bitmap.close();page.close();doc.close()
    pages=extract_document(out.getvalue())
    assert pages[0].method=='ocr'
    text=' '.join(w.text for w in pages[0].words)
    assert 'SafeHands' in text and '3000.00' in text
    assert all(w.confidence is not None for w in pages[0].words)
    assert all(0<=w.bbox[0]<w.bbox[2]<=pages[0].width and 0<=w.bbox[1]<w.bbox[3]<=pages[0].height for w in pages[0].words)

def test_invalid_or_oversized_files_are_rejected():
    with pytest.raises(DocumentError,match='PDF_INVALID'):extract_document(b'not a PDF')
    with pytest.raises(DocumentError,match='PDF_TOO_LARGE'):extract_document(native_invoice(),max_bytes=10)

def test_page_limit_is_enforced():
    out=io.BytesIO();c=canvas.Canvas(out)
    for _ in range(2):c.drawString(40,700,'a page');c.showPage()
    c.save()
    with pytest.raises(DocumentError,match='PDF_TOO_MANY_PAGES'):extract_document(out.getvalue(),max_pages=1)

def test_encrypted_pdf_requires_password_instead_of_guessing():
    from reportlab.lib.pdfencrypt import StandardEncryption
    out=io.BytesIO();c=canvas.Canvas(out,encrypt=StandardEncryption('test-only-password'))
    c.drawString(40,700,'Invoice confidential');c.save()
    with pytest.raises(DocumentError,match='PDF_ENCRYPTED'):extract_document(out.getvalue())
