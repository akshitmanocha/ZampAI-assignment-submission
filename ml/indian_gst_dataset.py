"""Pinned external Indian GST evaluation corpus; never imports decision code.

Downloads original images and publisher metadata without executing dataset code.
Expected answers stay exclusively in the offline evaluator, not PDF/model inputs.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import time
import urllib.request

DATASET = 'Divya52/indian-gst-invoices'
REVISION = 'fece40b9a96ac3949934fc05c714853a5283d730'
LICENSE = 'CC BY 4.0'
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT.parent / 'reconcile-artifacts/indian-gst-v1'
DEFAULT_MANIFEST = ROOT / 'ml/data/indian-gst-v1/manifest.json'
SOURCE_URL = f'https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def fetch(path, max_bytes=20*1024*1024):
    # Repository paths are metadata, not local path or URL instructions.
    relative = PurePosixPath(path)
    if relative.is_absolute() or '..' in relative.parts or '\\' in path:
        raise ValueError('Unsafe source path')
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(SOURCE_URL + '/' + path, timeout=40) as response:
                raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise RuntimeError('Source object exceeds size limit')
            return raw
        except Exception as error:
            last = error
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError('Public dataset download failed: ' + path) from last


def labels(row):
    return json.loads(row['label'], parse_float=Decimal, parse_int=Decimal)


def selected_records(metadata):
    result = []
    for config, rows in metadata.items():
        for row in rows:
            if config == 'synthetic' and row['split'] != 'test':
                continue
            result.append({'key':config + '/' + row['id'], 'config':config,
                'split':'official_test' if config == 'synthetic' else 'robustness',
                'source_split':row.get('split'), 'id':row['id'], 'source_path':config + '/' + row['file_name'],
                'layout':row.get('layout'), 'quality':row.get('level'), 'script':row.get('script'),
                'attack':row.get('attack'), 'attack_style':row.get('attack_style'),
                'seed':row.get('seed'), 'gold_sha256':digest(row['label'].encode()),
                'record_sha256':digest(canonical(row))})
    if len(result) != 261 or Counter(r['config'] for r in result) != {'synthetic':197,'injection':24,'regional':40}:
        raise RuntimeError('Pinned source selection is incomplete or changed')
    if len({r['key'] for r in result}) != len(result):
        raise RuntimeError('Repeated source identity')
    return sorted(result, key=lambda r:r['key'])


def prepare(data=DEFAULT_DATA, manifest_path=DEFAULT_MANIFEST):
    data.mkdir(parents=True, exist_ok=True)
    meta_dir = data / 'publisher-metadata'
    meta_dir.mkdir(exist_ok=True)
    metadata, metadata_hashes = {}, {}
    for config in ['synthetic','injection','regional']:
        path = meta_dir / (config + '.jsonl')
        raw = fetch(config + '/metadata.jsonl')
        if path.exists() and path.read_bytes() != raw:
            raise RuntimeError('Refusing to replace different pinned metadata')
        path.write_bytes(raw)
        metadata[config] = [json.loads(line) for line in raw.splitlines() if line.strip()]
        metadata_hashes[config] = digest(raw)
    if len(metadata['synthetic']) != 2000:
        raise RuntimeError('Unexpected main corpus size')
    records = selected_records(metadata)
    image_dir = data / 'images'
    image_dir.mkdir(exist_ok=True)

    def download(record):
        path = image_dir / (record['config'] + '--' + record['id'] + PurePosixPath(record['source_path']).suffix.lower())
        raw = path.read_bytes() if path.exists() else fetch(record['source_path'])
        if not path.exists():
            temporary = path.with_suffix(path.suffix + '.partial')
            temporary.write_bytes(raw)
            temporary.replace(path)
        return {**record,'image_file':str(path.relative_to(data)),'image_sha256':digest(raw),'image_bytes':len(raw)}

    with ThreadPoolExecutor(max_workers=6) as pool:
        finished = []
        for record in pool.map(download, records):
            finished.append(record)
            if len(finished) % 25 == 0 or len(finished) == len(records):
                print(f'Prepared {len(finished)} / {len(records)} Indian GST images', flush=True)
    # Validation images selected by layout/quality alone for source visibility audit.
    # They never join the scored official test set.
    audit_rows = []
    for layout in ['classic','minimal','handwritten','thermal']:
        for quality in ['clean','scan','photo']:
            row = next(r for r in metadata['synthetic'] if r['split']=='val' and r['layout']==layout and r['level']==quality)
            audit_rows.append(row)
    audit_images = []
    for row in audit_rows:
        path = data / 'audit-images' / Path(row['file_name']).name
        path.parent.mkdir(exist_ok=True)
        raw = path.read_bytes() if path.exists() else fetch('synthetic/' + row['file_name'])
        if not path.exists():path.write_bytes(raw)
        audit_images.append({'id':row['id'],'layout':row['layout'],'quality':row['level'],
            'image_file':str(path.relative_to(data)),'image_sha256':digest(raw),'gold_sha256':digest(row['label'].encode())})
    manifest = {'dataset':DATASET,'revision':REVISION,'license':LICENSE,
        'attribution':'Divya52, Indian GST invoices (synthetic), Hugging Face; publisher-generated labels retained unchanged.',
        'purpose':'Primary external invoice OCR/extraction evaluation. Not product matching training or invoice approval ground truth.',
        'publisher_rows':{k:len(v) for k,v in metadata.items()},
        'synthetic_split_column_counts':dict(Counter(r['split'] for r in metadata['synthetic'])),
        'selection':'All 197 synthetic rows whose split column is test; all 24 injection and 40 regional rows as separate robustness suites.',
        'hf_split_note':'The Hugging Face loader calls all rows train; source split column controls selection.',
        'metadata_sha256':metadata_hashes,'records':finished,'validation_audit_images':audit_images,
        'frozen_before_first_scoring':True,'fine_tuning_performed':False,
        'limitations':['Synthetic invoices, four source layouts and 25-product source catalog',
            'Publisher labels are not independently human audited by this project',
            'Invoice images alone provide no verified PO ledger, approval history, or same-product retrieval labels',
            'Regional Hindi/Kannada and some units/tax structures exceed current automatic application scope',
            'Some metadata/sample labels were inspected during dataset discovery; no model-output-guided selection or tuning',
            'No real-invoice population or future precision guarantee']}
    manifest_path.parent.mkdir(parents=True,exist_ok=True)
    serialized = json.dumps(manifest,indent=2,ensure_ascii=False) + '\n'
    if manifest_path.exists() and manifest_path.read_text() != serialized:
        raise RuntimeError('Refusing to rewrite frozen dataset manifest')
    manifest_path.write_text(serialized)
    print('Frozen dataset manifest SHA-256:',digest(serialized.encode()),flush=True)
    return manifest


def load_frozen(data, manifest_path):
    manifest = json.loads(manifest_path.read_text())
    if manifest['dataset'] != DATASET or manifest['revision'] != REVISION:
        raise RuntimeError('Unexpected dataset revision')
    metadata = {}
    for config, expected in manifest['metadata_sha256'].items():
        raw = (data/'publisher-metadata'/f'{config}.jsonl').read_bytes()
        if digest(raw) != expected:raise RuntimeError('Publisher metadata hash mismatch')
        metadata[config] = {r['id']:r for r in [json.loads(s) for s in raw.splitlines() if s.strip()]}
    expected = {r['key'] for r in selected_records({k:list(v.values()) for k,v in metadata.items()})}
    if {r['key'] for r in manifest['records']} != expected or len(manifest['records']) != 261:
        raise RuntimeError('Incomplete frozen suite')
    for record in manifest['records']:
        row = metadata[record['config']][record['id']]
        if digest(canonical(row)) != record['record_sha256'] or digest(row['label'].encode()) != record['gold_sha256']:
            raise RuntimeError('Record/gold hash mismatch')
        if digest((data/record['image_file']).read_bytes()) != record['image_sha256']:
            raise RuntimeError('Image hash mismatch')
    return manifest, metadata


def image_pdf(raw):
    """Neutral PDF wrapper; embeds source without deliberate resampling/augmentation."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    with Image.open(io.BytesIO(raw)) as image:
        width,height = image.size
        if width*height > 40_000_000:
            raise ValueError('Image pixel limit')
    buffer = io.BytesIO()
    w,h = width*72/200,height*72/200
    document = canvas.Canvas(buffer,pagesize=(w,h),invariant=1,pageCompression=1)
    document.setTitle('Invoice document')
    document.drawImage(ImageReader(io.BytesIO(raw)),0,0,width=w,height=h)
    document.save()
    return buffer.getvalue()


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=DEFAULT_DATA)
    p.add_argument('--manifest',type=Path,default=DEFAULT_MANIFEST)
    a=p.parse_args()
    prepare(a.data,a.manifest)
