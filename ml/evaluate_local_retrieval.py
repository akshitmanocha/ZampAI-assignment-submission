"""Verify the CPU ONNX implementation against the saved GPU embedding diagnostic.

This reuses an inspected 36-query set. It tests implementation parity, not fresh
model generalisation or calibrated invoice automation.
"""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from reconcile.retrieval import embed,VERSION


def main():
    catalog=json.loads((ROOT/'ml/data/pilot/catalog.json').read_text())
    reference=[json.loads(s) for s in (ROOT/'ml/results/retrieval/predictions.jsonl').read_text().splitlines()]
    corpus=embed([p['descriptions'][0] for p in catalog])
    scores=embed([q['description'] for q in reference])@corpus.T
    predictions=[]
    max_delta=0.0
    for query,cosines in zip(reference,scores):
        indices=np.argsort(-cosines,kind='stable')[:5]
        ids=[catalog[i]['product_id'] for i in indices]
        for id,old in zip(query['embedding_top5'],query['embedding_cosines']):
            index=next(i for i,p in enumerate(catalog) if p['product_id']==id)
            max_delta=max(max_delta,abs(float(cosines[index])-old))
        predictions.append({'description':query['description'],'correct_id':query['correct_id'],'top5':ids})
    report={'scope':'Previously inspected synthetic retrieval diagnostic; CPU/GPU implementation parity only',
        'runtime_matcher':VERSION,'queries':len(reference),'catalog':len(catalog),
        'recall':{str(k):sum(p['correct_id'] in p['top5'][:k] for p in predictions)/len(predictions) for k in [1,3,5]},
        'same_top1_as_gpu':sum(p['top5'][0]==q['embedding_top5'][0] for p,q in zip(predictions,reference)),
        'max_absolute_reference_cosine_difference':max_delta,
        'model_artifact_manifest':json.loads((ROOT/'ml/artifacts/minilm/manifest.json').read_text()),
        'source_sha256':hashlib.sha256((ROOT/'backend/reconcile/retrieval.py').read_bytes()).hexdigest(),
        'automatic_semantic_matching':False,'independent_final_test':False}
    out=ROOT/'ml/results/local-application';out.mkdir(parents=True,exist_ok=True)
    (out/'minilm-parity.json').write_text(json.dumps(report,indent=2))
    (out/'minilm-predictions.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in predictions))
    print(json.dumps(report,indent=2))
    if report['same_top1_as_gpu']!=len(reference) or max_delta>0.0001:raise SystemExit(1)

if __name__=='__main__':main()
