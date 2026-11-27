from pathlib import Path
from urllib.parse import unquote, urlsplit

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.util import asbool

from backend.app.config import get_settings


SessionFactory = sessionmaker[Session]


def get_engine(database_url: str | None = None) -> Engine:
    """Create an engine owned by the caller."""
    url = make_url(database_url or get_settings().database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("DATABASE_URL must use SQLite.")

    path = sqlite_file_path(url)
    is_memory = path is None
    if path is not None and not asbool(url.query.get("uri", False)):
        path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(path))

    # A private in-memory database lives on one connection. Lend that
    # connection to one unit of work at a time, including across worker threads.
    options = {"poolclass": QueuePool, "pool_size": 1, "max_overflow": 0} if is_memory else {}
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 60}, **options)
    _configure_sqlite_engine(engine, is_memory=is_memory)
    return engine


def sqlite_file_path(url: URL) -> Path | None:
    database = url.database
    if database in {None, "", ":memory:"}:
        return None
    if asbool(url.query.get("uri", False)) and database.startswith("file:"):
        database = unquote(urlsplit(database).path)
        if database in {"", ":memory:"} or url.query.get("mode") == "memory":
            return None
        return Path(database).resolve()
    return Path(database).expanduser().resolve()


def session_factory_for(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, autoflush=False)


def _configure_sqlite_engine(target_engine: Engine, *, is_memory: bool) -> None:
    @event.listens_for(target_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        if not is_memory:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
