import json
import logging

from backend.app.config import get_settings
from backend.app.database import create_schema
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from sqlalchemy.orm import sessionmaker


def import_json_to_sqlite() -> None:
    settings = get_settings()
    state_path = settings.state_file

    with open(state_path, "r", encoding="utf-8") as state_file:
        state = json.load(state_file)

    engine = create_schema(settings.database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as session:
        repository = SqliteStateRepository(session)
        repository.import_album_state(state)

    logging.info("Imported album state from %s into %s", state_path, settings.database_url)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    import_json_to_sqlite()


if __name__ == "__main__":
    main()
