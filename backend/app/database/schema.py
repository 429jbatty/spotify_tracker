import structlog
from sqlalchemy import Engine, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError

from backend.app.database.models import Base, User
from backend.app.database.repositories.user_repository import (
    DEFAULT_USER_DISPLAY_NAME,
    DEFAULT_USER_SLUG,
)
from backend.app.persistence_logging import database_error_fields


def initialize_database(engine: Engine) -> None:
    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as connection:
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
        # Preserve the schema failure logger name across the module move.
        structlog.get_logger("backend.app.database").error(
            "database_schema_initialization_failed", **database_error_fields(exc)
        )
        raise
