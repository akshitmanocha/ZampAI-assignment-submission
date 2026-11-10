"""PDF-to-structured-fields benchmark on pinned public synthetic images.

Sampling uses template metadata only for a balanced evaluation set. The parser
receives PDF bytes only, never file IDs, gold values, template IDs or PO data.
"""
import argparse
from collections import Counter,defaultdict
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import time
import unicodedata
from difflib import SequenceMatcher
from datasets import load_dataset
from huggingface_hub import hf_hub_download
from PIL import Image
from scipy.optimize import linear_sum_assignment
import numpy as np
import pytesseract
from reconcile.document_text import extract_document
from reconcile.invoice_parser import parse_invoice
from extraction_metrics import MAP,normalized,equal,line_score,summarize

SOURCE='alamgirqazi/invoice-ocr-synthetic'
REVISION='673ff85be462eb7f3715ec188a295dd17ca11115'






def prepare(root):
    root.mkdir(parents=True,exist_ok=True)
    labels=json.loads(Path(hf_hub_download(SOURCE,'ground_truth_released.json',repo_type='dataset',revision=REVISION)).read_text())
    counts=Counter();selected={};split_counts=Counter()
    # Exclude the first 100 source records, including our previously seen smoke
    # examples. Choose four later documents per template before reading results.
    for row in labels[100:]:
        template=row['_template_used']
        if counts[template]>=4:continue
        split='development' if counts[template]<2 else 'heldout'
        counts[template]+=1
        selected[row['file_name']]={'gold':row,'split':split}
    assert len(selected)==24 and len(counts)==6
    manifest={'dataset':SOURCE,'revision':REVISION,'license':'CC BY 4.0; Alamgir Qazi','selection':'first four records per template after skipping first 100 source records; first two per template development, next two heldout; all quality variants grouped','base_documents':24,'expected_images':72,'source_template_counts':dict(counts),'documents':{name:{'split':v['split'],'template':v['gold']['_template_used'],'gold_sha256':hashlib.sha256(json.dumps(v['gold'],sort_keys=True).encode()).hexdigest()} for name,v in selected.items()},'limitations':['Synthetic English documents; no INR or procurement history','Publisher labels can include fields not visibly printed; full image audit not complete','Only four documents per template; sample is stratified convenience, not population-representative']}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (root/'gold.json').write_text(json.dumps(selected))
    image_dir=root/'images';image_dir.mkdir(exist_ok=True)
    dataset=load_dataset(SOURCE,revision=REVISION,split='train',streaming=True).decode(False)
    present=set(p.stem for p in image_dir.glob('*.png'))
    seen=set()
    for row in dataset:
        name=row['file_name'];quality=row['quality']
        if name not in selected:continue
        key=Path(name).stem+'__'+quality
        if key in seen:raise RuntimeError('Duplicate dataset row')
        seen.add(key)
        if key not in present:
            img=row['image']
            raw=img.get('bytes')
            if raw is None:raise RuntimeError('Expected embedded image bytes')
            image=Image.open(io.BytesIO(raw)).convert('RGB');image.save(image_dir/(key+'.png'));image.close()
        print('Prepared image',len(seen),'of 72',flush=True)
        if len(seen)==72:break
    if len(seen)!=72:raise RuntimeError('Incomplete quality-variant sample')
    return manifest






def evaluate(root,out,split):
    gold=json.loads((root/'gold.json').read_text());manifest=json.loads((root/'manifest.json').read_text())
    out.mkdir(parents=True,exist_ok=True);records=[]
    prediction_file=out/'predictions.jsonl';prediction_file.write_text('')
    for filename,entry in gold.items():
        if entry['split']!=split:continue
        for quality in ['clean','faded','bad_scan']:
            path=root/'images'/(Path(filename).stem+'__'+quality+'.png')
            image=Image.open(path).convert('RGB');buffer=io.BytesIO();image.save(buffer,format='PDF',resolution=150);image.close()
            start=time.perf_counter();error=None
            try:prediction=parse_invoice(extract_document(buffer.getvalue()))
            except Exception as e:
                error=getattr(e,'code',type(e).__name__)
                prediction={'header':{k:{'status':'missing','value':None} for k in MAP},'lines':[],'warnings':['technical_failure']}
            record={'file_name':filename,'quality':quality,'template':entry['gold']['_template_used'],'split':split,'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'seconds':time.perf_counter()-start,'prediction':prediction,'gold':entry['gold'],'technical_error':error,'line_metrics':line_score(prediction['lines'],entry['gold']['line_items'])}
            records.append(record)
            with prediction_file.open('a') as f:f.write(json.dumps(record)+'\n')
            print('Evaluated',len(records),'of 36',quality,flush=True)
    report={'dataset_manifest':manifest,'split':split,'parser_version':records[0]['prediction'].get('parser_version','technical_failure') if records else None,'tesseract':str(pytesseract.get_tesseract_version()),'pdf_input':'public image wrapped as PDF at 150 DPI, then same application PDF reader renders OCR pages at 200 DPI','technical_failures':sum(r['technical_error'] is not None for r in records),'overall':summarize(records),'invoice_templates_only':summarize([r for r in records if r['template'] in ['formal_corporate','freelancer_invoice','modern_minimal']]),'by_quality':{q:summarize([r for r in records if r['quality']==q]) for q in ['clean','faded','bad_scan']},'by_template':{t:summarize([r for r in records if r['template']==t]) for t in sorted({r['template'] for r in records})},'row_metric':'Hungarian alignment by description similarity >=0.85, then exact normalized description and quantity/unit_price/amount must all match; labels not passed to parser','limitations':['Publisher labels not fully visually audited; labelled fields may not be printed','Native PDF accuracy not benchmarked by this image corpus','Small grouped synthetic sample; variants correlated','Counts include unsupported receipt/ticket/utility templates as explicit robustness slices, not a claim of invoice support']}
    (out/'metrics.json').write_text(json.dumps(report,indent=2));print('STRUCTURED_JSON '+json.dumps({'split':split,'overall':report['overall'],'technical_failures':report['technical_failures']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--prepare',action='store_true');p.add_argument('--split',choices=['development','heldout'],default='development');a=p.parse_args()
    if a.prepare:prepare(a.data)
    if a.output:evaluate(a.data,a.output,a.split)
