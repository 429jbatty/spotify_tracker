"""Database setup helpers for tests."""

from backend.app.database.engine import get_engine
from backend.app.database.schema import initialize_database


def create_schema(database_url):
    engine = get_engine(database_url)
    try:
        initialize_database(engine)
    except Exception:
        engine.dispose()
        raise
    return engine
