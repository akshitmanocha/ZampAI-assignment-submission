"""Bounded optional free-model comparison on public synthetic documents only."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import time
import urllib.request
from reconcile.vision_extraction import request_vision,MODEL
from extraction_metrics import MAP,line_score,summarize


def run(data,out,key_file,split,max_requests=16):
    # Refuse a non-free catalog price; no alternate paid model is permitted.
    catalog=json.load(urllib.request.urlopen('https://openrouter.ai/api/v1/models',timeout=30))
    model=next(m for m in catalog['data'] if m['id']==MODEL)
    if any(Decimal(model['pricing'].get(k,'0'))!=0 for k in ['prompt','completion']):raise RuntimeError('Model is not zero-priced; stopped')
    gold=json.loads((data/'gold.json').read_text());out.mkdir(parents=True,exist_ok=True)
    if (out/'metrics.json').exists():raise RuntimeError('Existing run output; use a fresh directory')
    (out/'provider_model.json').write_text(json.dumps(model,indent=2))
    selected=[(name,e) for name,e in gold.items() if e['split']==split]
    # Freeze before inference: all 12 clean images plus degraded variants for
    # first two selected base documents. No cross-quality input in one request.
    tasks=[(name,e,q) for i,(name,e) in enumerate(selected) for q in (['clean','faded','bad_scan'] if i<2 else ['clean'])]
    (out/'selection.json').write_text(json.dumps({'split':split,'images':[{'file_name':n,'quality':q} for n,_,q in tasks],'max_requests':max_requests,'selection':'all clean images plus faded/bad_scan for first two documents in fixed manifest order'},indent=2))
    records=[];used=0;failures=[]
    for name,e,q in tasks:
        if used>=max_requests:break
        started=time.perf_counter();used+=1
        response=request_vision(data/'images'/(Path(name).stem+'__'+q+'.png'),key_file)
        if response.get('error'):
            # Save synthetic response text only for schema diagnosis, never key.
            failures.append({'file_name':name,'quality':q,**response})
            print('Vision request failed:',response['error'],response.get('http_status'),flush=True)
            if response.get('http_status') in [401,402,403,404,429] or response.get('error')=='nonzero_reported_cost_stop':break
            continue
        record={'file_name':name,'quality':q,'template':e['gold']['_template_used'],'split':split,'seconds':time.perf_counter()-started,'prediction':response['prediction'],'gold':e['gold'],'technical_error':None,'line_metrics':line_score(response['prediction']['lines'],e['gold']['line_items']),'provider_response':response}
        records.append(record)
        with (out/'predictions.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
        print('Vision completed',len(records),'requests used',used,'of',max_requests,flush=True)
        time.sleep(3.2)
    report={'model':MODEL,'requests_used':used,'selected_images':len(tasks),'completed_images':len(records),'failures':failures,'split':split,'overall':summarize(records),'by_quality':{q:summarize([r for r in records if r['quality']==q]) for q in ['clean','faded','bad_scan']},'limitations':['Free public-data experiment only; no private invoices','Provider model can change; ID/usage/model metadata saved','Model-proposed values/boxes not automatically verified','Only completed requests summarized; coverage/failure counts reported separately','Publisher labels may not be visibly printed; label audit incomplete','No LLM judge used; independent saved labels determine scores','Image resizing differs from local PDF OCR route']}
    (out/'metrics.json').write_text(json.dumps(report,indent=2));print('VISION_JSON '+json.dumps({'completed':len(records),'requests':used,'overall':report['overall']}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--key-file',type=Path,required=True);p.add_argument('--split',choices=['development','heldout'],required=True);p.add_argument('--max-requests',type=int,default=16);a=p.parse_args();run(a.data,a.output,a.key_file,a.split,a.max_requests)
