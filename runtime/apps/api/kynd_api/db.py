"""Database session management.

One engine per process, one session per request. The session is committed by
the route handler explicitly — never implicitly on teardown, because an
implicit commit turns a half-finished failed request into a partially applied
write.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,  # a connection killed by the DB is detected, not returned
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed.

    Rolls back on exception so a failed request cannot leak a dirty session
    back into the pool.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
