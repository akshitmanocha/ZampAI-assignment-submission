"""Initialize a hosted database once, then run the existing durable worker.

Initialization is serialized on a direct PostgreSQL connection. Repeat startups
retain documents, allocations, passwords and sessions. No secrets enter logs.
"""
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from reconcile.database import connection_url
from reconcile.models import User
from reconcile.cli import seed
from reconcile.workflows import audit

LOCK_ID = 59031601217031


def initial_user(db):
    email = os.getenv('INITIAL_APPROVER_EMAIL', '').strip().lower()
    password_hash = os.getenv('INITIAL_APPROVER_PASSWORD_HASH', '')
    if not email or len(email) > 250 or not password_hash.startswith('$argon2id$'):
        raise ValueError('Configure the initial approver email and Argon2id hash')
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        return  # never rotate passwords or revoke sessions on worker restart
    db.add(User(email=email, display_name='Demo approver', role='approver',
                password_hash=password_hash, active=True))
    audit(db, 'hosted-bootstrap', 'user.provisioned', email=email, role='approver')


def initialize():
    # Session-level migration locks require a direct endpoint, not transaction pooling.
    value = os.getenv('DATABASE_URL_UNPOOLED') or os.environ['DATABASE_URL']
    engine = create_engine(connection_url(value), connect_args={'connect_timeout': 10})
    if engine.dialect.name != 'postgresql':
        raise ValueError('Hosted startup requires PostgreSQL')
    try:
        with engine.connect() as connection:
            connection.execute(text("SET lock_timeout = '60s'"))
            connection.execute(text('SELECT pg_advisory_lock(:id)'), {'id': LOCK_ID})
            connection.commit()
            try:
                config = Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
                config.attributes['connection'] = connection
                command.upgrade(config, 'head')
                connection.commit()
                with Session(bind=connection) as db, db.begin():
                    if os.getenv('SEED_DEMO_DATA') == 'true':
                        seed(db)
                    initial_user(db)
                connection.commit()
            finally:
                connection.rollback()
                connection.execute(text('SELECT pg_advisory_unlock(:id)'), {'id': LOCK_ID})
                connection.commit()
    finally:
        engine.dispose()


def main():
    try:
        initialize()
    except Exception as error:
        print('Hosted initialization failed (' + type(error).__name__ + ')', flush=True)
        raise SystemExit(1) from None
    print('Hosted database initialized; starting invoice worker', flush=True)
    from reconcile.worker import main as worker_main
    worker_main()


if __name__ == '__main__':
    main()
