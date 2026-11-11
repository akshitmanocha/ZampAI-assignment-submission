"""Score complete, predeclared development suites and a parser/OCR ablation."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
from indian_gst_dataset import ROOT,DEFAULT_DATA,labels,digest
from indian_gst_metrics import CORE,at,equal,summarize
from reconcile.document_types import Word,PageText
from reconcile.invoice_parser import parse_invoice
from reconcile.source_quality import assess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',type=Path,default=ROOT.parent/'reconcile-artifacts/ocr-development')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest_path=ROOT/'ml/data/indian-gst-ocr-v1/manifest.json'
    manifest=json.loads(manifest_path.read_text())
    raw=(DEFAULT_DATA/'publisher-metadata/synthetic.jsonl').read_bytes()
    assert digest(raw)==manifest['source_metadata_sha256']
    metadata={r['id']:r for r in [json.loads(l) for l in raw.splitlines()]}
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'metrics.json').exists():raise RuntimeError('Choose a fresh output directory')
    baseline=subprocess.check_output(['git','show','12a8dd4:backend/reconcile/invoice_parser.py'],cwd=ROOT)
    original=args.output/'original_parser.py';original.write_bytes(baseline)
    spec=importlib.util.spec_from_file_location('frozen_original_parser',original)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    source_paths=['backend/reconcile/invoice_parser.py','backend/reconcile/gst_parser.py',
        'backend/reconcile/paddle_text.py','backend/reconcile/ocr_models.py','backend/reconcile/source_quality.py',
        'backend/reconcile/document_types.py','ml/indian_gst_metrics.py']
    frozen={'frozen_before_scoring_at':datetime.now(timezone.utc).isoformat(),
        'development_manifest_sha256':digest(manifest_path.read_bytes()),
        'source_sha256':{p:digest((ROOT/p).read_bytes()) for p in source_paths},
        'original_parser_sha256':digest(baseline),'original_commit':'12a8dd4',
        'rule':'All requested records must be present; no failure/example filtering. Gold joined after parsing.',
        'cache_coordinate_conversion':'Source pixel coordinates mapped to PDF points at 200 DPI before parsing, matching the production neutral PDF wrapper. No OCR value edits.',
        'parser_development':'24 source training images; validation model choice is separate; calibration is not parser fitting.'}
    (args.output/'run-start.json').write_text(json.dumps(frozen,indent=2))
    def cases(engine,purpose,parse):
        selected=[r for r in manifest['records'] if (r['id'] in manifest['qualification_ids'] if purpose=='qualification' else r['purpose']==purpose)]
        result=[]
        for record in selected:
            path=args.cache/engine/(record['id']+'.json')
            if not path.exists():raise RuntimeError(f'Incomplete {engine}/{purpose}: {record["id"]}')
            cached=json.loads(path.read_text())
            if cached['image_sha256']!=record['image_sha256']:raise RuntimeError('Cached input hash mismatch')
            if digest(metadata[record['id']]['label'].encode())!=record['gold_sha256']:raise RuntimeError('Gold changed')
            p=cached['page'];scale=72/200
            words=tuple(Word(w['text'],tuple(c*scale for c in w['bbox']),w.get('confidence'),
                tuple(c*scale for c in w['source_bbox']) if w.get('source_bbox') else None) for w in p['words'])
            page=PageText(p['page'],p['method'],p['width']*scale,p['height']*scale,words)
            prediction=assess(parse([page]),[page])
            result.append({'id':record['id'],'layout':record['layout'],'quality':record['quality'],
                'technical_error':cached['error'],'prediction':prediction,'gold':labels(metadata[record['id']]),
                'cache_sha256':digest(path.read_bytes()),'ocr_seconds':cached['seconds']})
        return result
    report={'run':frozen,'training_debug':{},'model_selection':{},'qualification':{},'ablation':{}}
    saved=[]
    for engine in ['paddle-mobile','tesseract']:
        for purpose in ['parser_development','model_selection']:
            records=cases(engine,purpose,parse_invoice)
            key='training_debug' if purpose=='parser_development' else purpose
            report[key][engine]=summarize(records)
            saved.extend({'engine':engine,'purpose':purpose,**r} for r in records)
        old=cases(engine,'model_selection',module.parse_invoice)
        report['ablation'][engine+'_original_parser']=summarize(old)['raw_extracted']
        report['ablation'][engine+'_gst_parser']=report['model_selection'][engine]['raw_extracted']
    for engine in ['paddle-v2','paddle-mobile','tesseract']:
        report['qualification'][engine]=summarize(cases(engine,'qualification',parse_invoice))
    calibration=cases('paddle-mobile','calibration',parse_invoice)
    report['calibration']=summarize(calibration)
    saved.extend({'engine':'paddle-mobile','purpose':'calibration',**r} for r in calibration)
    curve=[]
    denominator=len(calibration)*len(CORE)
    for threshold in [60,70,80,85,90,95,98,99,99.5,99.9,100]:
        proposed=correct=0
        for record in calibration:
            for field,path in CORE.items():
                cell=record['prediction']['header'].get(field,{})
                if cell.get('status')=='found' and cell.get('minimum_ocr_score',-1)>=threshold:
                    proposed+=1;correct+=bool(equal(field,cell.get('value'),at(record['gold'],path)))
        curve.append({'minimum_ocr_score':threshold,'proposed':proposed,'correct':correct,
            'errors':proposed-correct,'precision':correct/proposed if proposed else None,
            'label_coverage':proposed/denominator})
    report['calibration_threshold_diagnostic']=curve
    report['threshold_policy']='Diagnostic only. Existing minimum-60 gate remains a quality heuristic; confidence is not a correctness probability or invoice automation.'
    report['selection']='PP-OCRv5 English mobile chosen for validation extraction quality, local CPU compatibility and ~3.1M stored model values; GPU VLM qualification reported separately.'
    report['limitations']=['Validation is development evidence, not production accuracy',
        'No new training/fine-tuning; parser developed on 24 training images',
        'Source labels not independently audited; no linked PO/approval truth',
        'No ambiguous date guessing to improve recall','Timing includes shared-host contention and first model load']
    (args.output/'metrics.json').write_text(json.dumps(report,indent=2,default=str))
    with (args.output/'predictions.jsonl').open('w') as stream:
        for record in saved:stream.write(json.dumps(record,default=str,ensure_ascii=False)+'\n')
    for engine,data in report['model_selection'].items():
        raw=data['raw_extracted'];print(engine,raw['documents'],raw['core_header_micro'],raw['complete_core_rows'])


if __name__=='__main__':main()
