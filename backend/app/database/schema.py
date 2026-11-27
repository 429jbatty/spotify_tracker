import structlog
from alembic.util import CommandError
from sqlalchemy import Engine
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError

from backend.app.database.migration_runtime import migration_connection, upgrade_database
from backend.app.database.models import User
from backend.app.database.repositories.user_repository import (
    DEFAULT_USER_DISPLAY_NAME,
    DEFAULT_USER_SLUG,
)
from backend.app.persistence_logging import database_error_fields


def initialize_database(engine: Engine) -> None:
    try:
        with migration_connection(engine) as connection:
            upgrade_database(connection)
            with connection.begin():
                connection.execute(
                    insert(User)
                    .values(slug=DEFAULT_USER_SLUG, display_name=DEFAULT_USER_DISPLAY_NAME)
                    .on_conflict_do_nothing(index_elements=[User.slug])
                )
    except (SQLAlchemyError, CommandError, TimeoutError) as exc:
        fields = database_error_fields(exc) or {"database_error_type": type(exc).__name__}
        structlog.get_logger("backend.app.database").error(
            "database_schema_initialization_failed", **fields
        )
        raise
