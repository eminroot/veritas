"""Engines and sessions.

The engine is synchronous (psycopg 3): request handlers are plain functions that
FastAPI runs in a thread pool. Connections use UTC, so every timestamp leaves
the database the same way whatever the server's time zone is.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str, **kwargs: object) -> Engine:
    connect_args = {"options": "-c timezone=UTC", "application_name": "veritas"}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    # Objects stay readable after commit, so a handler can build its response from them.
    return sessionmaker(engine, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """One unit of work: commit if the body finishes, roll back if it raises."""
    with factory() as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise


def db_now(session: Session) -> datetime:
    """The database clock. Expiry checks compare against it, never the app server's clock.

    It is the start of the current transaction, so every row written in one
    transaction gets the same time.
    """
    return session.scalars(select(func.now())).one()
