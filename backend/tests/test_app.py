from fastapi.testclient import TestClient
from reconcile.app import create_app


def test_liveness():
    with TestClient(create_app()) as client:
        assert client.get('/health/live').json() == {'status': 'ok'}


def test_readiness_never_claims_unconfigured_pipeline_ready(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with TestClient(create_app()) as client:
        response = client.get('/health/ready')
        assert response.status_code == 503
        assert response.json()['db'] == 'unconfigured'
        assert response.json()['worker'] == 'unavailable'


def test_all_api_routes_fail_closed():
    with TestClient(create_app()) as client:
        for path in ['/api', '/api/auth/me', '/api/invoices', '/api/unknown', '/api/admin/demo-reset']:
            for method in ['GET', 'POST', 'DELETE']:
                response = client.request(method, path)
                assert response.status_code == 401
                assert response.json()['error']['code'] == 'UNAUTHENTICATED'
                assert response.headers['WWW-Authenticate'] == 'Session realm="reconcile"'
                assert response.headers['X-Content-Type-Options'] == 'nosniff'


def test_backend_serves_built_ui(tmp_path, monkeypatch):
    (tmp_path / 'index.html').write_text('<title>Reconcile</title>')
    monkeypatch.setenv('WEB_DIST', str(tmp_path))
    with TestClient(create_app()) as client:
        assert '<title>Reconcile</title>' in client.get('/').text


def test_public_demo_entry_is_opt_in_and_requires_demo_data(monkeypatch):
    monkeypatch.delenv('PUBLIC_DEMO_MODE', raising=False)
    monkeypatch.delenv('SEED_DEMO_DATA', raising=False)
    with TestClient(create_app()) as client:
        assert client.get('/api/auth/config').json() == {'public_demo': False}
        headers = {'X-Reconcile-Client': 'web'}
        assert client.post('/api/auth/demo', json={}, headers=headers).status_code == 404
        monkeypatch.setenv('PUBLIC_DEMO_MODE', 'true')
        assert client.get('/api/auth/config').json() == {'public_demo': False}
        assert client.post('/api/auth/demo', json={}, headers=headers).status_code == 404
        monkeypatch.setenv('SEED_DEMO_DATA', 'true')
        assert client.get('/api/auth/config').json() == {'public_demo': True}
