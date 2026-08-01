"""
DB engine + session factory + the Base class every model inherits from.

Analogy: `engine` is the phone line to Postgres, `SessionLocal` is you
picking up the phone for one conversation (one request), and you hang up
(close the session) when done -- `get_db()` below does that hang-up for
you automatically via FastAPI's dependency injection.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session, always closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()