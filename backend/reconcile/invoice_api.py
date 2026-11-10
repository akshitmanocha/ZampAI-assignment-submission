"""Invoice, evidence, review, approval and ledger HTTP routes."""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
import base64
import hashlib
import json
import uuid
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func, text, case
from reconcile import auth
from reconcile.database import session
from reconcile.errors import AppError
from reconcile.models import (Submission, Document, Run, RunEvent, Decision, Correction, Audit,
    Vendor, PurchaseOrder, POLine, Invoice, InvoiceLine, now)
from reconcile.workflows import (summary, latest_run, current_decision, enqueue, ensure_open,
    apply_corrections, audit, save_decision)
from reconcile.settings import MAX_BYTES, POLICY, STAGES
from reconcile.pipeline import canonical_hash, company_for, evaluate
from reconcile.history import approve_invoice, identifier_key, remaining_balance, HistoryConflict
from reconcile.api_common import mutation, get_submission, run_json, error_body

router = APIRouter()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Change(StrictModel):
    field_path: str = Field(max_length=150)
    value: Any
    reason: str = Field(min_length=5, max_length=2000)


class Review(StrictModel):
    expected_decision_version: int = Field(ge=1)
    corrections: list[Change] = Field(max_length=500)


class Approve(StrictModel):
    expected_decision_version: int = Field(ge=1)


class Reject(Approve):
    reason: str = Field(min_length=5, max_length=2000)


@router.post('/api/invoices')
async def upload(request: Request, file: UploadFile = File()):
    auth.require_role(request.state.user, 'clerk', 'approver')
    if file.content_type not in ['application/pdf', 'application/octet-stream']:
        raise AppError('UNSUPPORTED_MEDIA_TYPE', 'Upload a PDF document.', 415)
    data = await file.read(MAX_BYTES + 1)
    await file.close()
    if len(data) > MAX_BYTES:
        raise AppError('PDF_TOO_LARGE', 'The PDF must be at most 10 MiB.', 413)
    if not data.startswith(b'%PDF-'):
        raise AppError('PDF_INVALID', 'This file does not contain a PDF header.', 422)
    fingerprint = hashlib.sha256(data).hexdigest()
    filename = Path((file.filename or 'invoice.pdf').replace('\\', '/')).name[:250]

    def operation(db, user):
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int(fingerprint[:15], 16)})
        count = db.scalar(select(func.count()).select_from(Submission).where(Submission.uploaded_by == user.id, Submission.created_at > now() - timedelta(hours=1)))
        if count >= 60:
            raise AppError('RATE_LIMITED', 'The upload limit is 60 documents per hour.', 429)
        if not db.get(Document, fingerprint):
            db.add(Document(sha256=fingerprint, content=data))
            db.flush()
        sub = Submission(document_hash=fingerprint, filename=filename, uploaded_by=user.id)
        db.add(sub)
        db.flush()
        run = enqueue(db, sub, actor=user.email)
        audit(db, user.email, 'invoice.uploaded', sub.id, sha256=fingerprint, filename=filename)
        return 202, {'invoice': summary(db, sub, run), 'run': run_json(run)}
    return mutation(request, {'sha256': fingerprint, 'filename': filename}, operation)


@router.get('/api/invoices')
def invoices(request: Request, status: str | None = None, q: str = '', limit: int = 25, offset: int = 0):
    if not 1 <= limit <= 100 or offset < 0 or len(q) > 250:
        raise AppError('INVALID_FILTER', 'Use a page size from 1 to 100 and a valid search.', 422)
    with session() as db:
        latest = select(Run).distinct(Run.submission_id).order_by(Run.submission_id, Run.run_no.desc()).subquery()
        display = case((Submission.review_state != 'open', Submission.review_state),
            (latest.c.state.in_(['queued', 'running']), 'processing'),
            (latest.c.state == 'processing_failed', 'processing_failed'), else_=Decision.result['recommendation'].as_string())
        query = select(Submission, Run, Decision).outerjoin(latest, latest.c.submission_id == Submission.id).outerjoin(Run, Run.id == latest.c.id).outerjoin(Decision,
            (Decision.submission_id == Submission.id) & (Decision.version == Submission.version))
        if q:
            pattern = '%' + q.replace('%', '\\%').replace('_', '\\_') + '%'
            query = query.where(Submission.filename.ilike(pattern) | Decision.result['document']['invoice_number'].as_string().ilike(pattern) | Decision.result['document']['vendor_name'].as_string().ilike(pattern))
        counts = dict(db.execute(select(display, func.count()).select_from(Submission).outerjoin(latest, latest.c.submission_id == Submission.id).outerjoin(Decision,
            (Decision.submission_id == Submission.id) & (Decision.version == Submission.version)).group_by(display)).all())
        if status:
            if status not in ['processing', 'processing_failed', 'ready_for_approval', 'needs_review', 'hold', 'approved', 'rejected']:
                raise AppError('INVALID_FILTER', 'Choose a recognised invoice status.', 422)
            query = query.where(display == status)
        rows = db.execute(query.order_by(Submission.created_at.desc(), Submission.id.desc()).limit(limit + 1).offset(offset)).all()
        items = [summary(db, sub, run, decision) for sub, run, decision in rows[:limit]]
        return {'items': items, 'counts': counts, 'next_offset': offset + limit if len(rows) > limit else None}


