from collections.abc import Generator
from pathlib import Path
from urllib.parse import unquote

from sqlalchemy import event
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


def _is_file_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite:///") and not database_url.endswith("/:memory:")


def get_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    _ensure_sqlite_parent(url)
    connect_args = (
        {"check_same_thread": False, "timeout": 60}
        if url.startswith("sqlite")
        else {}
    )
    target_engine = create_engine(url, connect_args=connect_args)
    if _is_file_sqlite_url(url):
        _configure_sqlite_engine(target_engine)
    return target_engine


def _configure_sqlite_engine(target_engine) -> None:
    @event.listens_for(target_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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
