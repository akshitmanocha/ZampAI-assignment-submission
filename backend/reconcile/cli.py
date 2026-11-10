"""Local operations: migrate, provision accounts, seed fictional orders and inspect invariants."""
import argparse
from datetime import date
from decimal import Decimal
import getpass
import hashlib
import json
import os
from pathlib import Path
import uuid
from sqlalchemy import select, func, text
from alembic import command
from alembic.config import Config
from reconcile.database import session
from reconcile.models import (User, Vendor, PurchaseOrder, POLine, Invoice, InvoiceLine, Audit,
    Approval, Allocation, Document, Submission, Run, Decision, RunEvent)
from reconcile.auth import passwords
from reconcile.history import approve_invoice, identifier_key, remaining_balance
from reconcile.workflows import audit


def uid(name):
    return uuid.uuid5(uuid.NAMESPACE_URL, 'reconcile-local-demo:' + name)


def migrate():
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini')), 'head')


def seed(db):
    if db.scalar(select(Audit).where(Audit.action == 'demo.seeded').limit(1)):
        for line in db.scalars(select(POLine)):
            po = db.get(PurchaseOrder, line.po_id)
            if po.id == uid(po.po_number) and 'tax_rate' not in line.attributes:
                line.attributes = {**line.attributes, 'tax_rate':'0'}
                po.revision += 1
        return
    for name in ['SafeHands Supplies', 'Brightline Hardware']:
        if not db.get(Vendor, uid(name)):
            db.add(Vendor(id=uid(name), legal_name=name, status='approved'))
    db.flush()
    for number in ['0147', '0148', '0149', '0150', '0151', '0130', '0200']:
        po_number = 'PO-2026-' + number
        if db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number)):
            raise RuntimeError('Demo order conflicts with an existing order; seed an empty demo schema instead')
        vendor = 'Brightline Hardware' if number == '0200' else 'SafeHands Supplies'
        po = PurchaseOrder(id=uid(po_number), po_number=po_number, vendor_id=uid(vendor),
            status='closed' if number == '0130' else 'open', currency='INR', order_date=date(2026, 11, 1))
        db.add(po)
        db.flush()
        items = [('BOLT10', 'Steel bolt M10', 'steel', 'M10', '12.50'), ('NUT10', 'Steel nut M10', 'steel', 'M10', '4')] if number == '0200' else [('GLV-M', 'Nitrile gloves medium', 'nitrile', 'medium', '5')]
        for n, (sku, description, material, size, price) in enumerate(items, 1):
            db.add(POLine(id=uid(po_number + ':' + str(n)), po_id=po.id, line_no=n, item_code=sku,
                description=description, attributes={'material': material, 'size': size, 'tax_rate':'0'}, uom='EA',
                ordered_qty=Decimal('1000'), unit_price=Decimal(price)))
        db.flush()
        if number != '0200' and number != '0130':
            inv = Invoice(id=uid('prior:' + number), vendor_id=po.vendor_id, po_id=po.id,
                invoice_number='PRIOR-' + number, invoice_number_key=identifier_key('PRIOR-' + number),
                document_sha256=hashlib.sha256(('fictional-prior-' + number).encode()).hexdigest(),
                gross_total=Decimal('2000'), recommendation='ready_for_approval')
            db.add(inv)
            db.flush()
            db.add(InvoiceLine(invoice_id=inv.id, po_line_id=uid(po_number + ':1'),
                normalized_qty=Decimal('400'), normalized_unit_price=Decimal('5'),
                evidence={'source': 'explicit fictional opening balance, not extracted invoice'}))
            db.flush()
            approve_invoice(db, inv.id, 1, 'demo-seed')
    audit(db, 'local-cli', 'demo.seeded', description='Fictional company orders and approved opening balances')


def create_user(db, email, name, role, password):
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user:
        user.display_name, user.role, user.password_hash, user.active = name, role, passwords.hash(password), True
        # Changing a password revokes existing sessions.
        from sqlalchemy import delete
        from reconcile.models import AuthSession
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    else:
        db.add(User(email=email, display_name=name, role=role, password_hash=passwords.hash(password)))
    audit(db, 'local-cli', 'user.provisioned', email=email, role=role)


def verify(db):
    violations = []
    for line in db.scalars(select(POLine)):
        if remaining_balance(db, line.id)['remaining_qty'] < 0:
            violations.append('PO quantity overallocated: ' + str(line.id))
    for blob in db.scalars(select(Document)):
        if hashlib.sha256(blob.content).hexdigest() != blob.sha256:
            violations.append('Document hash mismatch: ' + blob.sha256)
    active = db.execute(select(Run.submission_id, func.count()).where(Run.state.in_(['queued','running'])).group_by(Run.submission_id).having(func.count() > 1)).all()
    if active:
        violations.append('Multiple active runs')
    for sub in db.scalars(select(Submission)):
        if sub.version and not db.scalar(select(Decision).where(Decision.submission_id == sub.id, Decision.version == sub.version)):
            violations.append('Missing current decision: ' + str(sub.id))
    return {'ok': not violations, 'violations': violations,
            'counts': {m.__tablename__: db.scalar(select(func.count()).select_from(m)) for m in [Document, Submission, Run, Decision, Approval, Allocation]}}


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='operation', required=True)
    sub.add_parser('migrate')
    sub.add_parser('seed')
    sub.add_parser('verify-db')
    sub.add_parser('latency-report')
    importer = sub.add_parser('import-company')
    importer.add_argument('file', type=Path)
    user = sub.add_parser('user')
    user.add_argument('--email', required=True)
    user.add_argument('--name', default='Local reviewer')
    user.add_argument('--role', choices=['clerk','approver','admin'], default='approver')
    user.add_argument('--password-file', type=Path)
    args = p.parse_args()
    if args.operation == 'migrate':
        migrate()
        return
    with session() as db, db.begin():
        if args.operation == 'import-company':
            from reconcile.company_import import import_company
            import_company(db, json.loads(args.file.read_text()))
            print('Company master records imported; existing ledger effects retained.')
        elif args.operation == 'seed':
            seed(db)
            print('Fictional company data is ready. Existing application records retained.')
        elif args.operation == 'user':
            password = args.password_file.read_text().strip() if args.password_file else getpass.getpass('New password: ')
            if len(password) < 12:
                raise SystemExit('Use at least 12 characters')
            create_user(db, args.email, args.name, args.role, password)
            print('Account saved; existing sessions revoked.')
        elif args.operation == 'verify-db':
            result = verify(db)
            print(json.dumps(result, indent=2))
            if not result['ok']:
                raise SystemExit(1)
        elif args.operation == 'latency-report':
            rows = list(db.scalars(select(Run).where(Run.finished_at.is_not(None))))
            values = sorted((r.finished_at-r.created_at).total_seconds() for r in rows)
            print(json.dumps({'completed_or_failed_runs': len(rows), 'queue_and_run_seconds': {
                'p50': values[len(values)//2] if values else None,
                'p95': values[min(len(values)-1, int(len(values)*.95))] if values else None}}, indent=2))


if __name__ == '__main__':
    main()
