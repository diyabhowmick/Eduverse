from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

import os

# Requests run on a pool of THREADS threads. Each one may hold a database connection, so the pool must have at least
# as many connections as there are threads. With FastAPI's default 40 threads and SQLAlchemy's default 15
# connections, about 40 students acting at once froze the whole server: threads waited for a connection while the
# requests holding one waited for a free thread to finish. Everything stopped for 30 seconds, then failed.
THREADS = int(os.getenv("THREADS", "32"))
kw = {"connect_args": {"check_same_thread": False, "timeout": 30}} if settings.database_url.startswith("sqlite") else {
    "pool_pre_ping": True,
    "pool_size": int(os.getenv("DB_POOL_SIZE", str(THREADS))),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "8")),   # background work (task loop, explanations) on top
    "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "10")),
    "pool_recycle": 1800,
}
engine = create_engine(settings.database_url, **kw)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
