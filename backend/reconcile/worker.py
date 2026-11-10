"""Durable PostgreSQL queue with leases, fencing and bounded PDF subprocesses."""
from datetime import timedelta
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from sqlalchemy import select, or_, and_
from reconcile.database import session
from reconcile.models import Run, Document, Submission, WorkerHeartbeat, now
from reconcile.workflows import append_event, audit, save_decision
from reconcile.business_validation import from_extraction
from reconcile.pipeline import company_for, evaluate, unsupported_features
from reconcile.retrieval import retrieve

OWNER = 'worker-' + uuid.uuid4().hex


class LostLease(Exception):
    pass


class ProcessingError(Exception):
    def __init__(self, code):
        self.code = code


def fenced(db, run_id, fence):
    run = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if not run or run.state != 'running' or run.owner != OWNER or run.fence != fence or run.lease_until <= now():
        raise LostLease()
    return run


def event(run_id, fence, kind, stage=None, **data):
    with session() as db, db.begin():
        append_event(db, fenced(db, run_id, fence), kind, stage, **data)


def pulse(run_id=None, fence=None):
    with session() as db, db.begin():
        heartbeat = db.get(WorkerHeartbeat, OWNER)
        if heartbeat:
            heartbeat.touched_at = now()
        else:
            db.add(WorkerHeartbeat(id=OWNER))
        if run_id:
            run = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
            if run and run.state == 'running' and run.owner == OWNER and run.fence == fence:
                run.lease_until = now() + timedelta(seconds=60)


def claim():
    with session() as db, db.begin():
        run = db.scalar(select(Run).where(or_(
            and_(Run.state == 'queued', Run.available_at <= now()),
            and_(Run.state == 'running', Run.lease_until < now())))
            .order_by(Run.created_at, Run.id).with_for_update(skip_locked=True).limit(1))
        if not run:
            return None
        if run.attempt >= 3:
            run.state, run.error_code, run.finished_at = 'processing_failed', 'WORKER_ATTEMPTS_EXHAUSTED', now()
            append_event(db, run, 'run.failed', error_code=run.error_code)
            audit(db, 'system', 'run.failed', run.submission_id, error_code=run.error_code)
            return None
        if run.state == 'running':
            append_event(db, run, 'run.lease_recovered', previous_owner=run.owner, previous_attempt=run.attempt)
            audit(db, 'system', 'run.lease_recovered', run.submission_id, run_id=str(run.id))
        run.state, run.owner = 'running', OWNER
        run.attempt += 1
        run.fence += 1
        run.started_at = run.started_at or now()
        run.lease_until = now() + timedelta(seconds=60)
        append_event(db, run, 'run.claimed', attempt=run.attempt, summary='Worker claimed this run')
        return run.id, run.fence


