"""Verify real production Compose containers with two new fictional PDFs.

Adds two open verification records, preserves original bytes and never approves
or consumes an order balance. Credentials are read only from a private file.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time
import uuid
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ml'))
from render_workflows import render,scanned


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--account-file',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    accounts=json.loads(args.account_file.read_text())
    account=next(a for a in accounts if a['role']=='approver')
    headers={'X-Reconcile-Client':'web'}
    report={'scope':'Actual non-root, read-only Compose app/worker; fictional input; no approvals','cases':[]}
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=15) as client:
        deadline=time.monotonic()+40
        ready=None
        while time.monotonic()<deadline:
            try:
                ready=client.get('/health/ready')
                if ready.status_code==200:break
            except httpx.ConnectError:
                pass
            time.sleep(.25)
        assert ready is not None and ready.status_code==200, 'Application is not ready'
        report['readiness']=ready.json()
        login=client.post('/api/auth/login',json={'email':account['email'],'password':account['password']},headers=headers)
        assert login.status_code==204, 'Staff sign-in failed'
        before=client.get('/api/purchase-orders').json()
        for variant in ['native','scan']:
            nonce=uuid.uuid4().hex[:8].upper()
            doc={'vendor_name':'SafeHands Supplies','invoice_number':'CHECK-'+nonce,'invoice_date':'2026-11-06',
                'po_reference':'PO-2026-0147','currency':'INR','subtotal':'5.00','tax_total':'0.00','grand_total':'5.00',
                'lines':[{'description':'GLV-M Nitrile gloves medium [EA]','qty':'1','unit_price':'5.00','amount':'5.00'}]}
            data=render(doc)
            if variant=='scan':data=scanned(data)
            upload=client.post('/api/invoices',files={'file':('local-verification-'+variant+'.pdf',data,'application/pdf')},headers={**headers,'Idempotency-Key':str(uuid.uuid4())})
            assert upload.status_code==202, 'PDF upload failed'
            result=upload.json();id=result['invoice']['id'];run_id=result['run']['id']
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                run=client.get('/api/runs/'+run_id).json()
                if run['state'] in ['completed','processing_failed']:break
                time.sleep(.2)
            assert run['state']=='completed', 'Worker failed to complete the real PDF'
            detail=client.get('/api/invoices/'+id).json()
            initial_bucket=detail['decision']['bucket']
            mismatches=[]
            for name,value in doc.items():
                if name=='lines':continue
                if detail['decision']['document'].get(name)!=value:
                    mismatches.append({'field_path':'header.'+name,'value':value,'reason':'Local verification fixture: simulated reviewer copies the known authored value from the printed source. This is not an OCR accuracy result.'})
            for i,line in enumerate(doc['lines'],1):
                for name,value in line.items():
                    if detail['decision']['document']['lines'][i-1].get(name)!=value:
                        mismatches.append({'field_path':f'lines[{i}].'+name,'value':value,'reason':'Local verification fixture: simulated reviewer restores the authored source value, then the rules run again.'})
            if initial_bucket=='human_review':
                assert mismatches, 'Unexpected business review needs investigation'
                review=client.post('/api/invoices/'+id+'/review',json={'expected_decision_version':detail['decision']['version'],'corrections':mismatches},headers={**headers,'Idempotency-Key':str(uuid.uuid4())})
                assert review.status_code==202,'Staff correction failed'
                review_run=review.json()['run']['id'];deadline=time.monotonic()+45
                while time.monotonic()<deadline:
                    r=client.get('/api/runs/'+review_run).json()
                    if r['state'] in ['completed','processing_failed']:break
                    time.sleep(.2)
                assert r['state']=='completed','Correction revalidation failed'
                detail=client.get('/api/invoices/'+id).json()
            else:
                assert not mismatches,'Automatic outcome contains an incorrect source value'
            assert detail['decision']['bucket']=='accept','Verification invoice needs investigation'
            assert client.get('/api/invoices/'+id+'/document').content==data
            assert client.get('/api/invoices/'+id+'/pages/1').content.startswith(b'\x89PNG')
            report['cases'].append({'variant':variant,'invoice_id':id,'run_id':run_id,'bucket':detail['decision']['bucket'],
                'initial_bucket':initial_bucket,'simulated_review_fields':[c['field_path'] for c in mismatches],
                'oracle_document':doc,'method':detail['extraction']['pages'][0]['method'],'pdf_sha256':hashlib.sha256(data).hexdigest(),
                'bytes_preserved':True,'preview_available':True,'decision_version':detail['decision']['version']})
        after=client.get('/api/purchase-orders').json()
        assert before==after,'Recommendations must not change balances'
        report['ledger_unchanged']=True
        assert client.post('/api/auth/logout',json={},headers=headers).status_code==204
        assert client.get('/api/invoices').status_code==401
        report['logout_revoked']=True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
    print('PASS: actual native/scanned PDF processing, byte preservation, source preview, explicit review fallback, unchanged ledger and session revocation')

if __name__=='__main__':main()