@router.get('/api/runs/{id}')
def get_run(id: uuid.UUID, request: Request, after_seq: int = 0):
    with session() as db:
        run = db.get(Run, id)
        if not run:
            raise AppError('RUN_NOT_FOUND', 'This processing run could not be found.', 404)
        events = db.scalars(select(RunEvent).where(RunEvent.run_id == id, RunEvent.seq > after_seq).order_by(RunEvent.seq))
        return {**run_json(run), 'stages': STAGES, 'events': [{'seq': e.seq, 'type': e.type, 'stage': e.stage,
            'created_at': e.created_at.isoformat(), 'data': e.data} for e in events]}


@router.get('/api/invoices/{id}')
def invoice(id: uuid.UUID, request: Request):
    with session() as db:
        sub = get_submission(db, id)
        run, decision = latest_run(db, id), current_decision(db, sub)
        original = db.scalar(select(Run).where(Run.submission_id == id, Run.extraction.is_not(None)).order_by(Run.run_no).limit(1))
        stale = False
        if decision and decision.result['bucket'] == 'accept':
            fresh = evaluate(decision.result['document'], company_for(db, sub), sub.document_hash, decision.result.get('reviewed_lines'))
            stale = fresh['inputs_fingerprint'] != decision.result['inputs_fingerprint']
        history = db.scalars(select(Decision).where(Decision.submission_id == id).order_by(Decision.version.desc()))
        corrections = db.scalars(select(Correction).where(Correction.submission_id == id).order_by(Correction.created_at))
        entries = db.scalars(select(Audit).where(Audit.submission_id == id).order_by(Audit.created_at))
        return {'invoice': summary(db, sub, run, decision), 'run': run_json(run) if run else None,
            'decision': {'version': decision.version, 'created_at': decision.created_at.isoformat(), 'origin': decision.origin, **decision.result} if decision else None,
            'extraction': {'fields': original.extraction['fields'], 'pages': [{k: v for k, v in p.items() if k != 'words'} for p in original.extraction['pages']]} if original else None,
            'is_stale': stale,
            'decisions': [{'version': d.version, 'origin': d.origin, 'created_at': d.created_at.isoformat(), 'recommendation': d.result['recommendation'], 'blocking_rules': d.result['blocking_rules']} for d in history],
            'runs': [run_json(r) for r in db.scalars(select(Run).where(Run.submission_id == id).order_by(Run.run_no.desc()))],
            'corrections': [{'field_path': c.field_path, 'old_value': c.old_value, 'value': c.value, 'reason': c.reason, 'actor_id': str(c.actor_id), 'created_at': c.created_at.isoformat()} for c in corrections],
            'audit': [{'action': e.action, 'actor': e.actor, 'created_at': e.created_at.isoformat(), 'data': e.data} for e in entries]}


@router.get('/api/invoices/{id}/document')
def document(id: uuid.UUID, request: Request):
    with session() as db:
        sub = get_submission(db, id)
        return Response(db.get(Document, sub.document_hash).content, media_type='application/pdf',
                        headers={'Content-Disposition': 'attachment; filename="invoice.pdf"'})


@router.get('/api/invoices/{id}/pages/{page}')
def page_preview(id: uuid.UUID, page: int, request: Request):
    with session() as db:
        get_submission(db, id)
        run = db.scalar(select(Run).where(Run.submission_id == id, Run.extraction.is_not(None)).order_by(Run.run_no).limit(1))
        if not run or not 1 <= page <= len(run.extraction.get('previews', [])):
            raise AppError('PAGE_NOT_FOUND', 'This page preview is not available.', 404)
        return Response(base64.b64decode(run.extraction['previews'][page - 1]), media_type='image/png')


