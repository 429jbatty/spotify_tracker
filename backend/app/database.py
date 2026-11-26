from pathlib import Path
from urllib.parse import unquote

import structlog
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import get_settings
from backend.app.models import Base, User
from backend.app.persistence_logging import database_error_fields
from backend.app.repositories.user_repository import DEFAULT_USER_DISPLAY_NAME, DEFAULT_USER_SLUG


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


def create_schema(database_url: str | None = None):
    target_engine = get_engine(database_url) if database_url else engine
    try:
        Base.metadata.create_all(bind=target_engine)
        if target_engine.dialect.name == "sqlite":
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
        raise
    return target_engine
