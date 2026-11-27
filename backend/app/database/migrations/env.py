from alembic import context
from alembic.util import CommandError
from sqlalchemy import Connection

from backend.app.database.engine import get_engine
from backend.app.database.migration_runtime import migration_connection
from backend.app.database.models import Base


def run_migrations(connection: Connection) -> None:
    # sqlite3's legacy transaction mode does not BEGIN for DDL. Put the
    # schema changes and Alembic's revision updates in the same transaction.
    with connection.begin():
        connection.exec_driver_sql("BEGIN")
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=True,
            transactional_ddl=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise CommandError("Albumary migrations require a live SQLite connection.")

connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    engine = get_engine()
    try:
        with migration_connection(engine) as connection:
            run_migrations(connection)
    finally:
        engine.dispose()
