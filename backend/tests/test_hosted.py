import signal
import pytest
from reconcile.database import connection_url
from reconcile.settings import upload_limit, origins
from reconcile import worker


@pytest.mark.parametrize('scheme', ['postgres', 'postgresql', 'postgresql+psycopg'])
def test_managed_database_url_selects_psycopg_and_preserves_tls(scheme):
    url = connection_url(scheme+'://test:test@db.invalid/invoices?sslmode=require')
    assert url.drivername == 'postgresql+psycopg'
    assert url.query['sslmode'] == 'require' and url.database == 'invoices'


@pytest.mark.parametrize('value', ['0', '-1', '10485761', 'not-a-number'])
def test_upload_configuration_cannot_exceed_reader_limits(value):
    with pytest.raises(ValueError):
        upload_limit(value)


def test_hosted_upload_limit_and_local_default(monkeypatch):
    monkeypatch.delenv('MAX_UPLOAD_BYTES', raising=False)
    assert upload_limit() == 10*1024*1024
    monkeypatch.setenv('MAX_UPLOAD_BYTES', str(4*1024*1024))
    assert upload_limit() == 4*1024*1024


def test_hosted_origins_accept_only_configured_platform_hosts(monkeypatch):
    monkeypatch.setenv('APP_ORIGINS', 'https://invoices.example.com')
    monkeypatch.setenv('VERCEL_URL', 'review-example.vercel.app')
    monkeypatch.setenv('VERCEL_PROJECT_PRODUCTION_URL', 'untrusted.example.com')
    assert origins() == {'https://invoices.example.com', 'https://review-example.vercel.app'}


def test_shutdown_finishes_claimed_job_and_does_not_claim_another(monkeypatch):
    handlers = {}
    calls = []
    def register(sig, handler):
        previous = handlers.get(sig)
        handlers[sig] = handler
        return previous
    monkeypatch.setattr(worker.signal, 'signal', register)
    monkeypatch.setattr(worker, 'pulse', lambda: calls.append('heartbeat'))
    monkeypatch.setattr(worker, 'claim', lambda: ('job', 1))
    def process(*_):
        calls.append('start')
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        calls.append('finish')
    monkeypatch.setattr(worker, 'process', process)
    worker.main()
    assert calls == ['heartbeat', 'start', 'finish']
    assert handlers[signal.SIGTERM] is None
