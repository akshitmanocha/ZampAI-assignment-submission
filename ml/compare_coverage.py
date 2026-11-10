"""Compare existing epoch-1/epoch-3 checkpoints at ~90% pair coverage.

Select with validation auto accuracy then validation BCE; challenge is development
once inspected. Does not retrain, reject invoices, or enable production routing.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import torch
from transformers import AutoTokenizer,AutoModelForSequenceClassification
from coverage_policy import fit,evaluate_at_budget


def run(data,challenge,checkpoint_root,out):
    device='cuda:0' if torch.cuda.is_available() else 'cpu'
    tokenizer=AutoTokenizer.from_pretrained(checkpoint_root/'best_model')
    model=AutoModelForSequenceClassification.from_pretrained(checkpoint_root/'best_model').to(device)
    splits={k:[json.loads(x) for x in (data/f'{k}.jsonl').read_text().splitlines()] for k in ['validation','calibration','test']}
    challenge_rows=[json.loads(x) for x in (challenge/'pairs.jsonl').read_text().splitlines()]
    def score(rows):
        model.eval()
        with torch.no_grad():
            for start in range(0,len(rows),32):
                batch=rows[start:start+32]
                inputs=tokenizer([r['left'] for r in batch],[r['right'] for r in batch],padding=True,truncation=True,max_length=128,return_tensors='pt').to(device)
                for r,s in zip(batch,model(**inputs).logits.reshape(-1).cpu().tolist()):r['score']=s
        return rows
    def candidate(name):
        rows=score(splits['validation']);policy=fit(rows,.9)
        report=evaluate_at_budget(rows,policy,.9)
        loss=torch.nn.functional.binary_cross_entropy_with_logits(torch.tensor([r['score'] for r in rows]),torch.tensor([r['label'] for r in rows],dtype=torch.float32)).item()
        return {'checkpoint':name,'validation_auto_accuracy':report['automatic_accuracy'],'validation_bce':loss,'policy':policy}
    first=candidate('epoch_1')
    last=torch.load(checkpoint_root/'last_checkpoint.pt',map_location='cpu',weights_only=True)
    model.load_state_dict(last['model']);second=candidate('epoch_3')
    chosen=max([first,second],key=lambda c:(c['validation_auto_accuracy'],-c['validation_bce']))
    if chosen['checkpoint']=='epoch_1':model=AutoModelForSequenceClassification.from_pretrained(checkpoint_root/'best_model').to(device)
    reports={k:evaluate_at_budget(score(rows),chosen['policy'],.9) for k,rows in [*splits.items(),('challenge_development',challenge_rows)]}
    result={'selection':'validation auto accuracy at ~90% coverage, tie-break lower validation BCE; no new training','candidates':[{k:v for k,v in c.items() if k!='policy'} for c in [first,second]],'selected':chosen['checkpoint'],'policy':asdict(chosen['policy']),'reports':reports,'limitation':'challenge previously inspected; subsequent comparison is development evidence, not fresh blind test; pair classification is not invoice automation'}
    out.mkdir(parents=True,exist_ok=True);(out/'metrics.json').write_text(json.dumps(result,indent=2));model.save_pretrained(out/'model');tokenizer.save_pretrained(out/'model');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('ml/data/pilot'));p.add_argument('--challenge',type=Path,default=Path('ml/data/challenge-v1'));p.add_argument('--checkpoint-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.data,a.challenge,a.checkpoint_root,a.output)
