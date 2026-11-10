"""Disposable browser-test application, isolated from the ordinary company schema."""
import os
import signal
import subprocess
import sys
import threading
import uuid
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url


def main():
    if os.getenv('RECONCILE_BROWSER_FIXTURE')!='true':
        raise SystemExit('This fixture requires explicit RECONCILE_BROWSER_FIXTURE=true')
    base=os.environ['DATABASE_URL']
    schema='browser_test_'+uuid.uuid4().hex
    admin=create_engine(base)
    with admin.begin() as db:db.execute(text(f'CREATE SCHEMA "{schema}"'))
    os.environ['DATABASE_URL']=make_url(base).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    from reconcile.cli import migrate,seed,create_user
    from reconcile.database import session
    migrate()
    with session() as db,db.begin():
        seed(db)
        create_user(db,'browser@test.invalid','Browser test approver','approver','browser-test-only-password-42')
    stop=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stop.set())
    signal.signal(signal.SIGINT,lambda *_:stop.set())
    children=[subprocess.Popen([sys.executable,'-m','reconcile.worker']),
              subprocess.Popen([sys.executable,'-m','uvicorn','reconcile.app:app','--host','0.0.0.0','--port','8000','--no-access-log'])]
    try:
        while not stop.wait(.5):
            if any(p.poll() is not None for p in children):raise RuntimeError('Browser fixture process stopped')
    finally:
        for p in children:p.terminate()
        for p in children:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()
        from reconcile.database import engine
        engine().dispose()
        with admin.begin() as db:db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()

if __name__=='__main__':main()
