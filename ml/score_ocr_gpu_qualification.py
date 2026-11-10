"""Compare all twelve fixed qualification records; retain failures/truncations."""
import argparse
import json
from pathlib import Path
from indian_gst_dataset import ROOT,DEFAULT_DATA,labels,digest
from indian_gst_metrics import summarize
from reconcile.invoice_parser import parse_invoice
from vision_ocr_pages import proposed_page,require_review,omit_images


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest_path=ROOT/'ml/data/indian-gst-ocr-v1/manifest.json'
    manifest=json.loads(manifest_path.read_text())
    expected={r['id']:r for r in manifest['records'] if r['id'] in manifest['qualification_ids']}
    raw_meta=(DEFAULT_DATA/'publisher-metadata/synthetic.jsonl').read_bytes()
    assert digest(raw_meta)==manifest['source_metadata_sha256']
    metadata={r['id']:r for r in [json.loads(l) for l in raw_meta.splitlines()]}
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'metrics.json').exists():raise RuntimeError('Choose a fresh GPU score directory')
    report={'qualification_documents':12,'source_manifest_sha256':digest(manifest_path.read_bytes()),'engines':{},
        'adapter_sha256':digest((ROOT/'ml/vision_ocr_pages.py').read_bytes()),
        'parser_sha256':digest((ROOT/'backend/reconcile/invoice_parser.py').read_bytes()),
        'gst_parser_sha256':digest((ROOT/'backend/reconcile/gst_parser.py').read_bytes()),
        'scope':'Exploratory native VLM adapters, not the vendor official layout pipeline or intrinsic model leaderboard. Proposed geometry is unverified; every VLM reading requires source review.'}
    for engine in ['granite-v3','paddle-vl-v3']:
        source=args.input/engine;info=json.loads((source/'model.json').read_text())
        if info['manifest_sha256']!=report['source_manifest_sha256']:raise RuntimeError('Wrong GPU input manifest')
        assert info['actual_parameters']<1_000_000_000
        raw=(source/'predictions.jsonl').read_bytes()
        predictions=[json.loads(line) for line in raw.splitlines()]
        if len(predictions)!=12 or {r['id'] for r in predictions}!=set(expected):raise RuntimeError('Incomplete GPU qualification')
        cases=[]
        for r in predictions:
            if r['image_sha256']!=expected[r['id']]['image_sha256']:raise RuntimeError('GPU input hash mismatch')
            prediction=require_review(parse_invoice([proposed_page(r)])) if r.get('image_size') else {'header':{},'lines':[]}
            gold=labels(metadata[r['id']])
            cases.append({'id':r['id'],'prediction':prediction,'gold':gold,'technical_error':r.get('error')})
        score=summarize(cases)
        report['engines'][engine]={'model':info,'score':score,
            'incomplete_generations':sum(bool(r.get('stopped_before_eos',True)) for r in predictions),
            'mean_seconds':sum(r['seconds'] for r in predictions)/12,
            'original_prediction_jsonl_sha256':digest(raw),
            'original_export_path':str(source),'export_policy':'Embedded copies of original images omitted; OCR text, table data and proposed coordinates unchanged.'}
        destination=args.output/engine;destination.mkdir()
        (destination/'model.json').write_text(json.dumps(info,indent=2))
        with (destination/'predictions.jsonl').open('w') as stream:
            for r in predictions:stream.write(json.dumps(omit_images(r),ensure_ascii=False)+'\n')
        with (destination/'extractions.jsonl').open('w') as stream:
            for r in cases:stream.write(json.dumps(r,default=str,ensure_ascii=False)+'\n')
        r=score['raw_extracted'];print(engine,r['core_header_micro'],r['complete_core_rows'])
    (args.output/'metrics.json').write_text(json.dumps(report,indent=2,default=str))


if __name__=='__main__':main()
