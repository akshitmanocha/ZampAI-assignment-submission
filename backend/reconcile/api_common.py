"""Transaction and idempotency helpers shared by HTTP operations."""
import hashlib
import json
import uuid
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from reconcile.database import session
from reconcile.models import Submission
from reconcile.errors import AppError, response
from reconcile.pipeline import canonical_hash


def error_body(error, request):
    return json.loads(response(error, request.state.request_id).body)


def mutation(request, body, operation):
    user = request.state.user
    key = request.headers.get('Idempotency-Key', '')
    try:
        uuid.UUID(key)
    except ValueError:
        raise AppError('IDEMPOTENCY_KEY_REQUIRED', 'Send a UUID Idempotency-Key for this action.', 400) from None
    identity = hashlib.sha256((str(user.id) + '\0' + request.url.path + '\0' + key).encode()).hexdigest()
    fingerprint = canonical_hash(body)
    from reconcile.models import Idempotency
    with session() as db, db.begin():
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int(identity[:15], 16)})
        record = db.get(Idempotency, identity)
        if record:
            if record.request_hash != fingerprint:
                raise AppError('IDEMPOTENCY_KEY_REUSED', 'This request key was already used for different inputs.', 422)
            return JSONResponse(record.body, status_code=record.status, headers={'Idempotent-Replayed': 'true'})
        try:
            with db.begin_nested():
                status, result = operation(db, user)
        except AppError as error:
            if error.code in {'RUN_IN_PROGRESS', 'IDEMPOTENCY_IN_PROGRESS'} or error.status >= 500 or error.status == 429:
                raise
            status, result = error.status, error_body(error, request)
        db.add(Idempotency(id=identity, request_hash=fingerprint, status=status, body=result))
    return JSONResponse(result, status_code=status)


def get_submission(db, id, lock=False):
    query = select(Submission).where(Submission.id == id)
    item = db.scalar(query.with_for_update() if lock else query)
    if not item:
        raise AppError('INVOICE_NOT_FOUND', 'This invoice could not be found.', 404)
    return item


def run_json(run):
    return {'id': str(run.id), 'invoice_id': str(run.submission_id), 'run_no': run.run_no,
        'kind': run.kind, 'state': run.state, 'attempt': run.attempt, 'error_code': run.error_code,
        'created_at': run.created_at.isoformat(),
        'finished_at': run.finished_at.isoformat() if run.finished_at else None}
