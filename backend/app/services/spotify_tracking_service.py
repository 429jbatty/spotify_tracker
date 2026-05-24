import logging
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

import tracking
import utils as util
from backend.app.album_completion import ALBUM_COMPLETION_THRESHOLD
from backend.app.config import get_settings
from backend.app.database import create_schema
from backend.app.repositories.spotify_credentials_repository import (
    SpotifyCredentialsRepository,
)
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.repositories.user_repository import DEFAULT_USER_SLUG, UserRepository
from spotify_manager import SpotifyAPI


STALE_HOURS = 48

logger = logging.getLogger(__name__)


def run_tracking_for_default_user() -> dict[str, int]:
    return run_tracking_for_user(DEFAULT_USER_SLUG)


def run_tracking_for_all_users() -> dict[str, dict[str, int | str]]:
    session_factory = _session_factory()
    results: dict[str, dict[str, int | str]] = {}

    with session_factory() as session:
        credential_repository = SpotifyCredentialsRepository(session)
        users = credential_repository.users_with_credentials()
        user_slugs = [user.slug for user in users]

    for user_slug in user_slugs:
        try:
            results[user_slug] = run_tracking_for_user(user_slug)
        except Exception as exc:
            logger.exception("Spotify tracking failed for user %s", user_slug)
            _record_sync_error(user_slug, str(exc))
            results[user_slug] = {"error": str(exc)}

    return results


def run_tracking_for_user(user_slug: str) -> dict[str, int]:
    logger.info("=== Album tracking run started for user %s ===", user_slug)

    session_factory = _session_factory()
    with session_factory() as session:
        user = UserRepository(session).require_user_by_slug(user_slug)
        credentials = _credentials_for_user(
            session,
            user.id,
        )
        repository = SqliteStateRepository(session, user_slug=user_slug)
        start_state = repository.load_album_state()

        starting_completed_count = len(start_state.get("completed_albums", {}))
        logger.info("Starting completed albums: %s", starting_completed_count)

        spotify = SpotifyAPI(credentials)
        tracks = spotify.fetch_recent_tracks(start_state["last_checked"])
        logger.info("Fetched %s recent tracks from Spotify", len(tracks))

        clean_up_state = tracking.cleanup_stale_albums(
            start_state,
            max_age_hours=STALE_HOURS,
        )
        updated_tracks_state = tracking.update_album_progress(
            clean_up_state,
            spotify,
            tracks,
        )
        completed_album_ids = tracking.check_album_completion(
            updated_tracks_state,
            threshold=ALBUM_COMPLETION_THRESHOLD,
        )
        logger.info("Newly completed albums from Spotify: %s", len(completed_album_ids))

        newly_completed_albums = {}
        for album_id in completed_album_ids:
            new_entry = tracking.log_completed_album(updated_tracks_state, album_id)
            del updated_tracks_state["albums_in_progress"][album_id]
            newly_completed_albums = {**newly_completed_albums, **new_entry}

        base_state = updated_tracks_state.copy()
        base_state["completed_albums"] = {}
        if tracks:
            base_state["last_checked"] = max(t["played_at"] for t in tracks)

        end_state = base_state.copy()
        end_state["completed_albums"] = util.merge_completed_albums_with_priority(
            start_state=start_state.get("completed_albums", {}),
            updated=newly_completed_albums,
        )
        end_state["most_recently_listened"] = tracking.get_most_recently_listened(
            end_state,
            num=10,
        )

        repository.save_album_state(end_state)
        SpotifyCredentialsRepository(session).record_sync_success(
            user_id=user.id,
            synced_at=_utc_now(),
        )

        final_completed_count = len(end_state["completed_albums"])
        logger.info("Final completed albums after merge: %s", final_completed_count)
        logger.info("=== Album tracking run completed for user %s ===", user_slug)

        return {
            "tracks_fetched": len(tracks),
            "completed_albums": len(completed_album_ids),
            "net_album_count_change": final_completed_count - starting_completed_count,
        }


def _session_factory():
    settings = get_settings()
    engine = create_schema(settings.database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _credentials_for_user(
    session,
    user_id: int,
) -> dict[str, str | None]:
    credential_repository = SpotifyCredentialsRepository(session)
    user_credentials = credential_repository.get_for_user(user_id)
    credentials = _env_credentials()

    if user_credentials:
        credentials["refresh_token"] = user_credentials.refresh_token
    else:
        raise LookupError("Spotify is not connected for this user.")

    if not credentials.get("refresh_token"):
        raise LookupError("Spotify refresh token is missing.")

    return credentials


def _env_credentials() -> dict[str, str | None]:
    return util.get_local_credentials()


def _record_sync_error(user_slug: str, error: str) -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        user = UserRepository(session).get_user_by_slug(user_slug)
        if user is None:
            return
        SpotifyCredentialsRepository(session).record_sync_error(
            user_id=user.id,
            error=error,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
