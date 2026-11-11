"""First and repeated hosted startup against disposable real PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.engine import make_url
from reconcile import database, hosted
from reconcile.app import create_app
from reconcile.auth import passwords
from reconcile.models import User, Approval, AuthSession

DATABASE = os.getenv('APPLICATION_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DATABASE, reason='requires explicit real PostgreSQL application test database')


@pytest.fixture
def hosted_company(monkeypatch):
    schema = 'hosted_test_'+uuid.uuid4().hex
    admin = create_engine(DATABASE)
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(DATABASE).update_query_dict({'options': '-csearch_path='+schema})
    for name in ['DATABASE_URL', 'DATABASE_URL_UNPOOLED']:
        monkeypatch.setenv(name, url.render_as_string(hide_password=False))
    monkeypatch.setenv('SEED_DEMO_DATA', 'true')
    monkeypatch.setenv('INITIAL_APPROVER_EMAIL', 'hosted@test.invalid')
    monkeypatch.setenv('INITIAL_APPROVER_PASSWORD_HASH', passwords.hash('hosted-test-only-password-42'))
    database.engine.cache_clear()
    try:
        yield
    finally:
        database.engine().dispose()
        database.engine.cache_clear()
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_restart_preserves_original_password_session_documents_and_allocations(hosted_company, monkeypatch):
    hosted.initialize()
    with database.session() as db:
        original_hash = db.scalar(select(User.password_hash))
        original_approvals = db.scalar(select(func.count()).select_from(Approval))
    with TestClient(create_app()) as client:
        response = client.post('/api/auth/login', json={'email': 'hosted@test.invalid',
            'password': 'hosted-test-only-password-42'}, headers={'X-Reconcile-Client': 'web'})
        assert response.status_code == 204
        data = (Path(__file__).resolve().parents[1]/'reconcile/demo_samples/happy.pdf').read_bytes()
        uploaded = client.post('/api/invoices', files={'file': ('invoice.pdf', data, 'application/pdf')},
            headers={'X-Reconcile-Client': 'web', 'Idempotency-Key': str(uuid.uuid4())})
        assert uploaded.status_code == 202
        invoice = uploaded.json()['invoice']['id']
        monkeypatch.setenv('INITIAL_APPROVER_PASSWORD_HASH', passwords.hash('another-test-password-42'))
        hosted.initialize()
        assert client.get('/api/invoices').status_code == 200
        assert client.get('/api/invoices/'+invoice+'/document').content == data
        with database.session() as db:
            assert db.scalar(select(User.password_hash)) == original_hash
            assert db.scalar(select(func.count()).select_from(Approval)) == original_approvals == 5
            assert db.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_concurrent_initialization_creates_only_one_user_and_opening_ledger(hosted_company):
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(hosted.initialize) for _ in range(2)]
        for future in futures:
            future.result(timeout=30)
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Approval)) == 5