@router.post('/api/invoices/{id}/review')
def review(id: uuid.UUID, body: Review, request: Request):
    auth.require_role(request.state.user, 'clerk', 'approver')
    def operation(db, user):
        sub = get_submission(db, id, True)
        previous = ensure_open(db, sub, body.expected_decision_version)
        if previous and previous.state == 'processing_failed':
            raise AppError('LATEST_RUN_FAILED', 'Retry the failed check first so its saved corrections are evaluated.')
        decision = current_decision(db, sub)
        if not decision:
            raise AppError('NOT_REVIEWABLE', 'Process the document before making corrections.')
        doc, reviews, changes = apply_corrections(decision.result['document'], decision.result.get('reviewed_lines', {}),
            [c.model_dump() for c in body.corrections], decision.result.get('retrieval', {}))
        touched = {c['field_path'].split(']')[0][6:] for c in changes if c['field_path'].startswith('lines[')}
        for number, line in reviews.items():
            if number in touched:
                line.update(actor=user.email, attested_at=now().isoformat())
        base = db.scalar(select(Run).where(Run.submission_id == id, Run.extraction.is_not(None)).order_by(Run.run_no).limit(1))
        run = enqueue(db, sub, 'revalidate', {'document': doc, 'reviewed_lines': reviews, 'base_run_id': str(base.id)}, user.email)
        for change in changes:
            db.add(Correction(submission_id=id, run_id=run.id, actor_id=user.id, **change))
            audit(db, user.email, 'correction.saved', id, field_path=change['field_path'], reason=change['reason'])
        return 202, {'run': run_json(run)}
    return mutation(request, body.model_dump(), operation)


@router.post('/api/invoices/{id}/retry')
def retry(id: uuid.UUID, request: Request):
    auth.require_role(request.state.user, 'clerk', 'approver')
    def operation(db, user):
        sub = get_submission(db, id, True)
        run = ensure_open(db, sub)
        if not run or run.state != 'processing_failed':
            raise AppError('RETRY_NOT_ALLOWED', 'Only failed processing runs can be retried.')
        new = enqueue(db, sub, run.kind, run.inputs, user.email)
        return 202, {'run': run_json(new)}
    return mutation(request, {}, operation)


@router.post('/api/invoices/{id}/reject')
def reject(id: uuid.UUID, body: Reject, request: Request):
    auth.require_role(request.state.user, 'clerk', 'approver')
    def operation(db, user):
        sub = get_submission(db, id, True)
        ensure_open(db, sub, body.expected_decision_version)
        sub.review_state = 'rejected'
        audit(db, user.email, 'invoice.rejected', id, reason=body.reason)
        return 200, {'status': 'rejected', 'invoice_id': str(id)}
    return mutation(request, body.model_dump(), operation)


