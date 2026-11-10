"""Explicit synthetic database demo, isolated from application records.

python -m reconcile.history_demo --seed
python -m reconcile.history_demo --approve-current
"""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import uuid
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from reconcile.models import Vendor,PurchaseOrder,POLine,Invoice,InvoiceLine
from reconcile.history import identifier_key,remaining_balance,previous_purchases,find_duplicates,approve_invoice,rank_previous_purchases


def uid(name):return uuid.uuid5(uuid.NAMESPACE_URL,'reconcile-history-demo:'+name)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seed',action='store_true');parser.add_argument('--approve-current',action='store_true');args=parser.parse_args()
    base=make_url(os.environ['DATABASE_URL'])
    if args.seed:
        admin=create_engine(base)
        with admin.begin() as conn:conn.execute(text('CREATE SCHEMA IF NOT EXISTS reconcile_history_demo'))
        admin.dispose()
    url=base.update_query_dict({'options':'-csearch_path=reconcile_history_demo'})
    engine=create_engine(url,isolation_level='READ COMMITTED')
    if args.seed:
        previous=os.environ['DATABASE_URL'];os.environ['DATABASE_URL']=url.render_as_string(hide_password=False)
        try:command.upgrade(Config(str(Path(__file__).resolve().parents[1]/'alembic.ini')),'head')
        finally:os.environ['DATABASE_URL']=previous
        with Session(engine) as s,s.begin():
            if s.get(Vendor,uid('vendor')) is None:
                s.add(Vendor(id=uid('vendor'),legal_name='SafeHands Supplies'));s.flush()
                s.add(PurchaseOrder(id=uid('po'),po_number='PO-2026-0147',vendor_id=uid('vendor')));s.flush()
                s.add(POLine(id=uid('line'),po_id=uid('po'),line_no=1,item_code='GLV-NIT-M-PF',description='Medium powder-free nitrile gloves',attributes={'material':'nitrile','size':'medium'},uom='EA',ordered_qty=Decimal('1000'),unit_price=Decimal('5')));s.flush()
                for name,qty in [('PRIOR-400','400'),('CURRENT-600','600')]:
                    s.add(Invoice(id=uid(name),vendor_id=uid('vendor'),po_id=uid('po'),invoice_number=name,invoice_number_key=identifier_key(name),document_sha256=hashlib.sha256(name.encode()).hexdigest(),gross_total=Decimal(qty)*Decimal('5'),recommendation='ready_for_approval'));s.flush()
                    s.add(InvoiceLine(invoice_id=uid(name),po_line_id=uid('line'),normalized_qty=Decimal(qty),normalized_unit_price=Decimal('5'),evidence={'source':'synthetic demo, not live extraction','page':1}));s.flush()
                approve_invoice(s,uid('PRIOR-400'),1,'synthetic-demo')
    result={'source':'fictional demo records, no PDF extraction performed'}
    with Session(engine) as s:
        result['before']=remaining_balance(s,uid('line'))
        result['previous_orders']=previous_purchases(s,uid('vendor'))
        result['similar_previous_orders']=rank_previous_purchases(s,uid('vendor'),'medium nitrile powder-free gloves')
        result['duplicate_check']=find_duplicates(s,uid('vendor'),'PRIOR-400','0'*64,Decimal('2000'))
    if args.approve_current:
        with Session(engine) as s,s.begin():result['approval']=approve_invoice(s,uid('CURRENT-600'),1,'synthetic-demo')
    with Session(engine) as s:result['after']=remaining_balance(s,uid('line'))
    print(json.dumps(result,default=str,indent=2));engine.dispose()

if __name__=='__main__':main()
