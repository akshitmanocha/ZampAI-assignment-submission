"""Connection lifecycle shared by API, worker and CLI. No URLs in diagnostics."""
import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@lru_cache(maxsize=1)
def engine():
    return create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True,
                         isolation_level='READ COMMITTED', connect_args={'connect_timeout': 5})


def session():
    return sessionmaker(engine(), expire_on_commit=False)()
