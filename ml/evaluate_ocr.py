"""Small Hugging Face OCR smoke evaluation, NOT structured field extraction.

Scores whether supplied label text/numbers appear anywhere in raw OCR. This is
only a reading diagnostic; it cannot prove field attribution.
"""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
from itertools import islice
import json
from pathlib import Path
import re
import time
import unicodedata
from datasets import load_dataset
from huggingface_hub import HfApi
import pytesseract


def normalized(value):return re.sub(r'\W+','',unicodedata.normalize('NFKC',str(value)).casefold())


def run(out,count):
    source='alamgirqazi/invoice-ocr-synthetic'
    revision=HfApi().dataset_info(source).sha
    ds=load_dataset(source,revision=revision,split='train',streaming=True)
    records=[]
    for row in islice(ds,count):
        start=time.perf_counter();image=row['image'].convert('RGB')
        ocr=pytesseract.image_to_string(image,config='--psm 3',timeout=60)
        tokens=[]
        for value in re.findall(r'(?<![\w.])\d[\d,]*(?:\.\d{1,2})?(?![\w.])',ocr):
            try:tokens.append(Decimal(value.replace(',','')))
            except InvalidOperation:pass
        checks={}
        for key in ['supplier_name','invoice_number','po_number']:
            if row.get(key):checks[key]=normalized(row[key]) in normalized(ocr)
        if row.get('document_total_amount') is not None:
            checks['total_amount_anywhere']=Decimal(str(row['document_total_amount'])) in tokens
        records.append({'file_name':row['file_name'],'quality':row['quality'],'template':row['_template_used'],'image_sha256':hashlib.sha256(image.tobytes()).hexdigest(),'checks':checks,'seconds':time.perf_counter()-start,'ocr_text':ocr})
        print('OCR sample',len(records),'completed',flush=True)
    totals={key:{'eligible':sum(key in r['checks'] for r in records),'recovered':sum(r['checks'].get(key,False) for r in records)} for key in sorted({k for r in records for k in r['checks']})}
    for x in totals.values():x['recovery_rate']=x['recovered']/x['eligible'] if x['eligible'] else None
    result={'dataset':source,'revision':revision,'license_card':'CC BY 4.0; credit dataset author Alamgir Qazi','rows':len(records),'independent_documents':len({r['file_name'] for r in records}),'selection':'first N rows of streaming train split; convenience smoke sample, not a representative held-out test','quality_counts':dict(Counter(r['quality'] for r in records)),'template_counts':dict(Counter(r['template'] for r in records)),'metrics':totals,'metric_definition':'Label-text/number recovery anywhere in raw OCR; not structured extraction accuracy','limitations':['No manual image-label audit yet','No row-level or decision evaluation','Publisher synthetic labels; not INR or linked PO histories','Repeated variants can be correlated'],'tesseract':str(pytesseract.get_tesseract_version())}
    out.mkdir(parents=True,exist_ok=True)
    (out/'metrics.json').write_text(json.dumps(result,indent=2))
    (out/'predictions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    print('OCR_RESULT_JSON '+json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('results/ocr-smoke'));p.add_argument('--count',type=int,default=12);a=p.parse_args();run(a.output,a.count)
