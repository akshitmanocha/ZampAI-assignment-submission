"""Resource-limited child process for untrusted PDFs; no database credentials.

Communicates real progress and the extraction over newline-delimited JSON.
Parent enforces a wall timeout and kills the entire process group on expiry.
"""
import base64
import io
import json
import resource
import sys


def emit(value):
    print(json.dumps(value), flush=True)


def main():
    # Linux parent-death signal: stop parsing if the owning worker is killed.
    import ctypes, os, signal
    ctypes.CDLL(None).prctl(1, signal.SIGKILL)
    if os.getppid() == 1:
        raise SystemExit(3)
    resource.setrlimit(resource.RLIMIT_CPU, (100, 105))
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024, 1536 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (96, 96))
    from reconcile.document_text import extract_document, DocumentError
    from reconcile.invoice_parser import parse_invoice
    import pypdfium2
    data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    ocr = False

    def progress(kind, page, pages, method):
        nonlocal ocr
        if kind == 'ocr.started' and not ocr:
            ocr = True
            emit({'event': 'stage.started', 'stage': 'ocr', 'data': {'summary': 'Reading image-only document regions'}})
        emit({'event': 'stage.progress', 'stage': 'ocr' if method == 'ocr' else 'text_layer',
              'data': {'page': page, 'pages': pages, 'method': method, 'summary': kind}})

    try:
        emit({'event': 'stage.started', 'stage': 'text_layer', 'data': {'summary': 'Reading actual PDF pages'}})
        pages = extract_document(data, on_progress=progress)
        emit({'event': 'stage.completed', 'stage': 'text_layer', 'data': {'summary': f'Read {len(pages)} pages'}})
        emit({'event': 'stage.completed' if ocr else 'stage.skipped', 'stage': 'ocr',
              'data': {'summary': 'OCR finished' if ocr else 'Native text was sufficient'}})
        emit({'event': 'stage.started', 'stage': 'field_extraction', 'data': {'summary': 'Locating invoice fields and rows'}})
        extraction = parse_invoice(pages)
        from reconcile.tax_validation import read_tax_rate
        extraction['header']['tax_rate'] = read_tax_rate(pages)
        from reconcile.source_quality import assess
        extraction = assess(extraction, pages)
        previews = []
        pdf = pypdfium2.PdfDocument(data)
        try:
            for number, page in enumerate(pages):
                p = pdf[number]
                bitmap = p.render(scale=min(1.6, 1400 / max(page.width, page.height)))
                try:
                    image = bitmap.to_pil()
                    buffer = io.BytesIO()
                    image.save(buffer, format='PNG')
                    previews.append(base64.b64encode(buffer.getvalue()).decode())
                    image.close()
                finally:
                    bitmap.close()
                    p.close()
        finally:
            pdf.close()
        emit({'event': 'stage.completed', 'stage': 'field_extraction', 'data': {'summary': f'Extracted {len(extraction["lines"])} item rows'}})
        emit({'result': {'fields': extraction, 'pages': [p.to_dict() for p in pages], 'previews': previews}})
    except DocumentError as error:
        emit({'error': error.code})
        raise SystemExit(2)
    except Exception:
        emit({'error': 'PDF_PROCESSING_FAILED'})
        raise SystemExit(2)


if __name__ == '__main__':
    main()