@router.post('/api/invoices/{id}/approve')
def approve(id: uuid.UUID, body: Approve, request: Request):
    auth.require_role(request.state.user, 'approver')
    def operation(db, user):
        sub = get_submission(db, id, True)
        if sub.review_state == 'approved':
            audit(db, user.email, 'approval.replayed', id)
            return 200, {'status': 'already_approved', 'invoice_id': str(id)}
        run = ensure_open(db, sub, body.expected_decision_version)
        decision = current_decision(db, sub)
        if not decision or not run or run.state != 'completed' or decision.result['bucket'] != 'accept':
            raise AppError('NOT_APPROVABLE', 'The latest completed check must be ready for approval.')
        prior = decision.result
        po_id = uuid.UUID(prior['po_id'])
        po = db.get(PurchaseOrder, po_id)
        db.scalar(select(Vendor).where(Vendor.id == po.vendor_id).with_for_update())
        db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po_id).with_for_update().execution_options(populate_existing=True))
        list(db.scalars(select(POLine).where(POLine.po_id == po_id).order_by(POLine.id).with_for_update()))
        company = company_for(db, sub)
        identity = lambda c: {'vendors': c['vendors'], 'purchase_orders': c['purchase_orders']}
        if canonical_hash(identity(company)) != canonical_hash(identity(prior['company_snapshot'])) or prior['policy'] != POLICY:
            base = db.scalar(select(Run).where(Run.submission_id == id, Run.extraction.is_not(None)).order_by(Run.run_no).limit(1))
            queued = enqueue(db, sub, 'revalidate', {'document': prior['document'], 'reviewed_lines': prior.get('reviewed_lines', {}), 'base_run_id': str(base.id)}, 'system')
            audit(db, user.email, 'approval.stale', id, reason='master_data_changed')
            return 409, error_body(AppError('APPROVAL_STALE', 'Company records changed. A fresh check has been queued.', details={'run_id': str(queued.id)}), request)
        fresh = evaluate(prior['document'], company, sub.document_hash, prior.get('reviewed_lines'))
        fresh['retrieval'] = prior['retrieval']
        if fresh['bucket'] != 'accept':
            save_decision(db, sub, fresh, origin='approval_check')
            audit(db, user.email, 'approval.stale', id, reason='current_rules_failed', version=sub.version)
            return 409, error_body(AppError('APPROVAL_STALE', 'The current balance or duplicate check changed. Review the new decision.'), request)
        doc = fresh['document']
        invoice = Invoice(vendor_id=po.vendor_id, po_id=po.id, invoice_number=doc['invoice_number'],
            invoice_number_key=identifier_key(doc['invoice_number']), document_sha256=sub.document_hash,
            currency=doc['currency'], gross_total=Decimal(doc['grand_total']), recommendation='ready_for_approval',
            decision_version=sub.version, validation_policy=POLICY)
        db.add(invoice)
        db.flush()
        for line in fresh['normalized_lines']:
            db.add(InvoiceLine(invoice_id=invoice.id, po_line_id=uuid.UUID(line['po_line_id']),
                normalized_qty=Decimal(line['qty']), normalized_unit_price=Decimal(line['unit_price']),
                evidence={**line['evidence'], 'decision_version': sub.version, 'document_sha256': sub.document_hash}))
        db.flush()
        try:
            result = approve_invoice(db, invoice.id, sub.version, user.email)
        except HistoryConflict as error:
            raise AppError(error.code, 'Approval checks changed. Recheck the invoice before continuing.') from None
        sub.ledger_invoice_id, sub.review_state = invoice.id, 'approved'
        audit(db, user.email, 'approval.approved', id, approval_id=result['approval_id'], version=sub.version,
              policy=POLICY['version'], checked_fingerprint=fresh['inputs_fingerprint'])
        return 200, {**result, 'invoice_id': str(id)}
    return mutation(request, body.model_dump(), operation)


@router.get('/api/purchase-orders')
def purchase_orders(request: Request):
    with session() as db:
        rows = []
        for po, vendor in db.execute(select(PurchaseOrder, Vendor).join(Vendor, Vendor.id == PurchaseOrder.vendor_id).order_by(PurchaseOrder.po_number)):
            lines = []
            for line in db.scalars(select(POLine).where(POLine.po_id == po.id).order_by(POLine.line_no)):
                balance = remaining_balance(db, line.id)
                lines.append({'id': str(line.id), 'sku': line.item_code, 'description': line.description,
                    'unit_price': str(line.unit_price), 'uom': line.uom, **{k: str(v) for k, v in balance.items()}})
            rows.append({'id': str(po.id), 'number': po.po_number, 'vendor': vendor.legal_name, 'status': po.status,
                         'currency': po.currency, 'lines': lines})
        return {'items': rows}


@router.get('/api/benchmarks')
def benchmarks(request: Request):
    path = Path(__file__).with_name('benchmark_summary.json')
    return json.loads(path.read_text()) if path.exists() else {'source': 'saved', 'note': 'Reports are in the repository documentation.'}


@router.get('/api/samples')
def samples(request: Request):
    path = Path(__file__).with_name('demo_samples') / 'manifest.json'
    return json.loads(path.read_text()) if path.exists() else []


@router.get('/api/samples/{name}')
def sample(name: str, request: Request):
    root = Path(__file__).with_name('demo_samples')
    manifest = json.loads((root / 'manifest.json').read_text()) if (root / 'manifest.json').exists() else []
    item = next((s for s in manifest if s['name'] == name), None)
    if not item:
        raise AppError('SAMPLE_NOT_FOUND', 'This sample could not be found.', 404)
    return Response((root / item['file']).read_bytes(), media_type='application/pdf',
                    headers={'Content-Disposition': 'attachment; filename="' + item['file'] + '"'})


@router.get('/api/admin/diagnostics')
def diagnostics(request: Request):
    auth.require_role(request.state.user, 'admin')
    with session() as db:
        return {'submissions': db.scalar(select(func.count()).select_from(Submission)),
            'active_runs': db.scalar(select(func.count()).select_from(Run).where(Run.state.in_(['queued', 'running']))),
            'failed_runs': db.scalar(select(func.count()).select_from(Run).where(Run.state == 'processing_failed')),
            'database_bytes': db.scalar(text('SELECT pg_database_size(current_database())')),
            'recent_audit': [{'action': a.action, 'actor': a.actor, 'created_at': a.created_at.isoformat()} for a in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(25))]}
