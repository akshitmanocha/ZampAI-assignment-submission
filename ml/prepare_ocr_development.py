"""Freeze source-split development sets before comparing sub-billion OCR models."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from indian_gst_dataset import DEFAULT_DATA, DEFAULT_MANIFEST, ROOT, digest, fetch

OUT = ROOT / 'ml/data/indian-gst-ocr-v1/manifest.json'


def prepare():
    original = json.loads(DEFAULT_MANIFEST.read_text())
    raw = (DEFAULT_DATA/'publisher-metadata/synthetic.jsonl').read_bytes()
    if digest(raw) != original['metadata_sha256']['synthetic']:
        raise RuntimeError('Publisher metadata changed')
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    selected = []
    qualification = []
    for layout in ['classic', 'minimal', 'handwritten', 'thermal']:
        for quality in ['clean', 'scan', 'photo']:
            group = sorted([r for r in rows if r['layout']==layout and r['level']==quality], key=lambda r:r['id'])
            training = [r for r in group if r['split']=='train'][:2]
            validation = [r for r in group if r['split']=='val'][:5]
            if len(training)!=2 or len(validation)!=5:
                raise RuntimeError('Incomplete predeclared strata')
            qualification.append(validation[0]['id'])
            selected += [(r,'parser_development') for r in training]
            selected += [(r,'model_selection') for r in validation]
    chosen={r['id'] for r,_ in selected}
    selected += [(r,'calibration') for r in rows if r['split']=='val' and r['id'] not in chosen]
    if Counter(s for _,s in selected)!={'parser_development':24,'model_selection':60,'calibration':130}:
        raise RuntimeError('Development split counts changed')
    def one(pair):
        r,purpose=pair
        path=DEFAULT_DATA/'development-images'/Path(r['file_name']).name
        path.parent.mkdir(parents=True,exist_ok=True)
        image=path.read_bytes() if path.exists() else fetch('synthetic/'+r['file_name'])
        if not path.exists():path.write_bytes(image)
        return {'id':r['id'],'source_path':'synthetic/'+r['file_name'],'source_split':r['split'],
            'purpose':purpose,'layout':r['layout'],'quality':r['level'],
            'image_file':str(path.relative_to(DEFAULT_DATA)),'image_sha256':digest(image),
            'gold_sha256':digest(r['label'].encode())}
    with ThreadPoolExecutor(max_workers=6) as pool:records=list(pool.map(one,selected))
    manifest={'dataset':original['dataset'],'revision':original['revision'],'license':original['license'],
        'source_metadata_sha256':digest(raw),'selection':'First two train and first five validation IDs per layout/quality stratum; remaining validation for calibration.',
        'counts':dict(Counter(r['purpose'] for r in records)),'qualification_ids':qualification,
        'records':sorted(records,key=lambda r:r['id']),
        'policy':['No source test record in development/model selection/calibration',
            'Qualification uses one model-selection image per stratum, identical for all candidates',
            'Publisher labels unchanged and never passed to OCR models',
            'Previously scored test is reused only after freezing the new pipeline; report reuse explicitly',
            'Model selection may inspect its 60 validation examples; calibration is separate and not used for parser fitting']}
    serialized=json.dumps(manifest,indent=2)+'\n'
    OUT.parent.mkdir(parents=True,exist_ok=True)
    if OUT.exists() and OUT.read_text()!=serialized:raise RuntimeError('Refusing to change frozen development selection')
    OUT.write_text(serialized)
    print('Frozen development selection:',manifest['counts'],digest(serialized.encode()))


if __name__=='__main__':prepare()
