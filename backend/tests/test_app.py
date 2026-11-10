from fastapi.testclient import TestClient
from reconcile.app import create_app


def test_liveness():
    with TestClient(create_app()) as client:
        assert client.get('/health/live').json() == {'status': 'ok'}


def test_readiness_never_claims_unimplemented_pipeline_ready(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with TestClient(create_app()) as client:
        response = client.get('/health/ready')
        assert response.status_code == 503
        assert response.json()['db'] == 'unconfigured'
        assert response.json()['worker'] == 'not_implemented'


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
