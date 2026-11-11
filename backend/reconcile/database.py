"""Connection lifecycle shared by API, worker and CLI. No URLs in diagnostics."""
import os
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


def connection_url(value=None):
    """Accept managed-provider URLs while explicitly selecting psycopg 3."""
    url = make_url(value if value is not None else os.environ['DATABASE_URL'])
    if url.drivername in {'postgres', 'postgresql'}:
        url = url.set(drivername='postgresql+psycopg')
    return url


@lru_cache(maxsize=1)
def engine():
    return create_engine(connection_url(), pool_pre_ping=True,
                         isolation_level='READ COMMITTED', connect_args={'connect_timeout': 5})


def session():
    return sessionmaker(engine(), expire_on_commit=False)()