def extract(data, callback):
    environment = {k: os.environ[k] for k in ['PATH', 'LANG', 'PYTHONPATH'] if k in os.environ}
    environment.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', TOKENIZERS_PARALLELISM='false')
    process = subprocess.Popen([sys.executable, '-m', 'reconcile.ingest'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment, start_new_session=True)
    messages = queue.Queue()

    def reader():
        try:
            for line in process.stdout:
                if len(line) > 30 * 1024 * 1024:
                    messages.put({'error': 'EXTRACTION_OUTPUT_LIMIT'})
                    break
                messages.put(json.loads(line))
        except Exception:
            messages.put({'error': 'EXTRACTION_PROTOCOL_ERROR'})
        finally:
            messages.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    # PDFs are bounded to 10 MiB; the child immediately reads this pipe.
    deadline, result = time.monotonic() + 150, None
    try:
        process.stdin.write(data)
        process.stdin.close()
        while time.monotonic() < deadline:
            try:
                item = messages.get(timeout=1)
            except queue.Empty:
                continue
            if item is None:
                break
            if 'error' in item:
                raise ProcessingError(item['error'])
            if 'event' in item:
                callback(item)
            if 'result' in item:
                result = item['result']
        if result is None:
            raise ProcessingError('PDF_PROCESSING_TIMEOUT' if process.poll() is None else 'PDF_PROCESSING_FAILED')
        if process.wait(timeout=5) != 0:
            raise ProcessingError('PDF_PROCESSING_FAILED')
        return result
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        process.stdout.close()


def process(run_id, fence):
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(5):
            try:
                pulse(run_id, fence)
            except Exception:
                pass  # finalization always checks the durable lease/fence

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    stage = 'intake'

    def emit(kind, stage_name, **data):
        event(run_id, fence, kind, stage_name, **data)

    try:
        with session() as db, db.begin():
            run = fenced(db, run_id, fence)
            submission = db.get(Submission, run.submission_id)
            inputs, kind, fingerprint = run.inputs, run.kind, submission.document_hash
            data = db.get(Document, fingerprint).content
        if kind == 'full':
            import hashlib
            emit('stage.started', 'intake', summary='Verifying stored document bytes')
            if hashlib.sha256(data).hexdigest() != fingerprint:
                raise ProcessingError('DOCUMENT_INTEGRITY_FAILED')
            emit('stage.completed', 'intake', summary='Stored bytes verified')
            stage = 'text_layer'

            def child_event(item):
                nonlocal stage
                stage = item['stage']
                emit(item['event'], stage, **item.get('data', {}))

            extraction = extract(data, child_event)
            document = from_extraction(extraction['fields'])
            document['unsupported_features'] = unsupported_features(extraction['pages'])
            reviewed = {}
        else:
            with session() as db:
                base = db.get(Run, uuid.UUID(inputs['base_run_id']))
                extraction = base.extraction
            if not extraction:
                raise ProcessingError('BASE_EXTRACTION_UNAVAILABLE')
            for skipped in ['intake', 'text_layer', 'ocr']:
                emit('stage.skipped', skipped, summary='Reused the original immutable document extraction')
            document, reviewed = inputs['document'], inputs.get('reviewed_lines', {})
            emit('stage.started', 'field_extraction', summary='Applying saved reviewer corrections')
            emit('stage.completed', 'field_extraction', summary='Original readings preserved beside corrections')
        stage = 'normalization'
        emit('stage.started', stage, summary='Preparing decimal values and unit evidence')
        emit('stage.completed', stage, summary='No missing values filled from purchase orders')
        stage = 'vendor_match'
        emit('stage.started', stage, summary='Resolving supplier against company records')
        with session() as db:
            submission = db.get(Submission, run.submission_id)
            company = company_for(db, submission)
        emit('stage.completed', stage, summary='Loaded supplier records from PostgreSQL')
        stage = 'po_match'
        emit('stage.started', stage, summary='Resolving eligible supplier purchase orders')
        from reconcile.business_validation import key
        vendors = [v for v in company['vendors'] if key(v['legal_name']) == key(document.get('vendor_name'))]
        eligible_orders = [p for p in company['purchase_orders'] if len(vendors) == 1 and p['vendor_id'] == vendors[0]['id'] and p['status'] == 'open']
        emit('stage.completed', stage, summary=f'{len(eligible_orders)} open supplier orders loaded; reference evidence checked with policy rules')
        stage = 'line_match'
        emit('stage.started', stage, summary='MiniLM is retrieving supplier-scoped product candidates')
        try:
            candidates = retrieve(document, company)
        except Exception:
            raise ProcessingError('MATCHER_UNAVAILABLE') from None
        emit('stage.completed', stage, summary='Candidate rankings saved; semantic similarity never bypasses business checks', lines=len(candidates['lines']))
        stage = 'policy_checks'
        emit('stage.started', stage, summary='Checking duplicates, specifications, conversions, prices and balances')
        result = evaluate(document, company, fingerprint, reviewed)
        result['retrieval'] = candidates
        result['versions']['code'] = os.getenv('CODE_VERSION', 'development')
        emit('stage.completed', stage, summary=f'{len(result["blocking_rules"])} blockers; {len(result["unknown_rules"])} unresolved checks')
        stage = 'decision'
        emit('stage.started', stage, summary='Combining supported findings into a recommendation')
        emit('stage.completed', stage, summary=result['recommendation'])
        stage = 'finalize'
        emit('stage.started', stage, summary='Saving evidence and a new decision version')
        with session() as db, db.begin():
            run = fenced(db, run_id, fence)
            submission = db.scalar(select(Submission).where(Submission.id == run.submission_id).with_for_update())
            if submission.review_state != 'open':
                raise LostLease()
            save_decision(db, submission, result, run.id)
            run.extraction = extraction
            run.state, run.finished_at, run.lease_until = 'completed', now(), None
            append_event(db, run, 'stage.completed', 'finalize', summary='Evidence and decision saved')
            append_event(db, run, 'run.completed', decision_version=submission.version, recommendation=result['recommendation'])
            audit(db, 'system', 'run.completed', submission.id, run_id=str(run.id), version=submission.version)
    except LostLease:
        pass  # A recovered attempt owns the run; this attempt cannot write.
    except Exception as error:
        code = error.code if isinstance(error, ProcessingError) else 'PROCESSING_INTERNAL_ERROR'
        try:
            with session() as db, db.begin():
                run = fenced(db, run_id, fence)
                append_event(db, run, 'stage.failed', stage, error_code=code)
                retryable = code in ['OCR_UNAVAILABLE', 'MATCHER_UNAVAILABLE', 'PROCESSING_INTERNAL_ERROR'] and run.attempt < 3
                if retryable:
                    run.state, run.available_at = 'queued', now() + timedelta(seconds=2 ** run.attempt)
                    run.lease_until = None
                    append_event(db, run, 'run.retry_scheduled', error_code=code)
                else:
                    run.state, run.error_code, run.finished_at = 'processing_failed', code, now()
                    run.lease_until = None
                    append_event(db, run, 'run.failed', error_code=code)
                    audit(db, 'system', 'run.failed', run.submission_id, error_code=code)
        except LostLease:
            pass
    finally:
        stop.set()
        thread.join(timeout=6)


def main():
    while True:
        try:
            pulse()
            job = claim()
            if job:
                process(*job)
            else:
                time.sleep(.5)
        except KeyboardInterrupt:
            break
        except Exception:
            print('Worker database temporarily unavailable', flush=True)
            time.sleep(2)


if __name__ == '__main__':
    main()
