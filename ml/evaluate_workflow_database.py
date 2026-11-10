"""Real PostgreSQL traces. Execute inside app container; never SQLite.

Input payload supplies ordinary fictional company data and actual native PDFs.
Expected answers remain in this harness and never enter production functions.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
from datetime import date
import hashlib,json,os,threading,uuid
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine,select,func,text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from reconcile.models import Vendor,PurchaseOrder,POLine,Invoice,InvoiceLine,Allocation,Approval
from reconcile.company_records import snapshot
from reconcile.business_validation import validate,from_extraction
from reconcile.invoice_parser import parse_invoice
from reconcile.document_text import extract_document
from reconcile.history import approve_invoice,remaining_balance,identifier_key,HistoryConflict


def run_one(payload):
    case=payload['case'];answer=payload['expected'];action=case['actions'][0]
    schema='workflow_validation_'+uuid.uuid4().hex
    admin=create_engine(os.environ['DATABASE_URL']);engine=None;created=False
    result={'case_id':case['id'],'action':action}
    try:
        if admin.dialect.name!='postgresql':raise RuntimeError('Real PostgreSQL required')
        with admin.connect() as c:result['postgresql_version']=c.scalar(text("SELECT current_setting('server_version')"))
        with admin.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
        created=True
        url=make_url(os.environ['DATABASE_URL']).update_query_dict({'options':f'-csearch_path={schema}'})
        engine=create_engine(url,isolation_level='READ COMMITTED')
        previous=os.environ['DATABASE_URL'];os.environ['DATABASE_URL']=url.render_as_string(hide_password=False)
        try:command.upgrade(Config('/app/backend/alembic.ini'),'head')
        finally:os.environ['DATABASE_URL']=previous
        ids={};policy=case['company']['policy']
        with Session(engine) as s,s.begin():
            for v in case['company']['vendors']:
                row=Vendor(legal_name=v['legal_name'],status=v['status']);s.add(row);s.flush();ids[v['id']]=row.id
            for po in case['company']['purchase_orders']:
                row=PurchaseOrder(po_number=po['number'],vendor_id=ids[po['vendor_id']],status=po['status'],currency=po['currency'],order_date=date(2026,11,1));s.add(row);s.flush();ids[po['id']]=row.id
                for line in po['lines']:
                    r=POLine(po_id=row.id,line_no=po['lines'].index(line)+1,item_code=line['sku'],description=line['description'],attributes={'material':line['material'],'size':line['size']},uom=line['uom'],ordered_qty=Decimal(line['ordered_qty']),unit_price=Decimal(line['unit_price']))
                    # line_no only needs uniqueness within the order.
                    r.line_no=po['lines'].index(line)+1;s.add(r);s.flush();ids[line['id']]=r.id
            prior_count=0
            if case['company']['invoice_history']:
                raise RuntimeError('This stateful harness requires explicit allocation history only')
            for index,allocation in enumerate(case['company']['allocations']):
                line=s.get(POLine,ids[allocation['po_line_id']]);order=s.get(PurchaseOrder,line.po_id)
                qty=Decimal(allocation['qty']);amount=Decimal(allocation['amount'])
                assert qty*line.unit_price==amount
                number='PRIOR-'+str(index+1)
                prior=Invoice(vendor_id=order.vendor_id,po_id=order.id,invoice_number=number,invoice_number_key=identifier_key(number),document_sha256=hashlib.sha256(number.encode()).hexdigest(),currency=order.currency,gross_total=amount,recommendation='ready_for_approval');s.add(prior);s.flush()
                s.add(InvoiceLine(invoice_id=prior.id,po_line_id=line.id,normalized_qty=qty,normalized_unit_price=line.unit_price,evidence={'source':'seeded previously verified history'}));s.flush()
                approve_invoice(s,prior.id,1,'history-seed');prior_count+=1
        pending=[];initial=[]
        with Session(engine) as s,s.begin():
            for encoded in payload['pdfs']:
                data=base64.b64decode(encoded);document=from_extraction(parse_invoice(extract_document(data)))
                current=snapshot(s,policy)
                validation=validate(document,current,hashlib.sha256(data).hexdigest(),today='2026-11-10')
                initial.append(validation['bucket'])
                if validation['bucket']!='accept':raise AssertionError('Initial real-PDF validation did not accept')
                po_id=uuid.UUID(validation['po_id']);vendor_id=s.get(PurchaseOrder,po_id).vendor_id
                invoice=Invoice(vendor_id=vendor_id,po_id=po_id,invoice_number=document['invoice_number'],invoice_number_key=identifier_key(document['invoice_number']),document_sha256=hashlib.sha256(data).hexdigest(),currency=document['currency'],gross_total=Decimal(document['grand_total']),recommendation='ready_for_approval');s.add(invoice);s.flush()
                for line in validation['normalized_lines']:
                    s.add(InvoiceLine(invoice_id=invoice.id,po_line_id=uuid.UUID(line['po_line_id']),normalized_qty=Decimal(line['qty']),normalized_unit_price=Decimal(line['unit_price']),evidence=line['evidence']))
                s.flush();pending.append((invoice.id,document,hashlib.sha256(data).hexdigest()))
        def approve(item):
            try:
                with Session(engine) as s,s.begin():return approve_invoice(s,item[0],1,'validation-approver')['status']
            except HistoryConflict as e:return e.code
        if action=='repeat_approval':
            statuses=[approve(pending[0]),approve(pending[0])]
            assert statuses==['approved','already_approved']
        elif action=='sequential_stale':
            statuses=[approve(pending[0]),approve(pending[1])]
            assert statuses==['approved','APPROVAL_STALE']
        else:
            barrier=threading.Barrier(2)
            def contender(item):barrier.wait(timeout=10);return approve(item)
            with ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(contender,item) for item in pending];statuses=[f.result(timeout=30) for f in futures]
            assert sorted(statuses)==sorted(['approved','APPROVAL_STALE'])
        with Session(engine) as s:
            tracked_line=s.scalar(select(InvoiceLine.po_line_id).where(InvoiceLine.invoice_id==pending[0][0]))
            balance=remaining_balance(s,tracked_line);new_approvals=s.scalar(select(func.count()).select_from(Approval))-prior_count
            assert balance['remaining_qty']==Decimal(answer['values']['final_remaining_qty'])
            assert new_approvals==answer['values']['successful_new_approvals']
            allocation_count=s.scalar(select(func.count()).select_from(Allocation))
            assert allocation_count==prior_count+1
            if action!='repeat_approval':
                losing=next(item for item,status in zip(pending,statuses) if status=='APPROVAL_STALE')
                after=validate(losing[1],snapshot(s,policy,exclude_invoice_id=losing[0]),losing[2],today='2026-11-10')
                assert after['bucket']=='reject' and 'remaining_quantity' in after['blocking_rules']
                result['post_approval_revalidation']=after['bucket']
        result.update(passed=True,initial_pdf_buckets=initial,statuses=statuses,remaining_qty=str(balance['remaining_qty']),new_approvals=new_approvals,allocation_count=allocation_count)
    except Exception as e:
        result.update(passed=False,error_type=type(e).__name__)
    finally:
        if engine is not None:engine.dispose()
        if created:
            with admin.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
    return result


def run(payloads):
    results=[run_one(p) for p in payloads]
    print('DATABASE_WORKFLOW_JSON '+json.dumps({'database':'PostgreSQL','results':results,'passed':sum(r['passed'] for r in results),'total':len(results)}),flush=True)
