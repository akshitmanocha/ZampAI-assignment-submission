"""Transactional reset of the explicitly enabled fictional demo workspace."""
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import OperationalError
from reconcile.errors import AppError
from reconcile.models import (Allocation, Approval, Audit, Correction, Decision,
    Document, Idempotency, Invoice, InvoiceLine, POLine, PurchaseOrder, Run,
    RunEvent, Submission, Vendor)


def reset_demo(db, actor):
    # Exclude uploads, approvals and worker claims for the whole reset transaction.
    # NOWAIT avoids deadlocks with an operation that already owns a row lock.
    tables = [Run, Submission, RunEvent, Decision, Correction, Audit, Idempotency,
              Allocation, Approval, InvoiceLine, Invoice, POLine, PurchaseOrder,
              Vendor, Document]
    try:
        db.execute(text('LOCK TABLE ' + ', '.join(t.__tablename__ for t in tables)
                        + ' IN EXCLUSIVE MODE NOWAIT'))
    except OperationalError as error:
        if getattr(error.orig, 'sqlstate', None) == '55P03':
            raise AppError('RUN_IN_PROGRESS', 'The demo is busy. Wait for processing to finish, then reset again.', 409, retryable=True) from None
        raise
    if db.scalar(select(func.count()).select_from(Run).where(Run.state.in_(['queued', 'running']))):
        raise AppError('RUN_IN_PROGRESS', 'Wait for all invoices to finish processing before resetting the demo.', 409, retryable=True)
    count = db.scalar(select(func.count()).select_from(Submission))
    db.execute(delete(Audit).where(or_(Audit.submission_id.is_not(None), Audit.action == 'demo.seeded')))
    for model in [Correction, Decision, RunEvent, Run, Submission, Document,
                  Allocation, Approval, InvoiceLine, Invoice, POLine,
                  PurchaseOrder, Vendor]:
        db.execute(delete(model))
    # Keep reset receipts: retrying an old reset must not erase a later demo run.
    # Other old receipts refer to removed invoices and must not be replayed.
    db.execute(delete(Idempotency).where(Idempotency.body['demo_reset'].as_boolean().is_distinct_from(True)))
    from reconcile.cli import seed
    from reconcile.workflows import audit
    seed(db)
    audit(db, actor, 'demo.reset', removed_invoices=count)
    return {'demo_reset': True, 'removed_invoices': count,
            'message': 'Demo reset. Invoice history is empty and starting order balances are restored.'}
