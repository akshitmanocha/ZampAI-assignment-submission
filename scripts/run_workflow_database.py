"""Run three scenario traces in disposable real PostgreSQL schemas."""
import base64
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ml'))
from render_workflows import render
from evaluate_workflows import check_hashes


def run(dataset,output):
    check_hashes(dataset);payloads=[]
    for id in ['W23','W24','W25']:
        case=json.loads((dataset/'inputs'/f'{id}.json').read_text());expected=json.loads((dataset/'expected'/f'{id}.json').read_text())
        docs=[case['document']]
        if case['actions'][0]!='repeat_approval':
            second=deepcopy(docs[0]);second['invoice_number']='SH-STATE-B';docs.append(second)
        payloads.append({'case':case,'expected':expected,'pdfs':[base64.b64encode(render(d)).decode() for d in docs]})
    code=(ROOT/'ml/evaluate_workflow_database.py').read_text()+'\nrun(json.loads('+repr(json.dumps(payloads))+'))\n'
    result=subprocess.run(['docker','compose','exec','-T','app','python'],input=code,text=True,capture_output=True,cwd=ROOT,timeout=120)
    report=None
    for line in result.stdout.splitlines():
        if line.startswith('DATABASE_WORKFLOW_JSON '):report=json.loads(line[len('DATABASE_WORKFLOW_JSON '):])
    if report is None:raise RuntimeError('Database runner did not produce a result; command exit '+str(result.returncode))
    report['source_code_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'ml/evaluate_workflow_database.py',ROOT/'backend/reconcile/history.py',ROOT/'backend/reconcile/company_records.py']}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if result.returncode or report['passed']!=report['total']:raise SystemExit(1)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,default=ROOT/'fixtures/workflows/v1');p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.dataset,a.output)
