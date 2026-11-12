"""Real PDF -> durable worker -> saved decision -> authenticated action tests.

Each test uses its own migrated PostgreSQL schema. Gold expectations are authored
here; no test key or expected decision enters the production worker. No network
model calls or public application records are used.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.engine import make_url
from reconcile.app import create_app
from reconcile import database
from reconcile.cli import migrate, seed, create_user, uid, verify
from reconcile.models import (Submission, Run, Decision, Document, Approval,
    AuthSession, PurchaseOrder, POLine, now)

DATABASE = os.getenv('APPLICATION_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DATABASE, reason='requires explicit real PostgreSQL application test database')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ml'))


class Harness:
    def __init__(self):
        self.worker = None
        self.clients = []
        self.start_worker()
        self.client = self.login('approver')

    def start_worker(self):
        self.worker = subprocess.Popen([sys.executable, '-m', 'reconcile.worker'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def stop_worker(self, kill=False):
        if self.worker and self.worker.poll() is None:
            os.killpg(self.worker.pid, signal.SIGKILL if kill else signal.SIGTERM)
            self.worker.wait(timeout=10)

    def login(self, role):
        client = TestClient(create_app())
        client.__enter__()
        response = client.post('/api/auth/login', json={'email':role+'@test.invalid','password':'test-only-password-42'}, headers={'X-Reconcile-Client':'web'})
        assert response.status_code == 204, response.text
        assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=lax' in response.headers['set-cookie']
        self.clients.append(client)
        return client

    def post(self, path, body=None, client=None, key=None):
        return (client or self.client).post(path, json=body or {}, headers={
            'X-Reconcile-Client':'web','Idempotency-Key':key or str(uuid.uuid4())})

    def upload(self, name='happy', data=None, filename=None, key=None):
        data = data or (Path(__import__('reconcile').__file__).parent/'demo_samples'/f'{name}.pdf').read_bytes()
        response = self.client.post('/api/invoices', files={'file':(filename or name+'.pdf', data, 'application/pdf')},
            headers={'X-Reconcile-Client':'web','Idempotency-Key':key or str(uuid.uuid4())})
        assert response.status_code == 202, response.text
        return response.json(), data

    def wait(self, run_id, timeout=35):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            r=self.client.get('/api/runs/'+run_id)
            assert r.status_code == 200, r.text
            run=r.json()
            if run['state'] in ['completed','processing_failed']:
                return run
            time.sleep(.08)
        raise AssertionError('Worker did not finish: '+json.dumps(run))

    def processed(self, name='happy', **kwargs):
        response, data=self.upload(name, **kwargs)
        run=self.wait(response['run']['id'])
        assert run['state']=='completed', run
        id=response['invoice']['id']
        detail=self.client.get('/api/invoices/'+id).json()
        return id, detail, data

    def balance(self, po='0147'):
        rows=self.client.get('/api/purchase-orders').json()['items']
        return next(p for p in rows if p['number']=='PO-2026-'+po)['lines'][0]

    def close(self):
        self.stop_worker()
        for client in self.clients:
            client.__exit__(None,None,None)


@pytest.fixture
def h(monkeypatch):
    schema='application_test_'+uuid.uuid4().hex
    admin=create_engine(DATABASE)
    with admin.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    url=make_url(DATABASE).update_query_dict({'options':f'-csearch_path={schema}'})
    monkeypatch.setenv('DATABASE_URL',url.render_as_string(hide_password=False))
    database.engine.cache_clear()
    migrate()
    with database.session() as db,db.begin():
        seed(db)
        for role in ['approver','clerk','admin']:
            create_user(db, role+'@test.invalid', role.title(), role, 'test-only-password-42')
    harness=Harness()
    try:
        yield harness
    finally:
        harness.close()
        database.engine().dispose()
        database.engine.cache_clear()
        with admin.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_real_native_pdf_approval_replay_and_retained_bytes(h):
    id,detail,original=h.processed()
    assert detail['decision']['bucket']=='accept'
    assert detail['extraction']['pages'][0]['method']=='native'
    assert h.client.get('/api/invoices/'+id+'/document').content==original
    assert h.client.get('/api/invoices/'+id+'/pages/1').content.startswith(b'\x89PNG')
    events=h.client.get('/api/runs/'+detail['run']['id']).json()['events']
    assert any(e['type']=='stage.skipped' and e['stage']=='ocr' for e in events)
    assert len([e for e in events if e['type']=='stage.completed'])==10
    key=str(uuid.uuid4())
    result=h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1},key=key)
    assert result.status_code==200,result.text
    replay=h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1},key=key)
    assert replay.headers['Idempotent-Replayed']=='true'
    assert h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1}).json()['status']=='already_approved'
    assert Decimal(h.balance()['remaining_qty'])==0
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(Approval))==6
        assert verify(db)['ok']


def test_upload_idempotency_and_changed_payload(h):
    key=str(uuid.uuid4())
    first,data=h.upload(key=key)
    second,_=h.upload(key=key)
    assert first['invoice']['id']==second['invoice']['id']
    response=h.client.post('/api/invoices',files={'file':('another-name.pdf',data,'application/pdf')},headers={'X-Reconcile-Client':'web','Idempotency-Key':key})
    assert response.status_code==422 and response.json()['error']['code']=='IDEMPOTENCY_KEY_REUSED'
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(Submission))==1
        assert db.scalar(select(func.count()).select_from(Document))==1


def test_missing_pack_human_attestation_revalidates_without_overwriting_source(h):
    id,detail,_=h.processed('missing-pack')
    assert detail['decision']['bucket']=='human_review'
    original=deepcopy(detail['extraction']['fields'])
    response=h.post('/api/invoices/'+id+'/review',{'expected_decision_version':1,'corrections':[
        {'field_path':'lines[1].pack_factor','value':'100','reason':'Verified 100 gloves per box against approved supplier specification.'}]})
    assert response.status_code==202,response.text
    assert h.wait(response.json()['run']['id'])['state']=='completed'
    updated=h.client.get('/api/invoices/'+id).json()
    assert updated['decision']['bucket']=='accept',updated['decision']
    assert updated['decision']['version']==2
    assert updated['extraction']['fields']==original
    assert updated['corrections'][0]['value']=='100'
    assert h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1}).json()['error']['code']=='DECISION_VERSION_CONFLICT'
    assert h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':2}).status_code==200


def test_actual_minilm_candidates_human_choice_and_none_option(h):
    id,detail,_=h.processed('semantic')
    assert detail['decision']['bucket']=='human_review'
    retrieved=detail['decision']['retrieval']
    assert retrieved['version'].startswith('minilm-l6-onnx')
    candidate=retrieved['lines'][0]['candidates'][0]
    assert candidate['sku']=='GLV-M' and candidate['similarity']>0
    assert candidate['authorizes_invoice'] is False
    for choice,version,expected in [(None,1,'human_review'),(candidate['po_line_id'],2,'accept')]:
        result=h.post('/api/invoices/'+id+'/review',{'expected_decision_version':version,'corrections':[
            {'field_path':'lines[1].po_line_id','value':choice,'reason':'Manually compared the printed description with the supplier order specification.'}]})
        assert result.status_code==202,result.text
        h.wait(result.json()['run']['id'])
        assert h.client.get('/api/invoices/'+id).json()['decision']['bucket']==expected
    assert h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':3}).status_code==200


def test_specification_conflict_cannot_be_bypassed_by_review_choice(h):
    id,detail,_=h.processed('wrong-material')
    assert detail['decision']['bucket']=='reject'
    c=detail['decision']['retrieval']['lines'][0]['candidates'][0]
    assert 'material' in c['conflicts']
    result=h.post('/api/invoices/'+id+'/review',{'expected_decision_version':1,'corrections':[
        {'field_path':'lines[1].po_line_id','value':c['po_line_id'],'reason':'Attempt to choose conflicting item should fail.'}]})
    assert result.status_code==422
    assert h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1}).status_code==409


def test_offsetting_prices_are_both_detected(h):
    _,detail,_=h.processed('offset-prices')
    assert detail['decision']['bucket']=='reject'
    checks=detail['decision']['findings']['unit_price']['line_checks']
    assert [Decimal(c['delta']) for c in checks]==[Decimal('1'),Decimal('-1')]


def test_actual_image_only_pdf_uses_ocr(h):
    id,detail,_=h.processed('scan')
    assert detail['extraction']['pages'][0]['method']=='ocr'
    assert detail['decision']['bucket'] in ['accept','human_review'],detail['decision']
    printed='GLV-M Nitrile gloves medium [BOX; 100 EA/box]'
    original=deepcopy(detail['extraction']['fields'])
    if detail['decision']['bucket']=='human_review':
        assert original['lines'][0]['description'].get('requires_source_verification')
        response=h.post('/api/invoices/'+id+'/review',{'expected_decision_version':1,'corrections':[
            {'field_path':'lines[1].description','value':printed,
             'reason':'Authored test fixture: simulated reviewer restores the exact printed pack string from the source; this is not an OCR accuracy result.'}]})
        assert response.status_code==202,response.text
        assert h.wait(response.json()['run']['id'])['state']=='completed'
        corrected=h.client.get('/api/invoices/'+id).json()
        assert corrected['decision']['bucket']=='accept',corrected['decision']
        assert corrected['extraction']['fields']==original
    else:
        assert original['lines'][0]['description']['value']==printed
    events=h.client.get('/api/runs/'+detail['run']['id']).json()['events']
    assert any(e['type']=='stage.started' and e['stage']=='ocr' for e in events)


def test_two_concurrent_approvals_recheck_balances_and_save_new_decision(h):
    a,da,_=h.processed('partial-a')
    b,db,_=h.processed('partial-b')
    assert da['decision']['bucket']==db['decision']['bucket']=='accept'
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda id:h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1}),[a,b]))
    assert sorted(r.status_code for r in results)==[200,409],[r.text for r in results]
    loser=[a,b][next(i for i,r in enumerate(results) if r.status_code==409)]
    detail=h.client.get('/api/invoices/'+loser).json()
    assert detail['decision']['version']==2
    assert detail['decision']['origin']=='approval_check'
    assert detail['decision']['bucket']=='reject'
    assert Decimal(h.balance('0150')['remaining_qty'])==200
    with database.session() as db:assert verify(db)['ok']


def test_newer_duplicate_does_not_block_first_upload(h):
    first,detail,data=h.processed('happy')
    second,_,_=h.processed(data=data,filename='rescanned-copy.pdf')
    assert h.client.get('/api/invoices/'+second).json()['decision']['bucket']=='reject'
    assert h.post('/api/invoices/'+first+'/approve',{'expected_decision_version':1}).status_code==200


def test_roles_csrf_session_revocation_and_passwords_not_returned(h):
    id,_,_=h.processed()
    clerk=h.login('clerk')
    denied=h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1},client=clerk)
    assert denied.status_code==403
    assert clerk.post('/api/auth/logout').status_code==403
    assert h.client.post('/api/auth/logout',json={},headers={'X-Reconcile-Client':'web','Origin':'https://foreign.invalid'}).status_code==403
    admin=h.login('admin')
    assert h.post('/api/invoices/'+id+'/reject',{'expected_decision_version':1,'reason':'Not allowed for admin'},client=admin).status_code==403
    assert admin.get('/api/admin/diagnostics').status_code==200
    me=clerk.get('/api/auth/me')
    assert 'password' not in me.text
    assert len(h.client.cookies.get('reconcile_session'))>30
    assert h.post('/api/auth/logout',client=clerk).status_code==204
    assert clerk.get('/api/invoices').status_code==401


def test_login_rate_limit_uses_persistent_database(h):
    client=TestClient(create_app())
    for _ in range(10):
        response=client.post('/api/auth/login',json={'email':'missing@test.invalid','password':'wrong'},headers={'X-Reconcile-Client':'web'})
        assert response.status_code==401
    assert client.post('/api/auth/login',json={'email':'missing@test.invalid','password':'wrong'},headers={'X-Reconcile-Client':'web'}).status_code==429


def enable_public_demo(monkeypatch, email='approver@test.invalid'):
    monkeypatch.setenv('PUBLIC_DEMO_MODE', 'true')
    monkeypatch.setenv('SEED_DEMO_DATA', 'true')
    monkeypatch.setenv('INITIAL_APPROVER_EMAIL', email)


def test_public_demo_creates_revocable_session_without_password(h, monkeypatch):
    enable_public_demo(monkeypatch)
    monkeypatch.setenv('SESSION_COOKIE_SECURE', 'true')
    with TestClient(create_app(), base_url='https://testserver') as client:
        assert client.get('/api/invoices').status_code == 401
        assert client.post('/api/auth/demo', json={}).status_code == 403
        headers = {'X-Reconcile-Client': 'web'}
        assert client.post('/api/auth/demo', json={}, headers={**headers, 'Origin': 'https://foreign.invalid'}).status_code == 403
        response = client.post('/api/auth/demo', json={}, headers=headers)
        assert response.status_code == 204
        assert all(value in response.headers['set-cookie'] for value in ['HttpOnly', 'Secure', 'SameSite=lax', 'Path=/api'])
        me = client.get('/api/auth/me')
        assert me.json()['email'] == 'approver@test.invalid'
        assert me.json()['role'] == 'approver' and 'password' not in me.text
        token = client.cookies.get('reconcile_session')
        assert client.post('/api/auth/demo', json={}, headers=headers).status_code == 204
        assert client.cookies.get('reconcile_session') == token
        assert client.get('/api/purchase-orders').status_code == 200
        assert client.get('/api/admin/diagnostics').status_code == 403
        assert client.post('/api/auth/logout', json={}, headers=headers).status_code == 204
        assert client.get('/api/invoices').status_code == 401


@pytest.mark.parametrize('email', ['clerk@test.invalid', 'admin@test.invalid', 'missing@test.invalid'])
def test_public_demo_cannot_select_other_roles_or_missing_account(h, monkeypatch, email):
    enable_public_demo(monkeypatch, email)
    with TestClient(create_app()) as client:
        response = client.post('/api/auth/demo', json={}, headers={'X-Reconcile-Client': 'web'})
        assert response.status_code == 503
        assert not client.cookies.get('reconcile_session')


def test_public_demo_session_creation_is_rate_limited(h, monkeypatch):
    enable_public_demo(monkeypatch)
    with TestClient(create_app()) as client:
        for _ in range(10):
            client.cookies.clear()
            assert client.post('/api/auth/demo', json={}, headers={'X-Reconcile-Client': 'web'}).status_code == 204
        client.cookies.clear()
        assert client.post('/api/auth/demo', json={}, headers={'X-Reconcile-Client': 'web'}).status_code == 429


def test_public_demo_can_process_and_approve_without_password(h, monkeypatch):
    enable_public_demo(monkeypatch)
    original_client = h.client
    with TestClient(create_app()) as client:
        assert client.post('/api/auth/demo', json={}, headers={'X-Reconcile-Client': 'web'}).status_code == 204
        h.client = client
        try:
            invoice_id, detail, _ = h.processed()
            assert detail['decision']['bucket'] == 'accept'
            assert h.post('/api/invoices/'+invoice_id+'/approve', {'expected_decision_version': 1}).status_code == 200
            assert Decimal(h.balance()['remaining_qty']) == 0
        finally:
            h.client = original_client


def test_demo_reset_restores_balances_and_old_retry_cannot_erase_new_run(h, monkeypatch):
    from reconcile.models import Correction, RunEvent
    enable_public_demo(monkeypatch)
    upload_key, reset_key = str(uuid.uuid4()), str(uuid.uuid4())
    invoice_id, _, _ = h.processed(key=upload_key)
    assert h.post('/api/invoices/'+invoice_id+'/approve', {'expected_decision_version': 1}).status_code == 200
    review_id, _, _ = h.processed('missing-pack')
    reviewed = h.post('/api/invoices/'+review_id+'/review', {'expected_decision_version': 1, 'corrections': [
        {'field_path': 'lines[1].pack_factor', 'value': '100', 'reason': 'Fictional supplier confirms 100 gloves per box.'}]})
    assert reviewed.status_code == 202
    assert h.wait(reviewed.json()['run']['id'])['state'] == 'completed'
    reset = h.post('/api/demo/reset', {'confirmation': 'RESET DEMO'}, key=reset_key)
    assert reset.status_code == 200, reset.text
    assert reset.json()['removed_invoices'] == 2
    assert h.client.get('/api/invoices').json()['items'] == []
    assert h.client.get('/api/auth/me').status_code == 200
    for po in ['0147', '0148', '0149', '0150', '0151']:
        assert Decimal(h.balance(po)['remaining_qty']) == 600
    with database.session() as db:
        for model in [Submission, Document, Run, Decision, Correction, RunEvent]:
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert verify(db)['ok']
    new_id, detail, _ = h.processed(key=upload_key)
    assert new_id != invoice_id and detail['decision']['bucket'] == 'accept'
    replay = h.post('/api/demo/reset', {'confirmation': 'RESET DEMO'}, key=reset_key)
    assert replay.status_code == 200 and replay.headers['Idempotent-Replayed'] == 'true'
    assert len(h.client.get('/api/invoices').json()['items']) == 1


def test_demo_reset_requires_demo_mode_approver_confirmation_and_csrf(h, monkeypatch):
    body = {'confirmation': 'RESET DEMO'}
    assert h.post('/api/demo/reset', body).status_code == 404
    enable_public_demo(monkeypatch)
    assert h.post('/api/demo/reset', {'confirmation': 'wrong'}).status_code == 422
    assert h.client.post('/api/demo/reset', json=body).status_code == 403
    assert h.post('/api/demo/reset', body, client=h.login('clerk')).status_code == 403
    assert h.post('/api/demo/reset', body, client=h.login('admin')).status_code == 403
    monkeypatch.setenv('SEED_DEMO_DATA', 'false')
    assert h.post('/api/demo/reset', body).status_code == 404


def test_demo_reset_refuses_active_processing_without_removing_documents(h, monkeypatch):
    enable_public_demo(monkeypatch)
    h.stop_worker()
    uploaded, original = h.upload()
    response = h.post('/api/demo/reset', {'confirmation': 'RESET DEMO'})
    assert response.status_code == 409 and response.json()['error']['code'] == 'RUN_IN_PROGRESS'
    assert h.client.get('/api/invoices/'+uploaded['invoice']['id']+'/document').content == original


def test_demo_reset_rolls_back_everything_if_reseeding_fails(h, monkeypatch):
    from reconcile.errors import AppError
    enable_public_demo(monkeypatch)
    invoice_id, _, _ = h.processed()
    assert h.post('/api/invoices/'+invoice_id+'/approve', {'expected_decision_version': 1}).status_code == 200

    def unavailable(db):
        raise AppError('DEMO_RESET_FAILED', 'Try resetting again shortly.', 503, retryable=True)

    monkeypatch.setattr('reconcile.cli.seed', unavailable)
    assert h.post('/api/demo/reset', {'confirmation': 'RESET DEMO'}).status_code == 503
    assert h.client.get('/api/invoices/'+invoice_id).status_code == 200
    assert Decimal(h.balance()['remaining_qty']) == 0


def test_corrupt_pdf_is_processing_failure_and_retry_has_new_run(h):
    upload,original=h.upload(data=b'%PDF-1.7\ncorrupt-content')
    failed=h.wait(upload['run']['id'])
    assert failed['state']=='processing_failed'
    id=upload['invoice']['id']
    detail=h.client.get('/api/invoices/'+id).json()
    assert detail['decision'] is None
    assert detail['invoice']['display_status']=='processing_failed'
    assert h.client.get('/api/invoices/'+id+'/document').content==original
    retry=h.post('/api/invoices/'+id+'/retry')
    assert retry.status_code==202 and retry.json()['run']['id']!=failed['id']
    assert h.wait(retry.json()['run']['id'])['state']=='processing_failed'


def test_tolerance_policy_matches_approval_guard(h):
    from render_workflows import render
    source=json.loads((ROOT/'fixtures/workflows/v1/inputs/W19.json').read_text())['document']
    source['po_reference']='PO-2026-0147'
    id,detail,_=h.processed(data=render(source))
    assert detail['decision']['bucket']=='accept',detail['decision']
    result=h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1})
    assert result.status_code==200,result.text


def test_master_data_change_queues_revalidation_instead_of_approving(h):
    id,_,_=h.processed()
    with database.session() as db,db.begin():
        po=db.get(PurchaseOrder,uid('PO-2026-0147'));po.revision+=1
    response=h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1})
    assert response.status_code==409
    assert response.json()['error']['code']=='APPROVAL_STALE'
    assert h.wait(response.json()['error']['details']['run_id'])['state']=='completed'
    assert h.client.get('/api/invoices/'+id).json()['decision']['version']==2


def test_real_worker_kill_recovers_expired_lease_with_one_decision(h):
    response,_=h.upload('scan')
    id,run_id=response['invoice']['id'],response['run']['id']
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        state=h.client.get('/api/runs/'+run_id).json()
        if any(e['stage']=='ocr' and e['type']=='stage.started' for e in state['events']):break
        time.sleep(.03)
    else:raise AssertionError('OCR did not start')
    h.stop_worker(kill=True)
    with database.session() as db,db.begin():
        run=db.get(Run,uuid.UUID(run_id))
        assert run.state=='running'
        run.lease_until=now()-timedelta(seconds=1) # accelerate 60-second lease expiry after a real kill
    h.start_worker()
    result=h.wait(run_id)
    assert result['state']=='completed',result
    assert result['attempt']==2
    assert any(e['type']=='run.lease_recovered' for e in result['events'])
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(Decision).where(Decision.submission_id==uuid.UUID(id)))==1
        assert verify(db)['ok']


def test_expired_sessions_and_upload_limits_fail_before_creating_runs(h):
    count=h.client.get('/api/invoices').json()['counts']
    r=h.client.post('/api/invoices',files={'file':('oversized.pdf',b'%PDF-'+b'a'*(10*1024*1024),'application/pdf')},headers={'X-Reconcile-Client':'web','Idempotency-Key':str(uuid.uuid4())})
    assert r.status_code==413
    assert h.client.get('/api/invoices').json()['counts']==count
    with database.session() as db,db.begin():
        for token in db.scalars(select(AuthSession)):token.expires_at=now()-timedelta(seconds=1)
    assert h.client.get('/api/invoices').status_code==401


def test_company_import_cannot_erase_existing_approved_quantity(h):
    from reconcile.company_import import import_company
    payload={'vendors':[{'legal_name':'SafeHands Supplies','status':'approved'}], 'purchase_orders':[
        {'number':'PO-2026-0147','vendor_name':'SafeHands Supplies','order_date':'2026-11-01', 'lines':[
            {'sku':'GLV-M','description':'Nitrile gloves medium','material':'nitrile','size':'medium','uom':'EA',
             'ordered_qty':'300','unit_price':'5','tax_rate':'0'}]}]}
    with pytest.raises(ValueError,match='already approved'):
        with database.session() as db,db.begin():import_company(db,payload)
    assert Decimal(h.balance()['remaining_qty'])==600


def test_pathological_page_dimensions_are_bounded_in_worker(h):
    from reportlab.pdfgen import canvas
    data=io.BytesIO();c=canvas.Canvas(data,pagesize=(5000,5000));c.drawString(10,4900,'Invoice');c.save()
    upload,_=h.upload(data=data.getvalue())
    run=h.wait(upload['run']['id'])
    assert run['state']=='processing_failed' and run['error_code']=='PDF_PAGE_DIMENSIONS'


def test_printed_positive_tax_rate_goes_through_pdf_worker_and_approval(h):
    from reportlab.pdfgen import canvas
    with database.session() as db,db.begin():
        line=db.get(POLine,uid('PO-2026-0147:1'))
        line.attributes={**line.attributes,'tax_rate':'0.18'}
    data=io.BytesIO();c=canvas.Canvas(data,pagesize=(612,842))
    c.setFont('Helvetica',12)
    for y,text in [(800,'INVOICE'),(775,'FROM'),(755,'SafeHands Supplies'),
        (725,'Invoice No: TAX-REAL-PDF-1'),(700,'Date: 2026-11-06'),(675,'PO: PO-2026-0147'),(650,'Currency: INR')]:
        c.drawString(40,y,text)
    for x,text in [(40,'DESCRIPTION'),(325,'QTY'),(410,'UNIT PRICE'),(520,'AMOUNT')]:c.drawString(x,600,text)
    c.setFont('Helvetica',8)
    for x,text in [(40,'GLV-M Nitrile gloves medium [BOX; 100 EA/box]'),(325,'6'),(410,'500.00'),(520,'3000.00')]:c.drawString(x,570,text)
    c.setFont('Helvetica',12)
    c.drawString(330,500,'Subtotal INR 3000.00')
    c.drawString(330,475,'Tax @ 18% INR 540.00')
    c.drawString(330,450,'Grand Total INR 3540.00')
    c.save()
    id,detail,_=h.processed(data=data.getvalue())
    assert detail['decision']['document']['tax_rate']=='0.18',detail['decision']
    assert detail['decision']['bucket']=='accept',detail['decision']
    assert h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1}).status_code==200


def test_failed_revalidation_retains_intended_corrections_until_retry(h,monkeypatch):
    id,detail,_=h.processed('happy')
    assert detail['decision']['bucket']=='accept'
    h.stop_worker()
    original=os.environ.get('MINILM_DIR')
    monkeypatch.setenv('MINILM_DIR','/tmp/nonexistent-test-model-'+uuid.uuid4().hex)
    h.start_worker()
    correction={'field_path':'header.invoice_number','value':'HUMAN-CORRECTED-REF','reason':'Verified the corrected reference against the supplier evidence.'}
    queued=h.post('/api/invoices/'+id+'/review',{'expected_decision_version':1,'corrections':[correction]})
    assert queued.status_code==202,queued.text
    failed=h.wait(queued.json()['run']['id'])
    assert failed['state']=='processing_failed' and failed['error_code']=='MATCHER_UNAVAILABLE'
    assert h.post('/api/invoices/'+id+'/approve',{'expected_decision_version':1}).status_code==409
    blocked=h.post('/api/invoices/'+id+'/review',{'expected_decision_version':1,'corrections':[]})
    assert blocked.json()['error']['code']=='LATEST_RUN_FAILED'
    h.stop_worker()
    if original is None:monkeypatch.delenv('MINILM_DIR')
    else:monkeypatch.setenv('MINILM_DIR',original)
    h.start_worker()
    retry=h.post('/api/invoices/'+id+'/retry')
    assert h.wait(retry.json()['run']['id'])['state']=='completed'
    new=h.client.get('/api/invoices/'+id).json()
    assert new['decision']['version']==2
    assert new['decision']['document']['invoice_number']=='HUMAN-CORRECTED-REF'
    assert len(new['corrections'])==1
