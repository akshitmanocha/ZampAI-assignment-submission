"""Cache label-free OCR pages so parser changes do not rerun the models."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import time
os.environ.setdefault('OMP_THREAD_LIMIT','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
from PIL import Image
from indian_gst_dataset import DEFAULT_DATA,ROOT,digest
from reconcile.document_types import PageText,Word


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',choices=['paddle','paddle-mobile','tesseract'],required=True)
    parser.add_argument('--purpose',choices=['parser_development','model_selection','calibration','qualification'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads((ROOT/'ml/data/indian-gst-ocr-v1/manifest.json').read_text())
    selected=[r for r in manifest['records'] if (r['id'] in manifest['qualification_ids'] if args.purpose=='qualification' else r['purpose']==args.purpose)]
    args.output.mkdir(parents=True,exist_ok=True)
    for record in selected:
        path=args.output/(record['id']+'.json')
        if path.exists():continue
        raw=(DEFAULT_DATA/record['image_file']).read_bytes()
        if digest(raw)!=record['image_sha256']:raise RuntimeError('Image changed')
        image=Image.open(DEFAULT_DATA/record['image_file']).convert('RGB')
        t=time.perf_counter();error=None;words=()
        try:
            if args.engine.startswith('paddle'):
                from reconcile.paddle_text import recognize
                words=recognize(image,image.width,image.height,'/workspace/reconcile-artifacts/ppocr-v5',
                    profile='mobile' if args.engine=='paddle-mobile' else 'server')
            else:
                import pytesseract
                result=pytesseract.image_to_data(image,config='--psm 3',output_type=pytesseract.Output.DICT,timeout=30)
                words=tuple(Word(s.strip(),(float(result['left'][i]),float(result['top'][i]),float(result['left'][i]+result['width'][i]),float(result['top'][i]+result['height'][i])),float(result['conf'][i])) for i,s in enumerate(result['text']) if s.strip())
        except Exception as exception:error=type(exception).__name__
        page=PageText(1,'ocr',image.width,image.height,words)
        image.close()
        path.write_text(json.dumps({'id':record['id'],'image_sha256':digest(raw),'engine':args.engine,
            'seconds':time.perf_counter()-t,'error':error,'page':asdict(page)},ensure_ascii=False))
        print(record['id'],args.engine,'words',len(words),'error',error,flush=True)


if __name__=='__main__':main()
