"""Application shell. Business endpoints remain gated until auth is implemented."""
from pathlib import Path
import os
import subprocess
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text


def create_app():
    app = FastAPI(title='Reconcile', version='0.1.0', docs_url=None, redoc_url=None)

    @app.middleware('http')
    async def security_gate(request: Request, call_next):
        request_id = 'req_' + uuid.uuid4().hex[:12]
        # Fail closed, including future API routes. Login is not exposed until
        # persistent sessions, rate limits, and demo users are implemented.
        if request.url.path == '/api' or request.url.path.startswith('/api/'):
            response = JSONResponse({'error': {'code': 'UNAUTHENTICATED', 'message': 'Sign in to continue.', 'retryable': False, 'request_id': request_id, 'details': {}}}, status_code=401, headers={'WWW-Authenticate': 'Session realm="reconcile"'})
        else:
            response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        return response

    @app.get('/health/live')
    def live():
        return {'status': 'ok'}

    @app.get('/health/ready')
    def ready():
        result = {'db': 'unconfigured', 'migrations': 'not_implemented', 'worker': 'not_implemented', 'ocr': 'unavailable', 'blob_store': 'not_implemented', 'code_version': os.getenv('CODE_VERSION', 'development')}
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            engine = None
            try:
                engine = create_engine(database_url, connect_args={'connect_timeout': 3})
                with engine.connect() as conn:
                    conn.execute(text('SELECT 1'))
                result['db'] = 'ok'
            except Exception:
                result['db'] = 'unavailable'
            finally:
                if engine:
                    engine.dispose()
        try:
            subprocess.run(['tesseract', '--version'], capture_output=True, timeout=5, check=True)
            result['ocr'] = 'ok'
        except (OSError, subprocess.SubprocessError):
            pass
        # A scaffold must not pretend the invoice pipeline is ready.
        return JSONResponse(result, status_code=503)

    static = Path(os.getenv('WEB_DIST', str(Path(__file__).resolve().parents[2] / 'web' / 'dist')))
    if static.is_dir():
        app.mount('/', StaticFiles(directory=static, html=True), name='web')
    return app

app = create_app()
