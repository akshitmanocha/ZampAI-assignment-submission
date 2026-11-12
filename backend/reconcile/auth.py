"""Argon2id passwords and revocable, hashed, server-side 12-hour sessions."""
from datetime import timedelta
import hashlib
import os
import secrets
from pwdlib import PasswordHash
from sqlalchemy import select, func, text
from reconcile.models import User, AuthSession, LoginAttempt, Audit, now
from reconcile.errors import AppError

passwords = PasswordHash.recommended()
# Run the same verification workload for unknown accounts.
dummy_hash = passwords.hash(secrets.token_urlsafe(32))
COOKIE = 'reconcile_session'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def authenticated(db, token):
    if not token:
        return None
    return db.scalar(select(User).join(AuthSession, AuthSession.user_id == User.id).where(
        AuthSession.token_hash == digest(token), AuthSession.expires_at > now(), User.active.is_(True)))


def login(db, email, password, ip):
    email = email.strip().lower()
    subject = digest(ip + '\0' + email)
    error = record_attempt(db, subject)
    if error:
        return None, error
    user = db.scalar(select(User).where(User.email == email))
    valid = passwords.verify(password, user.password_hash if user else dummy_hash)
    if not valid or not user or not user.active:
        db.add(Audit(actor='anonymous', action='auth.login_failed', data={'subject': subject}))
        return None, AppError('INVALID_CREDENTIALS', 'The email or password is incorrect.', 401)
    return start_session(db, user, 'auth.login'), None


def record_attempt(db, subject):
    # Serialise the rolling limit across API processes, without storing raw IPs.
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int(subject[:15], 16)})
    recent = db.scalar(select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.subject == subject, LoginAttempt.created_at > now() - timedelta(minutes=15)))
    if recent >= 10:
        return AppError('RATE_LIMITED', 'Too many sign-in attempts. Try again in 15 minutes.', 429)
    db.add(LoginAttempt(subject=subject))
    return None


def start_session(db, user, action):
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=digest(token), user_id=user.id, expires_at=now() + timedelta(hours=12)))
    db.add(Audit(actor=user.email, action=action, data={}))
    return token


def public_demo_enabled():
    # Opt-in only, and never enable passwordless entry for a non-demo workspace.
    return os.getenv('PUBLIC_DEMO_MODE') == 'true' and os.getenv('SEED_DEMO_DATA') == 'true'


def demo_login(db, token, ip):
    if not public_demo_enabled():
        return None, AppError('NOT_FOUND', 'Public demo access is not enabled.', 404)
    email = os.getenv('INITIAL_APPROVER_EMAIL', '').strip().lower()
    user = db.scalar(select(User).where(User.email == email, User.active.is_(True), User.role == 'approver'))
    if not user:
        return None, AppError('DEMO_UNAVAILABLE', 'The demo workspace is starting. Try again shortly.', 503, retryable=True)
    current = authenticated(db, token)
    if current and current.id == user.id:
        return token, None
    error = record_attempt(db, digest(ip + '\0public-demo'))
    if error:
        return None, error
    return start_session(db, user, 'auth.demo_login'), None


def public_user(user):
    return {'id': str(user.id), 'email': user.email, 'display_name': user.display_name, 'role': user.role}


def require_role(user, *roles):
    if user.role not in roles:
        raise AppError('FORBIDDEN', 'Your role cannot perform this action.', 403)


def secure_cookie():
    return os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
