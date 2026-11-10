import os
from alembic import context
from sqlalchemy import create_engine
from reconcile.models import Base

url=os.environ['DATABASE_URL']
if context.is_offline_mode():
    context.configure(url=url,target_metadata=Base.metadata,literal_binds=True)
    with context.begin_transaction():context.run_migrations()
else:
    engine=create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn,target_metadata=Base.metadata)
        with context.begin_transaction():context.run_migrations()
    engine.dispose()
