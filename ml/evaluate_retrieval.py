"""Embedding retrieval and cross-encoder reranking diagnostic.

Uses the already-inspected pilot test families; not a new blind benchmark.
Catalog IDs supply evaluation truth only and are never model inputs.
"""
from pathlib import Path
import json
import time
import numpy as np
from huggingface_hub import HfApi
from sentence_transformers import SentenceTransformer
import torch
from transformers import AutoTokenizer,AutoModelForSequenceClassification


def run(data,model_dir,out):
    out.mkdir(parents=True,exist_ok=True)
    catalog=json.loads((data/'catalog.json').read_text())
    queries=[{'description':v,'correct_id':p['product_id'],'family':p['family']} for p in catalog if p['split']=='test' for v in p['descriptions'][1:]]
    name='sentence-transformers/all-MiniLM-L6-v2';revision=HfApi().model_info(name).sha
    encoder=SentenceTransformer(name,revision=revision,device='cuda:0')
    corpus=encoder.encode([p['descriptions'][0] for p in catalog],normalize_embeddings=True,convert_to_numpy=True)
    start=time.perf_counter()
    vectors=encoder.encode([q['description'] for q in queries],normalize_embeddings=True,convert_to_numpy=True)
    scores=vectors@corpus.T
    orders=np.argsort(-scores,axis=1,kind='stable')
    retrieval_seconds=time.perf_counter()-start
    tokenizer=AutoTokenizer.from_pretrained(model_dir)
    matcher=AutoModelForSequenceClassification.from_pretrained(model_dir).to('cuda:0').eval()
    predictions=[]
    with torch.no_grad():
        for q,order,cosines in zip(queries,orders,scores):
            top=order[:5]
            inputs=tokenizer([q['description']]*len(top),[catalog[i]['descriptions'][0] for i in top],padding=True,truncation=True,max_length=128,return_tensors='pt').to('cuda:0')
            logits=matcher(**inputs).logits.reshape(-1).cpu().numpy()
            reranked=top[np.argsort(-logits,kind='stable')]
            predictions.append({**q,'embedding_top5':[catalog[i]['product_id'] for i in top],'reranked_top5':[catalog[i]['product_id'] for i in reranked],'embedding_cosines':[float(cosines[i]) for i in top]})
    result={'query_count':len(queries),'candidate_products':len(catalog),'test_families':sorted({q['family'] for q in queries}),'embedding_model':name,'embedding_revision':revision,'cross_encoder':'selected pilot E1 checkpoint','embedding_recall':{str(k):sum(p['correct_id'] in p['embedding_top5'][:k] for p in predictions)/len(predictions) for k in [1,3,5]},'reranked_recall':{str(k):sum(p['correct_id'] in p['reranked_top5'][:k] for p in predictions)/len(predictions) for k in [1,3,5]},'embedding_query_batch_s':retrieval_seconds,'limitations':['36 simple queries, only three families, 80 fictional catalog items','Reuses already-inspected pilot test families; diagnostic, not a fresh blind test','Only matchable queries; no no-match or incomplete-catalog accuracy measured','No human review performed and no end-to-end invoice accuracy measured','Cosines/logits are not calibrated confidence probabilities','Vendor/current-PO filtering is required in the real app before retrieval']}
    (out/'metrics.json').write_text(json.dumps(result,indent=2))
    (out/'predictions.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in predictions))
    print('RETRIEVAL_JSON '+json.dumps(result),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('ml/data/pilot'));p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('ml/results/retrieval'));a=p.parse_args();run(a.data,a.model_dir,a.output)
