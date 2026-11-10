"""Native/scanned PDF text with page coordinates, before field parsing.

Run on untrusted uploads only inside the planned resource-limited worker
subprocess. This utility is not exposed through an upload endpoint yet.
"""
from reconcile.document_types import Word,PageText
import io
import math
import os
import pdfplumber
import pypdfium2
import pytesseract
from pdfminer.pdfdocument import PDFPasswordIncorrect


class DocumentError(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)


def extract_document(data:bytes,max_pages=10,max_bytes=10*1024*1024,on_progress=None):
    if not 1<=max_pages<=100:raise ValueError('Invalid page limit')
    if len(data)>max_bytes:raise DocumentError('PDF_TOO_LARGE')
    if not data.startswith(b'%PDF-'):raise DocumentError('PDF_INVALID')
    try:pdf=pdfplumber.open(io.BytesIO(data))
    except PDFPasswordIncorrect:raise DocumentError('PDF_ENCRYPTED') from None
    except Exception as error:
        # pdfplumber can wrap the original pdfminer password exception.
        current=error;seen=set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if isinstance(current,PDFPasswordIncorrect):raise DocumentError('PDF_ENCRYPTED') from None
            current=current.__cause__ or current.__context__
        raise DocumentError('PDF_INVALID') from None
    with pdf:
        if not pdf.pages:raise DocumentError('PDF_EMPTY')
        if len(pdf.pages)>max_pages:raise DocumentError('PDF_TOO_MANY_PAGES')
        result=[];rendered=None
        try:
            for number,page in enumerate(pdf.pages):
                if on_progress:on_progress('page.started',number+1,len(pdf.pages),None)
                if not (0 < float(page.width) <= 2000 and 0 < float(page.height) <= 2000):raise DocumentError('PDF_PAGE_DIMENSIONS')
                words=page.extract_words()
                # Image-bearing pages use whole-page OCR: native headers alone
                # must not hide a scanned line-item table. Very sparse native
                # pages also get OCR; both routes keep source coordinates.
                use_native=len(words)>=5 and not page.images
                if use_native:
                    result.append(PageText(number+1,'native',float(page.width),float(page.height),tuple(Word(w['text'],(float(w['x0']),float(w['top']),float(w['x1']),float(w['bottom']))) for w in words)))
                    if on_progress:on_progress('page.completed',number+1,len(pdf.pages),'native')
                    continue
                if on_progress:on_progress('ocr.started',number+1,len(pdf.pages),'ocr')
                if rendered is None:rendered=pypdfium2.PdfDocument(data)
                rp=rendered[number]
                bitmap=None
                try:
                    bitmap=rp.render(scale=200/72)
                    image=bitmap.to_pil()
                    try:
                        engine=os.getenv('OCR_ENGINE','tesseract')
                        if engine=='paddle':
                            from reconcile.paddle_text import recognize
                            try:found=recognize(image,float(page.width),float(page.height))
                            except Exception as error:raise DocumentError('OCR_MODEL_OR_INFERENCE_FAILED') from error
                            warnings=() if found else ('no_readable_text',)
                            result.append(PageText(number+1,'ocr',float(page.width),float(page.height),found,warnings,
                                'ppocr-v5-'+os.getenv('OCR_PROFILE','server')))
                            if on_progress:on_progress('page.completed',number+1,len(pdf.pages),'ocr')
                            continue
                        if engine!='tesseract':raise DocumentError('OCR_ENGINE_UNSUPPORTED')
                        ocr=pytesseract.image_to_data(image,config='--psm 3',output_type=pytesseract.Output.DICT,timeout=30)
                        sx=float(page.width)/image.width;sy=float(page.height)/image.height
                        found=[]
                        for i,text in enumerate(ocr['text']):
                            text=text.strip()
                            if not text:continue
                            x,y,w,h=(float(ocr[k][i]) for k in ['left','top','width','height'])
                            confidence=float(ocr['conf'][i])
                            if not all(math.isfinite(v) for v in [x,y,w,h,confidence]):continue
                            found.append(Word(text,(x*sx,y*sy,(x+w)*sx,(y+h)*sy),confidence))
                        warnings=() if found else ('no_readable_text',)
                        result.append(PageText(number+1,'ocr',float(page.width),float(page.height),tuple(found),warnings,'tesseract'))
                        if on_progress:on_progress('page.completed',number+1,len(pdf.pages),'ocr')
                    except pytesseract.TesseractNotFoundError:raise DocumentError('OCR_UNAVAILABLE') from None
                    except pytesseract.TesseractError:raise DocumentError('OCR_FAILED') from None
                    except RuntimeError:raise DocumentError('OCR_TIMEOUT') from None
                    finally:image.close()
                finally:
                    if bitmap is not None:bitmap.close()
                    rp.close()
        finally:
            if rendered is not None:rendered.close()
        return result
