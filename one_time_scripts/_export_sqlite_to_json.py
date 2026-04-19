import json
import logging
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import create_schema
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository


def export_sqlite_to_json() -> None:
    settings = get_settings()
    output_path = Path(settings.export_state_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_schema(settings.database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with session_factory() as session:
        repository = SqliteStateRepository(session)
        state = repository.load_album_state()

    with output_path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2)

    logging.info("Exported album state from %s to %s", settings.database_url, output_path)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    export_sqlite_to_json()


if __name__ == "__main__":
    main()
