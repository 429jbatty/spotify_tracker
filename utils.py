import os
import logging
from dotenv import load_dotenv

from backend.app.job_database import job_session
from backend.app.database.repositories.album_state import AlbumStateRepository
from backend.app.database.repositories.user_repository import UserRepository

load_dotenv()
SOURCE_PRIORITY_BY_PARAM = {"updated": 3, "manual": 2, "start": 1, "google_sheets": 0}


def load_state():
    with job_session() as session:
        user = UserRepository(session).ensure_default_user()
        return AlbumStateRepository(session, user).load()


def save_state(state):
    with job_session() as session:
        user = UserRepository(session).ensure_default_user()
        AlbumStateRepository(session, user).replace(state)


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
                merged[key] = record
                stats["overwritten"] += 1
            else:
                stats["skipped_lower_priority"] += 1

    logging.getLogger(__name__).debug("Album merge summary: %s, total=%s", stats, len(merged))

    return merged
