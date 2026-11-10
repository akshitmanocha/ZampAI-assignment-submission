"""Pinned MiniLM embeddings on CPU. Similarity retrieves; it never approves."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import numpy as np
from reconcile.settings import model_dir

MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
VERSION = 'minilm-l6-onnx-meanpool-v1:' + REVISION


@lru_cache(maxsize=2)
def encoder(directory):
    import onnxruntime as ort
    ort.disable_telemetry_events()
    from tokenizers import Tokenizer
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['revision'] != REVISION or manifest['model'] != MODEL:
        raise RuntimeError('MATCHER_ARTIFACT_MISMATCH')
    from reconcile.model_setup import EXPECTED
    if manifest['sha256'] != EXPECTED:
        raise RuntimeError('MATCHER_ARTIFACT_MISMATCH')
    for name, digest in manifest['sha256'].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('MATCHER_ARTIFACT_MISMATCH')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    model = ort.InferenceSession(str(directory / 'model.onnx'), sess_options=options,
                                providers=['CPUExecutionProvider'])
    tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding(pad_id=0, pad_token='[PAD]')
    return tokenizer, model


def embed(texts):
    if not texts:
        return np.empty((0, 384), dtype=np.float32)
    tokenizer, model = encoder(str(model_dir()))
    tokens = tokenizer.encode_batch(texts)
    values = {
        'input_ids': np.array([t.ids for t in tokens], dtype=np.int64),
        'attention_mask': np.array([t.attention_mask for t in tokens], dtype=np.int64),
        'token_type_ids': np.array([t.type_ids for t in tokens], dtype=np.int64),
    }
    inputs = {i.name: values[i.name] for i in model.get_inputs()}
    output = model.run(None, inputs)[0]
    if output.ndim == 3:
        mask = values['attention_mask'][..., None]
        output = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
    output = output / np.maximum(np.linalg.norm(output, axis=1, keepdims=True), 1e-12)
    return output.astype(np.float32)


def retrieve(document, company, top_k=5):
    """Vendor-filter first; include closed history only as ineligible context.

    Descriptions/SKUs/attributes enter embeddings; prices, quantities, balances,
    labels and filenames do not. No unvalidated score threshold enables matches.
    """
    from reconcile.business_validation import key, attributes
    vendors = [v for v in company['vendors'] if key(v['legal_name']) == key(document.get('vendor_name'))]
    if len(vendors) != 1:
        return {'version': VERSION, 'lines': [], 'reason': 'Resolve the supplier before retrieving products.'}
    records = []
    for po in company['purchase_orders']:
        if po['vendor_id'] != vendors[0]['id']:
            continue
        for line in po['lines']:
            records.append({**line, 'po_line_id': line['id'], 'po_id': po['id'],
                            'po_number': po['number'], 'po_status': po['status'],
                            'eligible': po['status'] == 'open' and po['currency'] == document.get('currency')
                            and (not document.get('po_reference') or key(po['number']) == key(document['po_reference']))})
    lines = document.get('lines', [])
    if not records or not lines:
        return {'version': VERSION, 'lines': [], 'reason': 'No supplier-scoped order lines available.'}
    catalog = embed([r['sku'] + ' ' + r['description'] for r in records])
    queries = embed([l.get('description') or '' for l in lines])
    result = []
    for number, (line, scores) in enumerate(zip(lines, queries @ catalog.T), 1):
        attrs = attributes(line.get('description'))
        candidates = []
        # Eligible candidates and historical context are ranked separately.
        for i in sorted(range(len(records)), key=lambda i: (not records[i]['eligible'], -float(scores[i]), records[i]['id'])):
            r = records[i]
            conflicts = [name for name in ['material', 'size'] if attrs[name] and r.get(name)
                         and key(attrs[name]) != key(r[name])]
            candidates.append({**r, 'similarity': round(float(scores[i]), 6),
                               'conflicts': conflicts, 'authorizes_invoice': False})
        result.append({'source_line': number,
                       'candidates': [c for c in candidates if c['eligible']][:top_k],
                       'history': [c for c in candidates if not c['eligible']][:top_k],
                       'reason': 'Similarity is a ranking score, not a correctness probability.'})
    return {'version': VERSION, 'lines': result, 'automatic_semantic_matching': False}
