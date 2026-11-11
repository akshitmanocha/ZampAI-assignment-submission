"""Run against real PostgreSQL, in a fresh private schema per test.

Container: docker compose exec -T app python < backend/tests/test_history_postgres.py
Local pytest skips unless HISTORY_TEST_DATABASE_URL is explicitly configured.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
import hashlib
import os
from pathlib import Path
import threading
import unittest
import uuid
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from reconcile.models import Base, Vendor, PurchaseOrder, POLine, Invoice, InvoiceLine, Allocation
from reconcile.history import identifier_key, find_duplicates, remaining_balance, previous_purchases, approve_invoice, HistoryConflict, rank_previous_purchases


DATABASE=os.getenv('HISTORY_TEST_DATABASE_URL')
if __name__=='__main__':DATABASE=os.getenv('DATABASE_URL')

@unittest.skipUnless(DATABASE,'requires explicitly configured real PostgreSQL integration database')
class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.schema='history_test_'+uuid.uuid4().hex
        self.admin=create_engine(DATABASE)
        self.assertEqual(self.admin.dialect.name,'postgresql')
        with self.admin.begin() as conn:conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        url=make_url(DATABASE).update_query_dict({'options':f'-csearch_path={self.schema}'})
        self.engine=create_engine(url,isolation_level='READ COMMITTED')
        original=os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL']=url.render_as_string(hide_password=False)
        try:
            config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini') if '/backend/tests/' in str(Path(__file__).resolve()) else '/app/backend/alembic.ini')
            command.upgrade(config,'head');command.upgrade(config,'head')
        finally:
            if original is None:os.environ.pop('DATABASE_URL',None)
            else:os.environ['DATABASE_URL']=original
        with Session(self.engine) as s,s.begin():
            vendor=Vendor(legal_name='SafeHands Supplies');s.add(vendor);s.flush()
            po=PurchaseOrder(po_number='PO-2026-0147',vendor_id=vendor.id);s.add(po);s.flush()
            line=POLine(po_id=po.id,line_no=1,item_code='GLV-NIT-M-PF',description='Medium powder-free nitrile gloves',attributes={'material':'nitrile','size':'medium'},uom='EA',ordered_qty=D('1000'),unit_price=D('5'));s.add(line);s.flush()
            self.vendor,self.po,self.line=vendor.id,po.id,line.id

    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as c:c.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        self.admin.dispose()

    def invoice(self,s,number='INV-001',qty='600',state='open',vendor=None,price='5',document=None):
        inv=Invoice(vendor_id=vendor or self.vendor,po_id=self.po,invoice_number=number,invoice_number_key=identifier_key(number),document_sha256=document or hashlib.sha256(number.encode()).hexdigest(),gross_total=D(qty)*D(price),review_state=state,recommendation='ready_for_approval')
        s.add(inv);s.flush()
        s.add(InvoiceLine(invoice_id=inv.id,po_line_id=self.line,normalized_qty=D(qty),normalized_unit_price=D(price),evidence={'page':1,'pack_factor':'100','printed_qty':'6 boxes'}));s.flush()
        return inv.id

    def approve(self,invoice_id):
        try:
            with Session(self.engine) as s,s.begin():return approve_invoice(s,invoice_id,1,'test-approver')['status']
        except HistoryConflict as exc:return exc.code

    def test_migration_repeatable_and_matches_models(self):
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        with self.engine.connect() as c:
            differences=compare_metadata(MigrationContext.configure(c),Base.metadata)
            self.assertEqual(differences,[])

    def test_pending_and_rejected_do_not_consume_balance(self):
        with Session(self.engine) as s,s.begin():
            self.invoice(s,'PENDING');self.invoice(s,'REJECTED',state='rejected')
            self.assertEqual(remaining_balance(s,self.line)['remaining_qty'],D('1000'))

    def test_partial_billing_400_plus_600_and_replay(self):
        with Session(self.engine) as s,s.begin():a=self.invoice(s,'PRIOR',qty='400');b=self.invoice(s,'CURRENT')
        self.assertEqual(self.approve(a),'approved');self.assertEqual(self.approve(b),'approved');self.assertEqual(self.approve(b),'already_approved')
        with Session(self.engine) as s:
            balance=remaining_balance(s,self.line)
            self.assertEqual(balance['approved_qty'],D('1000'));self.assertEqual(balance['remaining_qty'],D('0'));self.assertEqual(balance['remaining_net_amount'],D('0'))
            self.assertEqual(s.scalar(select(func.count()).select_from(Allocation)),2)

    def test_overage_stops_before_writing_any_allocation(self):
        with Session(self.engine) as s,s.begin():a=self.invoice(s,'PRIOR',qty='400');b=self.invoice(s,'EXCESS',qty='700')
        self.assertEqual(self.approve(a),'approved');self.assertEqual(self.approve(b),'APPROVAL_STALE')
        with Session(self.engine) as s:self.assertEqual(remaining_balance(s,self.line)['remaining_qty'],D('600'))

    def test_concurrent_approvals_cannot_overspend(self):
        with Session(self.engine) as s,s.begin():a=self.invoice(s,'COMPETING-A');b=self.invoice(s,'COMPETING-B')
        barrier=threading.Barrier(2)
        def work(i):barrier.wait(timeout=5);return self.approve(i)
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(work,i) for i in [a,b]];results=[f.result(timeout=15) for f in futures]
        self.assertCountEqual(results,['approved','APPROVAL_STALE'])
        with Session(self.engine) as s:self.assertEqual(remaining_balance(s,self.line)['approved_qty'],D('600'))

    def test_simultaneous_repeat_has_one_effect(self):
        with Session(self.engine) as s,s.begin():i=self.invoice(s)
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(self.approve,[i,i]))
        self.assertCountEqual(results,['approved','already_approved'])

    def test_duplicate_file_and_business_identifier(self):
        with Session(self.engine) as s,s.begin():
            self.invoice(s)
            exact=find_duplicates(s,self.vendor,'DIFFERENT',hashlib.sha256(b'INV-001').hexdigest(),D('3000'))
            self.assertEqual(exact[0]['kind'],'exact_file')
            repeat=find_duplicates(s,self.vendor,'INV-001','0'*64,D('3000'))
            self.assertEqual(repeat[0]['kind'],'same_vendor_number')
            changed=find_duplicates(s,self.vendor,'INV-001','0'*64,D('3100'))
            self.assertEqual(changed[0]['kind'],'possible_revision')

    def test_other_vendor_same_number_is_not_duplicate(self):
        with Session(self.engine) as s,s.begin():
            self.invoice(s);v=Vendor(legal_name='Different vendor');s.add(v);s.flush()
            self.assertEqual(find_duplicates(s,v.id,'INV-001','0'*64,D('3000')),[])

    def test_identifier_collision_is_review_not_exact_duplicate(self):
        with Session(self.engine) as s,s.begin():
            self.invoice(s,number='INV-00-1')
            matches=find_duplicates(s,self.vendor,'INV001','0'*64,D('3000'))
            self.assertEqual(matches[0]['kind'],'identifier_collision')
            self.assertNotEqual(identifier_key('INV001'),identifier_key('INV01'))

    def test_duplicate_approval_blocked(self):
        with Session(self.engine) as s,s.begin():
            a=self.invoice(s);self.invoice(s,document='0'*64)
        self.assertEqual(self.approve(a),'DUPLICATE_REVIEW_REQUIRED')

    def test_aggregated_rows_cannot_overdraw(self):
        with Session(self.engine) as s,s.begin():
            i=self.invoice(s)
            s.add(InvoiceLine(invoice_id=i,po_line_id=self.line,normalized_qty=D('600'),normalized_unit_price=D('5'),evidence={'page':1}))
        self.assertEqual(self.approve(i),'APPROVAL_STALE')

    def test_price_conflict_is_not_hidden_by_matching(self):
        with Session(self.engine) as s,s.begin():i=self.invoice(s,price='6')
        self.assertEqual(self.approve(i),'PRICE_CONFLICT')

    def test_blocked_vendor_cannot_be_approved(self):
        with Session(self.engine) as s,s.begin():i=self.invoice(s);s.get(Vendor,self.vendor).status='blocked'
        self.assertEqual(self.approve(i),'VENDOR_NOT_APPROVED')

    def test_stale_decision_version(self):
        with Session(self.engine) as s,s.begin():i=self.invoice(s);s.get(Invoice,i).decision_version=2
        self.assertEqual(self.approve(i),'DECISION_VERSION_CONFLICT')

    def test_historical_candidates_are_vendor_scoped(self):
        with Session(self.engine) as s:
            rows=previous_purchases(s,self.vendor);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['po_number'],'PO-2026-0147')
            self.assertEqual(previous_purchases(s,uuid.uuid4()),[])

    def test_similarity_is_suggestion_not_authorization(self):
        with Session(self.engine) as s:
            ranked=rank_previous_purchases(s,self.vendor,'medium nitrile gloves')
            self.assertEqual(len(ranked),1)
            self.assertFalse(ranked[0]['authorizes_invoice'])
            self.assertGreater(ranked[0]['similarity'],0)
            self.assertEqual(rank_previous_purchases(s,self.vendor,'zzzzzzzz'),[])

if __name__=='__main__':unittest.main(verbosity=2)
