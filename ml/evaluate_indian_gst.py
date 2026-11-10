"""External Indian GST baseline through the actual bounded application extractor.

PDF bytes are the sole extractor input. Labels are joined only after the child
returns. No company records, decisions, training, provider calls or label repair.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime,timezone
from importlib.metadata import version
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from indian_gst_dataset import (ROOT, DEFAULT_DATA, DEFAULT_MANIFEST, load_frozen,labels,image_pdf,digest)
from indian_gst_metrics import VERSION,CORE,EXTRA,ROW_CORE,ROW_EXTRA,summarize
from reconcile.worker import extract


def evaluate(data,manifest_path,out,workers=3):
    if os.getpid() == 1:
        raise RuntimeError('Run this evaluator under docker --init; the production PDF child requires a supervising parent')
    if not 1<=workers<=4:raise ValueError('Use one to four bounded extraction workers')
    manifest,metadata=load_frozen(data,manifest_path)
    out.mkdir(parents=True,exist_ok=True)
    prediction_path=out/'predictions.jsonl'
    if prediction_path.exists() and prediction_path.stat().st_size:
        raise RuntimeError('Refusing to overwrite an existing run; choose a new output directory')
    source_files=['backend/reconcile/invoice_parser.py','backend/reconcile/document_text.py',
        'backend/reconcile/gst_parser.py','backend/reconcile/paddle_text.py',
        'backend/reconcile/ocr_models.py','backend/reconcile/document_types.py',
        'backend/reconcile/ingest.py','backend/reconcile/source_quality.py','backend/reconcile/tax_validation.py',
        'backend/reconcile/worker.py','ml/indian_gst_dataset.py','ml/indian_gst_metrics.py','ml/evaluate_indian_gst.py']
    frozen={'started_at':datetime.now(timezone.utc).isoformat(),
        'dataset_manifest_sha256':digest(manifest_path.read_bytes()),'metric_version':VERSION,
        'expected_documents':261,'source_sha256':{p:digest((ROOT/p).read_bytes()) for p in source_files},
        'execution':{'extraction_workers':workers,'tesseract_timeout_seconds':30,
            'pdf_child_cpu_seconds':100,'pdf_child_wall_seconds':150,
            'ocr_engine':os.getenv('OCR_ENGINE','tesseract'),'ocr_profile':os.getenv('OCR_PROFILE'),
            'ocr_child_omp_thread_limit':1,
            'shared_host':True,'latency_benchmark':False},
        'python':platform.python_version(),'tesseract':subprocess.run(['tesseract','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0],
        'packages':{name:version(name) for name in ['pytesseract','rapidocr','onnxruntime','opencv-python-headless','pdfplumber','pypdfium2','reportlab','pillow','scipy']},
        'label_policy':'Unmodified publisher JSON. Decimal comparisons exact. No label fitting or test-time training.',
        'pdf_wrapper':'Original image embedded in a neutral PDF at 200 DPI without deliberate resampling or augmentation; actual application OCR renders at 200 DPI.',
        'prediction_input':'PDF bytes only; source IDs, metadata, gold and filenames never passed to extractor',
        'line_alignment':'Hungarian description-only similarity >= 0.65; row correctness still requires exact normalized description and numeric fields. No price/quantity alignment.'}
    (out/'run-start.json').write_text(json.dumps(frozen,indent=2))

    def one(entry):
        started=time.perf_counter();error=None;prediction={'header':{},'lines':[],'warnings':[]};page_methods=[];pdf_hash=None
        try:
            raw=(data/entry['image_file']).read_bytes();pdf=image_pdf(raw);pdf_hash=digest(pdf)
            result=extract(pdf,lambda event:None)
            prediction=result['fields'];page_methods=[p['method'] for p in result['pages']]
        except Exception as exception:
            error=getattr(exception,'code',type(exception).__name__)
        # Only now access the expected record for scoring.
        gold=labels(metadata[entry['config']][entry['id']])
        return {'key':entry['key'],'config':entry['config'],'split':entry['split'],'layout':entry['layout'],
            'quality':entry['quality'],'script':entry.get('script'),'attack':entry.get('attack'),
            'image_sha256':entry['image_sha256'],'pdf_sha256':pdf_hash,'gold_sha256':entry['gold_sha256'],
            'seconds':time.perf_counter()-started,'page_methods':page_methods,
            'technical_error':error,'prediction':prediction,'gold':gold}

    records=[]
    with prediction_path.open('w') as stream, ThreadPoolExecutor(max_workers=workers) as pool:
        jobs={pool.submit(one,entry):entry for entry in manifest['records']}
        for future in as_completed(jobs):
            record=future.result();records.append(record)
            stream.write(json.dumps(record,default=str,ensure_ascii=False)+'\n');stream.flush()
            if len(records)%10==0 or len(records)==261:
                print(f'Evaluated {len(records)} / 261 — {record["config"]}, {record["quality"]}',flush=True)
    if len(records)!=261 or len({r['key'] for r in records})!=261:
        raise RuntimeError('Missing or duplicate evaluation records')
    records.sort(key=lambda r:r['key'])
    main=[r for r in records if r['config']=='synthetic']
    report={'run':frozen,'finished_at':datetime.now(timezone.utc).isoformat(),
        'dataset':{k:manifest[k] for k in ['dataset','revision','license','attribution','selection','hf_split_note','synthetic_split_column_counts']},
        'primary_official_test':summarize(main),
        'robustness':{config:summarize([r for r in records if r['config']==config]) for config in ['injection','regional']},
        'primary_by_quality':{q:summarize([r for r in main if r['quality']==q]) for q in sorted({r['quality'] for r in main})},
        'primary_by_layout':{q:summarize([r for r in main if r['layout']==q]) for q in sorted({r['layout'] for r in main})},
        'technical_errors':dict(Counter(r['technical_error'] for r in records if r['technical_error'])),
        'core_target_map':{k:list(v) for k,v in CORE.items()},
        'additional_target_map':{k:list(v) for k,v in EXTRA.items()},
        'row_core_target_map':ROW_CORE,'row_additional_target_map':ROW_EXTRA,
        'unlabelled_application_fields':['currency','po_reference','scalar tax_total and combined tax_rate'],
        'additional_targets_without_found_output':{
            'headers':[k for k in EXTRA if not any(r['prediction'].get('header',{}).get(k,{}).get('status')=='found' for r in records)],
            'rows':[k for k in ROW_EXTRA if not any(line.get(k,{}).get('status')=='found' for r in records for line in r['prediction'].get('lines',[]))]},
        'unsupported_scope_profile':{'regional_documents':40,
            'main_documents_with_mixed_line_gst_rates':sum(len({str(l['gst_rate']) for l in r['gold']['line_items'] if l.get('gst_rate') is not None})>1 for r in main),
            'main_invoice_unit_counts':dict(Counter(l.get('unit') for r in main for l in r['gold']['line_items']))},
        'limitations':manifest['limitations']+[
            'This is an extraction evaluation, not accept/reject accuracy or invoice automation',
            'Original parser and source-quality policy are fixed before scoring; no fine-tuning or test-guided fixes',
            'Scalar aggregate tax is not manufactured from separate components as an extraction target',
            'Publisher zero/null fields may need visibility audit; strict source labels retained',
            'Exact full-row comparison targets NET taxable_value, not gross total; unsupported row fields are reported separately',
            'Raw and source-verified tracks measure the cost of abstention; verified coverage is not automation',
            'Auxiliary injection/regional scores do not mix into primary English synthetic test metrics'],
        'full_invoice_approval_accuracy':None,'retrieval_accuracy':None,'new_training_performed':False}
    if frozen['execution']['ocr_engine']=='paddle':
        from reconcile.ocr_models import assets
        report['ocr_weights']={task:{'file':name,'sha256':sha} for task,(name,sha) in assets(os.getenv('OCR_PROFILE','server')).items()}
        report['limitations'] += ['Test was already inspected in baseline-v2; this is a disclosed re-score after training-split parser development and validation-only model selection, not a fresh blind test',
            'PP-OCRv5 English mobile does not establish Hindi/Kannada support; regional suite remains separate',
            'Deskewed logical coordinates are separate from original-source evidence rectangles']
    (out/'metrics.json').write_text(json.dumps(report,indent=2,default=str,ensure_ascii=False))
    compact=report['primary_official_test']
    print('INDIAN_GST_RESULT '+json.dumps({'documents':len(main),'technical_failures':compact['raw_extracted']['technical_failures'],
        'raw_core_headers':compact['raw_extracted']['core_header_micro'],
        'verified_core_headers':compact['source_verified']['core_header_micro'],
        'raw_complete_rows':compact['raw_extracted']['complete_core_rows']}),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=DEFAULT_DATA)
    p.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--workers',type=int,default=3)
    a=p.parse_args();evaluate(a.data,a.manifest,a.output,a.workers)
