from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timezone
import time
import uuid

import structlog
from requests.exceptions import Timeout as RequestsTimeout
from spotipy.exceptions import SpotifyException
from structlog.contextvars import bind_contextvars, bound_contextvars

from sqlalchemy.orm import Session

import tracking
import utils as util
from backend.app.album_completion import ALBUM_COMPLETION_THRESHOLD
from backend.app.job_database import job_session, job_session_factory
from backend.app.persistence_logging import database_error_fields
from backend.app.database.repositories.spotify_credentials_repository import (
    SpotifyCredentialsRepository,
)
from backend.app.database.repositories.album_state import AlbumStateRepository
from backend.app.database.repositories.user_repository import DEFAULT_USER_SLUG, UserRepository
from backend.app.services.spotify_access_service import require_spotify_sync_access
from spotify_manager import SpotifyAPI


STALE_HOURS = 48

logger = structlog.get_logger(__name__)


def run_tracking_for_default_user() -> dict[str, int]:
    return run_tracking_for_user(DEFAULT_USER_SLUG)


def run_tracking_for_all_users() -> dict[str, dict[str, int | str]]:
    results: dict[str, dict[str, int | str]] = {}
    with job_session_factory() as sessions:
        with sessions() as session:
            users = SpotifyCredentialsRepository(session).users_with_credentials()
            user_slugs = [user.slug for user in users]

        for user_slug in user_slugs:
            try:
                results[user_slug] = run_tracking_for_user(user_slug, open_session=sessions)
            except Exception as exc:
                with sessions() as session:
                    _record_sync_error(session, user_slug, str(exc))
                results[user_slug] = {"error": str(exc)}
    return results


def run_tracking_for_user(
    user_slug: str,
    *,
    open_session: Callable[[], AbstractContextManager[Session]] = job_session,
) -> dict[str, int]:
    started = time.perf_counter()
    with bound_contextvars(sync_run_id=uuid.uuid4().hex, user_id=None, sync_phase="initialize", album_state_saved=False):
        try:
            with open_session() as session:
                result = _run_tracking_for_user(user_slug, session)
            logger.info("spotify_sync_completed", duration_ms=round((time.perf_counter() - started) * 1000, 3), **result)
            return result
        except Exception as exc:
            status_code = exc.http_status if isinstance(exc, SpotifyException) else None
            category = "rate_limited" if status_code == 429 else "timeout" if isinstance(exc, (TimeoutError, RequestsTimeout)) else "other"
            database_fields = database_error_fields(exc)
            log_failure = logger.error if database_fields else logger.exception
            log_failure("spotify_sync_failed", duration_ms=round((time.perf_counter() - started) * 1000, 3), failure_category=category, status_code=status_code, **database_fields)
            raise


def _run_tracking_for_user(user_slug: str, session: Session) -> dict[str, int]:
    user = UserRepository(session).require_user_by_slug(user_slug)
    bind_contextvars(user_id=user.id)
    logger.info("spotify_sync_started")
    bind_contextvars(sync_phase="credentials")
    require_spotify_sync_access(user)
    credentials = _credentials_for_user(
        session,
        user.id,
    )
    repository = AlbumStateRepository(session, user)
    bind_contextvars(sync_phase="load_state")
    start_state = repository.load()

    starting_completed_count = len(start_state.get("completed_albums", {}))

    bind_contextvars(sync_phase="initialize_spotify_client")
    spotify = SpotifyAPI(credentials)
    bind_contextvars(sync_phase="fetch_recent_tracks")
    tracks = spotify.fetch_recent_tracks(start_state["last_checked"])

    bind_contextvars(sync_phase="derive_listens")
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

    bind_contextvars(sync_phase="save_album_state")
    repository.replace(end_state)
    # The state save commits separately from the sync-success update below.
    bind_contextvars(sync_phase="record_sync_success", album_state_saved=True)
    SpotifyCredentialsRepository(session).record_sync_success(
        user_id=user.id,
        synced_at=_utc_now(),
    )

    final_completed_count = len(end_state["completed_albums"])

    return {
        "tracks_fetched": len(tracks),
        "completed_albums": len(completed_album_ids),
        "net_album_count_change": final_completed_count - starting_completed_count,
    }


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


def _record_sync_error(session: Session, user_slug: str, error: str) -> None:
    user = UserRepository(session).get_user_by_slug(user_slug)
    if user is None:
        return
    SpotifyCredentialsRepository(session).record_sync_error(
        user_id=user.id,
        error=error,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
