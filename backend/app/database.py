from pathlib import Path

import structlog
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from backend.app.config import get_settings
from backend.app.models import Base, User
from backend.app.persistence_logging import database_error_fields
from backend.app.repositories.user_repository import DEFAULT_USER_DISPLAY_NAME, DEFAULT_USER_SLUG


SessionFactory = sessionmaker[Session]


def get_engine(database_url: str | None = None) -> Engine:
    """Create an engine owned by the caller."""
    url = make_url(database_url or get_settings().database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("DATABASE_URL must use SQLite.")

    is_memory = (
        url.database in {None, "", ":memory:"} or url.query.get("mode") == "memory"
        or url.database == "file::memory:"
    )
    if not is_memory and url.query.get("uri") != "true":
        path = Path(url.database).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(path))

    # A private in-memory database lives on one connection. Lend that
    # connection to one unit of work at a time, including across worker threads.
    options = {"poolclass": QueuePool, "pool_size": 1, "max_overflow": 0} if is_memory else {}
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 60}, **options)
    if not is_memory:
        _configure_sqlite_engine(engine)
    return engine


def session_factory_for(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, autoflush=False)


def _configure_sqlite_engine(target_engine: Engine) -> None:
    @event.listens_for(target_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_schema(database_url: str | None = None) -> Engine:
    target_engine = get_engine(database_url)
    try:
        Base.metadata.create_all(bind=target_engine)
        with target_engine.begin() as connection:
            connection.execute(
                insert(User)
                .values(slug=DEFAULT_USER_SLUG, display_name=DEFAULT_USER_DISPLAY_NAME)
                .on_conflict_do_nothing(index_elements=[User.slug])
            )
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_albums_release_group_mbid "
                "ON albums (release_group_mbid) "
                "WHERE release_group_mbid IS NOT NULL AND release_group_mbid != ''"
            ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_owner_account_id "
                "ON users (owner_account_id) WHERE owner_account_id IS NOT NULL"
            ))
    except SQLAlchemyError as exc:
        structlog.get_logger(__name__).error(
            "database_schema_initialization_failed", **database_error_fields(exc)
        )
        target_engine.dispose()
        raise
    return target_engine
