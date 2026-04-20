import os
from contextlib import contextmanager
from dotenv import load_dotenv

from sqlalchemy.orm import sessionmaker

from backend.app.config import get_settings
from backend.app.database import create_schema
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository

load_dotenv()
SOURCE_PRIORITY_BY_PARAM = {"updated": 3, "manual": 2, "start": 1, "google_sheets": 0}


def use_sqlite_state():
    return True


def _sqlite_repository():
    settings = get_settings()
    engine = create_schema(settings.database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    return session, SqliteStateRepository(session)


@contextmanager
def sqlite_state_repository():
    session, repository = _sqlite_repository()
    try:
        yield repository
    finally:
        session.close()


def load_state():
    with sqlite_state_repository() as repository:
        return repository.load_album_state()


def save_state(state):
    with sqlite_state_repository() as repository:
        repository.save_album_state(state)


def get_local_credentials():
    return {
        "client_id": os.environ.get("SPOTIFY_CLIENT_ID"),
        "client_secret": os.environ.get("SPOTIFY_CLIENT_SECRET"),
        "redirect_uri": os.environ.get("SPOTIFY_REDIRECT_URI"),
        "refresh_token": None,
    }


def merge_completed_albums_with_priority(start_state, **album_dicts):
    """
    Merge additional album dicts into a starting state using source priority.

    Each kwarg name (e.g. spotify=..., discogs=...) is used to determine
    priority via SOURCE_PRIORITY_BY_PARAM.

    Stats are measured relative to the start_state.
    """

    merged = start_state.copy()

    stats = {
        "added": 0,  # new albums not in start_state
        "overwritten": 0,  # start_state entries replaced by higher priority
        "skipped_lower_priority": 0,
    }

    for param_name, album_dict in album_dicts.items():
        incoming_priority = SOURCE_PRIORITY_BY_PARAM.get(param_name, -1)

        for key, record in album_dict.items():

            if key not in merged:
                merged[key] = record
                stats["added"] += 1
                continue

            existing_record = merged[key]
            existing_source = existing_record.get("source")
            existing_priority = SOURCE_PRIORITY_BY_PARAM.get(existing_source, -1)

            if incoming_priority > existing_priority:
                print(
                    f"[OVERWRITE] {key} | "
                    f"{param_name} ({incoming_priority}) "
                    f"overrode {existing_source} ({existing_priority})"
                )
                merged[key] = record
                stats["overwritten"] += 1

            elif incoming_priority == existing_priority:
                print(
                    f"[EQUAL PRIORITY] {key} | "
                    f"{param_name} ({incoming_priority}) "
                    f"tied with {existing_source} ({existing_priority}) - keeping existing"
                )
                stats["skipped_lower_priority"] += 1

            else:
                print(
                    f"[SKIP] {key} | "
                    f"{param_name} ({incoming_priority}) "
                    f"lost to {existing_source} ({existing_priority})"
                )
                stats["skipped_lower_priority"] += 1

    print("MERGE STATS:", stats)
    print("FINAL TOTAL:", len(merged))

    return merged
