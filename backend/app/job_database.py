"""Database lifetime for standalone jobs that can run before API startup."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from backend.app.database.engine import SessionFactory, get_engine, session_factory_for
from backend.app.database.schema import initialize_database


@contextmanager
def job_session_factory(
    database_url: str | None = None, *, initialize: bool = True,
) -> Iterator[SessionFactory]:
    engine = get_engine(database_url)
    try:
        if initialize:
            initialize_database(engine)
        yield session_factory_for(engine)
    finally:
        engine.dispose()


@contextmanager
def job_session(
    database_url: str | None = None, *, initialize: bool = True,
) -> Iterator[Session]:
    with job_session_factory(database_url, initialize=initialize) as sessions, sessions() as session:
        yield session
