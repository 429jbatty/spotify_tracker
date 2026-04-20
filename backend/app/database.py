from collections.abc import Generator
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import get_settings
from backend.app.migrations import run_sqlite_migrations
from backend.app.models import Base


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    raw_path = unquote(database_url.removeprefix("sqlite:///"))
    database_path = raw_path
    if not database_path or database_path == ":memory:":
        return

    Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def get_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    _ensure_sqlite_parent(url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_schema(database_url: str | None = None):
    target_engine = get_engine(database_url) if database_url else engine
    Base.metadata.create_all(bind=target_engine)
    run_sqlite_migrations(target_engine)
    return target_engine


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
