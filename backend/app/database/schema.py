import structlog
from alembic.util import CommandError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.app.database.migration_runtime import migration_connection, upgrade_database
from backend.app.persistence_logging import database_error_fields


def initialize_database(engine: Engine) -> None:
    try:
        with migration_connection(engine) as connection:
            upgrade_database(connection)
    except (SQLAlchemyError, CommandError, TimeoutError) as exc:
        fields = database_error_fields(exc) or {"database_error_type": type(exc).__name__}
        structlog.get_logger("backend.app.database").error(
            "database_schema_initialization_failed", **fields
        )
        raise
