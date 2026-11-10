"""Authenticated same-origin API and React application. Never executes payment."""
from datetime import timedelta
from pathlib import Path
import os
import subprocess
import uuid
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func, text, delete
from sqlalchemy.exc import SQLAlchemyError
from reconcile import auth
from reconcile.database import session
from reconcile.errors import AppError, response
from reconcile.models import AuthSession, Document, WorkerHeartbeat, now
from reconcile.settings import MAX_BYTES, origins, model_dir


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    email: str = Field(max_length=250)
    password: str = Field(max_length=1024)


def create_app():
    app = FastAPI(title='Reconcile', version='1.0.0', docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def security(request: Request, call_next):
        request.state.request_id = 'req_' + uuid.uuid4().hex[:12]
        api = request.url.path == '/api' or request.url.path.startswith('/api/')
        try:
            if api:
                if not (request.url.path == '/api/auth/login' and request.method == 'POST'):
                    token = request.cookies.get(auth.COOKIE)
                    if not token:
                        raise AppError('UNAUTHENTICATED', 'Sign in to continue.', 401)
                    with session() as db:
                        user = auth.authenticated(db, token)
                    if not user:
                        raise AppError('UNAUTHENTICATED', 'Your session expired. Sign in again.', 401)
                    request.state.user = user
                if request.method not in ['GET', 'HEAD', 'OPTIONS']:
                    if request.headers.get('X-Reconcile-Client') != 'web':
                        raise AppError('CSRF_HEADER_MISSING', 'The required client header is missing.', 403)
                    origin = request.headers.get('Origin')
                    if origin and origin.rstrip('/') not in origins():
                        raise AppError('ORIGIN_FORBIDDEN', 'This origin is not allowed.', 403)
                    length = request.headers.get('Content-Length')
                    if length is None:
                        raise AppError('CONTENT_LENGTH_REQUIRED', 'Send Content-Length with this request.', 411)
                    maximum = MAX_BYTES + 65536 if request.url.path == '/api/invoices' else 256 * 1024
                    if not length.isdigit() or int(length) > maximum:
                        raise AppError('REQUEST_TOO_LARGE', 'The request exceeds the allowed size.', 413)
            result = await call_next(request)
        except AppError as error:
            result = response(error, request.state.request_id)
        except SQLAlchemyError:
            result = response(AppError('DATABASE_UNAVAILABLE', 'The database is temporarily unavailable. Retry shortly.', 503, retryable=True), request.state.request_id)
        result.headers['X-Request-ID'] = request.state.request_id
        result.headers['X-Content-Type-Options'] = 'nosniff'
        result.headers['Referrer-Policy'] = 'same-origin'
        result.headers['X-Frame-Options'] = 'DENY'
        result.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if api:
            result.headers['Cache-Control'] = 'private, no-store'
        return result

    @app.exception_handler(AppError)
    async def handle_error(request, error):
        return response(error, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return response(AppError('INVALID_REQUEST', 'Check the request fields and their types.', 422), request.state.request_id)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, error):
        return response(AppError('NOT_FOUND' if error.status_code == 404 else 'HTTP_ERROR',
            'The requested resource or method is not available.', error.status_code), request.state.request_id)

    @app.get('/health/live')
    def live():
        return {'status': 'ok'}

    @app.get('/health/ready')
    def ready():
        checks = {'db': 'unconfigured', 'migrations': 'unavailable', 'worker': 'unavailable',
                  'ocr': 'unavailable', 'blob_store': 'unavailable', 'matcher': 'unavailable',
                  'code_version': os.getenv('CODE_VERSION', 'development')}
        if os.getenv('DATABASE_URL'):
            try:
                with session() as db:
                    db.execute(text('SELECT 1'))
                    checks['db'] = 'ok'
                    revision = db.scalar(text('SELECT version_num FROM alembic_version'))
                    checks['migrations'] = 'at_head' if revision == '0002_application' else 'behind'
                    beat = db.scalar(select(func.max(WorkerHeartbeat.touched_at)))
                    checks['worker'] = 'ok' if beat and (now() - beat).total_seconds() < 30 else 'unavailable'
                    checks['worker_heartbeat_age_s'] = round((now() - beat).total_seconds(), 1) if beat else None
                    db.execute(select(Document.sha256).limit(1))
                    checks['blob_store'] = 'ok'
            except SQLAlchemyError:
                pass
        try:
            subprocess.run(['tesseract', '--version'], capture_output=True, timeout=3, check=True)
            checks['ocr'] = 'ok'
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            from reconcile.retrieval import encoder
            encoder(str(model_dir()))
            checks['matcher'] = 'ok'
        except Exception:
            pass
        success = all(checks[k] == v for k, v in {'db': 'ok', 'migrations': 'at_head', 'worker': 'ok', 'ocr': 'ok', 'blob_store': 'ok', 'matcher': 'ok'}.items())
        return JSONResponse(checks, status_code=200 if success else 503)

    @app.post('/api/auth/login')
    def login(body: Login, request: Request):
        with session() as db, db.begin():
            token, error = auth.login(db, body.email, body.password, request.client.host if request.client else 'unknown')
        if error:
            raise error
        result = Response(status_code=204)
        result.set_cookie(auth.COOKIE, token, max_age=43200, httponly=True, secure=auth.secure_cookie(), samesite='lax', path='/api')
        return result

    @app.get('/api/auth/me')
    def me(request: Request):
        return auth.public_user(request.state.user)

    @app.post('/api/auth/logout')
    def logout(request: Request):
        with session() as db, db.begin():
            db.execute(delete(AuthSession).where(AuthSession.token_hash == auth.digest(request.cookies[auth.COOKIE])))
        result = Response(status_code=204)
        result.delete_cookie(auth.COOKIE, path='/api')
        return result

    from reconcile.invoice_api import router
    app.include_router(router)
    static = Path(os.getenv('WEB_DIST', str(Path(__file__).resolve().parents[2] / 'web/dist')))
    if static.is_dir():
        app.mount('/', StaticFiles(directory=static, html=True), name='web')
    return app


app = create_app()
