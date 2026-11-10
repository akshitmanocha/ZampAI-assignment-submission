"""Run B0/B1/E1 on the frozen synthetic pair pilot; write measured results.

Run on Kaggle: python experiment.py --data data/pilot --output results/pilot
Requires torch, transformers, huggingface_hub, sklearn, numpy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time
import numpy as np
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from huggingface_hub import HfApi


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def metrics(labels,scores,threshold):
    predicted=np.asarray(scores)>=threshold
    p,r,f,_=precision_recall_fscore_support(labels,predicted,average='binary',zero_division=0)
    return {'n':len(labels),'threshold':float(threshold),'accuracy':float(accuracy_score(labels,predicted)),'precision':float(p),'recall':float(r),'f1':float(f),'confusion_matrix_tn_fp_fn_tp':confusion_matrix(labels,predicted,labels=[0,1]).ravel().tolist()}


def threshold_for(labels,scores):
    candidates=np.unique(np.r_[scores,np.max(scores)+1e-5,np.min(scores)-1e-5])
    return max(candidates,key=lambda t:(metrics(labels,scores,t)['f1'],metrics(labels,scores,t)['precision'],float(t)))


def run(data,output):
    output.mkdir(parents=True,exist_ok=True)
    random.seed(17);np.random.seed(17);torch.manual_seed(17)
    if torch.cuda.is_available():torch.cuda.manual_seed_all(17)
    splits={k:load(data/f'{k}.jsonl') for k in ['train','validation','calibration','test']}
    labels={k:np.array([r['label'] for r in v]) for k,v in splits.items()}
    manifest=json.loads((data/'manifest.json').read_text())
    for k,v in splits.items():
        assert hashlib.sha256((data/f'{k}.jsonl').read_bytes()).hexdigest()==manifest['splits'][k]['sha256']
    result={'dataset_manifest':manifest,'seed':17,'scope':'pair classification only, NOT PDF extraction, retrieval, invoice decisions or approval safety','experiments':{},'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'}
    vectorizer=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5))
    vectorizer.fit([r[x] for r in splits['train'] for x in ['left','right']])
    def baseline(rows):
        a=vectorizer.transform([r['left'] for r in rows]);b=vectorizer.transform([r['right'] for r in rows]);return np.asarray(a.multiply(b).sum(axis=1)).ravel()
    scores={k:baseline(v) for k,v in splits.items()}
    threshold=threshold_for(labels['calibration'],scores['calibration'])
    result['experiments']['B0']={k:metrics(labels[k],scores[k],threshold) for k in ['validation','calibration','test']}
    (output/'metrics.json').write_text(json.dumps(result,indent=2))
    name='cross-encoder/ms-marco-MiniLM-L6-v2'
    revision=HfApi().model_info(name).sha
    result['model']={'name':name,'revision':revision}
    tokenizer=AutoTokenizer.from_pretrained(name,revision=revision)
    model=AutoModelForSequenceClassification.from_pretrained(name,revision=revision)
    device='cuda:0' if torch.cuda.is_available() else 'cpu';model.to(device)
    # This MS MARCO model is a relevance scorer, not a procurement classifier.
    # Compare raw logits; fine-tune on binary identity labels with BCE logits.
    def score(rows):
        model.eval();values=[];start=time.perf_counter()
        with torch.no_grad():
            for offset in range(0,len(rows),32):
                batch=rows[offset:offset+32]
                inputs=tokenizer([r['left'] for r in batch],[r['right'] for r in batch],padding=True,truncation=True,max_length=128,return_tensors='pt').to(device)
                values.extend(model(**inputs).logits.reshape(-1).cpu().tolist())
        return np.array(values),time.perf_counter()-start
    b1={k:score(v)[0] for k,v in splits.items() if k!='train'}
    t=threshold_for(labels['calibration'],b1['calibration'])
    result['experiments']['B1']={k:metrics(labels[k],b1[k],t) for k in b1}
    (output/'metrics.json').write_text(json.dumps(result,indent=2));print('Frozen baseline evaluated',flush=True)
    optimizer=torch.optim.AdamW(model.parameters(),lr=2e-5)
    best=-1;history=[]
    for epoch in range(3):
        start=time.perf_counter();model.train();order=list(splits['train']);random.Random(17+epoch).shuffle(order);losses=[]
        for offset in range(0,len(order),16):
            batch=order[offset:offset+16]
            inputs=tokenizer([r['left'] for r in batch],[r['right'] for r in batch],padding=True,truncation=True,max_length=128,return_tensors='pt').to(device)
            y=torch.tensor([r['label'] for r in batch],dtype=torch.float32,device=device)
            optimizer.zero_grad();logits=model(**inputs).logits.reshape(-1)
            loss=torch.nn.functional.binary_cross_entropy_with_logits(logits,y);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step();losses.append(loss.item())
        val,_=score(splits['validation']);vt=threshold_for(labels['validation'],val);vm=metrics(labels['validation'],val,vt)
        history.append({'epoch':epoch+1,'training_loss':sum(losses)/len(losses),'validation_f1':vm['f1'],'duration_s':time.perf_counter()-start})
        print(json.dumps(history[-1]),flush=True)
        if vm['f1']>best:
            best=vm['f1'];model.save_pretrained(output/'best_model');tokenizer.save_pretrained(output/'best_model');result['best_epoch']=epoch+1
        torch.save({'epoch':epoch+1,'model':model.state_dict(),'optimizer':optimizer.state_dict(),'torch_rng':torch.get_rng_state()},output/'last_checkpoint.pt')
        (output/'training_history.json').write_text(json.dumps(history,indent=2))
    model=AutoModelForSequenceClassification.from_pretrained(output/'best_model').to(device)
    final={k:score(v) for k,v in splits.items() if k!='train'}
    t=threshold_for(labels['calibration'],final['calibration'][0])
    result['experiments']['E1']={k:{**metrics(labels[k],v[0],t),'total_scoring_s':v[1]} for k,v in final.items()}
    result['training']={'epochs':3,'batch_size':16,'lr':2e-5,'max_length':128,'loss':'BCEWithLogits','selection':'validation F1; thresholds calibrated separately','history':history}
    result['limitations']=['Synthetic easy templated pairs; no independent human label audit','Small test contains only three held-out product families','MS MARCO pretrained relevance model; verify license/data restrictions before distribution','No claim of invoice-level safety or extraction accuracy']
    (output/'metrics.json').write_text(json.dumps(result,indent=2))
    predictions=[]
    for i,row in enumerate(splits['test']):
        predictions.append({**row,'B0_score':float(scores['test'][i]),'B1_score':float(b1['test'][i]),'E1_logit':float(final['test'][0][i])})
    (output/'test_predictions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in predictions))
    tokenizer.save_pretrained(output/'best_model')
    print('RESULT_JSON '+json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('ml/data/pilot'));p.add_argument('--output',type=Path,default=Path('ml/results/pilot'));a=p.parse_args();run(a.data,a.output)
