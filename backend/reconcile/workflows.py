"""Persistent workflow operations. Every caller owns a database transaction."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import re
from sqlalchemy import select
from reconcile.models import Run, RunEvent, Decision, Audit, now
from reconcile.errors import AppError
from reconcile.settings import MAX_LINES


def audit(db, actor, action, submission_id=None, **data):
    db.add(Audit(actor=actor, action=action, submission_id=submission_id, data=data))


def latest_run(db, submission_id):
    return db.scalar(select(Run).where(Run.submission_id == submission_id).order_by(Run.run_no.desc()).limit(1))


def current_decision(db, submission):
    return db.scalar(select(Decision).where(Decision.submission_id == submission.id, Decision.version == submission.version))


def append_event(db, run, kind, stage=None, **data):
    if kind == 'stage.completed' and stage:
        started = db.scalar(select(RunEvent).where(RunEvent.run_id == run.id,
            RunEvent.stage == stage, RunEvent.type == 'stage.started').order_by(RunEvent.seq.desc()).limit(1))
        if started:
            data['duration_ms'] = round((now() - started.created_at).total_seconds() * 1000)
    run.event_seq += 1
    db.add(RunEvent(run_id=run.id, seq=run.event_seq, type=kind, stage=stage, data=data))


def enqueue(db, submission, kind='full', inputs=None, actor='system'):
    previous = latest_run(db, submission.id)
    if previous and previous.state in ['queued', 'running']:
        raise AppError('RUN_IN_PROGRESS', 'This invoice is already processing.', retryable=True)
    run = Run(submission_id=submission.id, run_no=previous.run_no + 1 if previous else 1,
              kind=kind, inputs=inputs or {}, state='queued', event_seq=0)
    db.add(run)
    db.flush()
    append_event(db, run, 'run.queued', summary='Waiting for the processing worker')
    audit(db, actor, 'run.queued', submission.id, run_id=str(run.id), kind=kind)
    return run


def summary(db, submission, run=None, decision=None):
    run = run or latest_run(db, submission.id)
    decision = decision or current_decision(db, submission)
    doc = decision.result['document'] if decision else {}
    status = submission.review_state if submission.review_state != 'open' else (
        'processing' if run and run.state in ['queued', 'running'] else
        'processing_failed' if run and run.state == 'processing_failed' else
        decision.result['recommendation'] if decision else 'processing')
    return {'id': str(submission.id), 'display_ref': f'RC-{submission.number:06}',
        'original_filename': submission.filename, 'document_sha256': submission.document_hash,
        'uploaded_at': submission.created_at.isoformat(), 'review_state': submission.review_state,
        'display_status': status, 'decision_version': submission.version,
        'vendor_name': doc.get('vendor_name'), 'invoice_number': doc.get('invoice_number'),
        'po_reference': doc.get('po_reference'), 'grand_total': doc.get('grand_total'),
        'currency': doc.get('currency'), 'latest_run_id': str(run.id) if run else None}


def ensure_open(db, submission, expected_version=None):
    if submission.review_state != 'open':
        raise AppError('INVOICE_CLOSED', 'This invoice has already been approved or rejected.')
    run = latest_run(db, submission.id)
    if run and run.state in ['queued', 'running']:
        raise AppError('RUN_IN_PROGRESS', 'Wait for processing to finish.', retryable=True)
    if expected_version is not None and expected_version != submission.version:
        raise AppError('DECISION_VERSION_CONFLICT', 'The decision changed. Reload before continuing.')
    return run


HEADERS = {'vendor_name', 'invoice_number', 'invoice_date', 'po_reference', 'subtotal', 'tax_total', 'grand_total', 'tax_rate'}
LINE_FIELDS = {'description', 'qty', 'unit_price', 'amount'}
REVIEW_FIELDS = {'pack_factor', 'unit', 'po_line_id'}
NUMERIC = {'subtotal', 'tax_total', 'grand_total', 'qty', 'unit_price', 'amount', 'pack_factor', 'tax_rate'}


def checked_value(field, value):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > (1000 if field == 'description' else 250):
        raise AppError('CORRECTION_INVALID', 'Corrections must be text values within the field limit.', 422)
    value = value.strip()
    if field in NUMERIC:
        if not re.fullmatch(r'\d{1,12}(?:\.\d{1,4})?', value):
            raise AppError('CORRECTION_INVALID', 'Use a nonnegative decimal with at most four decimal places.', 422)
        if field in {'qty', 'pack_factor'} and Decimal(value) <= 0:
            raise AppError('CORRECTION_INVALID', 'Quantity and pack size must be greater than zero.', 422)
    if field == 'tax_rate' and Decimal(value) > 1:
        raise AppError('CORRECTION_INVALID', 'Enter a combined tax fraction, such as 0.18 for 18%.', 422)
    if field == 'invoice_date':
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError('Use the canonical calendar date')
        except ValueError:
            raise AppError('CORRECTION_INVALID', 'Use an invoice date in YYYY-MM-DD format.', 422) from None
    if field == 'unit' and value not in ['EA', 'BOX']:
        raise AppError('CORRECTION_INVALID', 'Choose EA or BOX as the invoice unit.', 422)
    return value


def apply_corrections(document, reviewed_lines, corrections, candidates):
    """Keep original readings immutable; build an explicitly attested new input.

    Whole-row replacement supports OCR table repair; it clears all old identity
    attestations so they cannot silently transfer to different source rows.
    """
    doc, reviews = deepcopy(document), deepcopy(reviewed_lines)
    changes = []
    paths = [c['field_path'] for c in corrections]
    if len(set(paths)) != len(paths):
        raise AppError('CORRECTION_INVALID', 'A field can only be corrected once in a request.', 422)
    for correction in corrections:
        path, value, reason = correction['field_path'], correction['value'], correction['reason'].strip()
        if not 5 <= len(reason) <= 2000:
            raise AppError('CORRECTION_INVALID', 'Explain the evidence for each correction in at least five characters.', 422)
        if path == 'lines':
            if not isinstance(value, list) or not 1 <= len(value) <= MAX_LINES:
                raise AppError('CORRECTION_INVALID', 'Provide between one and 100 item rows.', 422)
            if any(not isinstance(l, dict) or set(l) != LINE_FIELDS for l in value):
                raise AppError('CORRECTION_INVALID', 'Each row needs description, qty, unit_price and amount.', 422)
            replacement = [{k: checked_value(k, v) for k, v in line.items()} for line in value]
            old = doc['lines']
            doc['lines'] = replacement
            reviews = {}
        elif path.startswith('header.') and path[7:] in HEADERS:
            field = path[7:]
            value = checked_value(field, value)
            old = doc.get(field)
            doc[field] = value
            if field in {'vendor_name', 'po_reference'}:
                reviews = {}  # assignments from another supplier/PO are not reusable
        else:
            match = re.fullmatch(r'lines\[([1-9]\d*)\]\.(\w+)', path)
            if not match or match[2] not in LINE_FIELDS | REVIEW_FIELDS or int(match[1]) > len(doc['lines']):
                raise AppError('CORRECTION_INVALID', 'This field cannot be corrected.', 422)
            number, field = int(match[1]), match[2]
            value = checked_value(field, value)
            if field in LINE_FIELDS:
                old = doc['lines'][number - 1].get(field)
                doc['lines'][number - 1][field] = value
                if field == 'description':
                    reviews.pop(str(number), None)
            else:
                review = reviews.setdefault(str(number), {})
                old = review.get(field)
                if field == 'po_line_id' and value:
                    rows = next((l['candidates'] for l in candidates.get('lines', []) if l['source_line'] == number), [])
                    candidate = next((c for c in rows if c['po_line_id'] == value and c['eligible'] and not c['conflicts']), None)
                    if not candidate:
                        raise AppError('CORRECTION_INVALID', 'Choose an eligible displayed item without specification conflicts. Recheck changed descriptions first.', 422)
                if value is None:
                    review.pop(field, None)
                    if field == 'po_line_id':review['none_of_candidates'] = True
                else:
                    review[field] = value
                    if field == 'po_line_id':review.pop('none_of_candidates', None)
                review['reason'] = reason
        changes.append({'field_path': path, 'old_value': old, 'value': value, 'reason': reason})
    # Source fields are never repaired using PO data. Human attestations remain
    # separate and are stamped with actor/time when saved by the API.
    return doc, reviews, changes


def save_decision(db, submission, result, run_id=None, origin='run'):
    submission.version += 1
    decision = Decision(submission_id=submission.id, version=submission.version,
                        run_id=run_id, result=result, origin=origin)
    db.add(decision)
    audit(db, 'system', 'decision.created', submission.id, version=submission.version,
          recommendation=result['recommendation'], origin=origin)
    return decision
