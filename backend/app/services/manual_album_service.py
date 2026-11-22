import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

import album_metadata_service
from backend.app.repositories.sqlite_state_repository import AlbumChange, SqliteStateRepository
from backend.app.services.user_activity_logging import AlbumActivity, emit_manual_activity
from backend.app.schemas import ManualAlbumCreate

logger = logging.getLogger(__name__)

# Manual creation is a foreground first-use flow.  Metadata is useful, but it
# must never keep a user's own album and listen from being saved.
MANUAL_METADATA_TIMEOUT_SECONDS = 8
_metadata_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="manual-metadata")
_metadata_slots = threading.BoundedSemaphore(value=2)


def _manual_record(request: ManualAlbumCreate) -> dict[str, Any]:
    record = request.model_dump(exclude={"listen_date"}, exclude_none=True)
    record["source"] = "manual"
    record["entry_source"] = "manual"
    record["_manual_input_identity"] = f"{request.artist}\0{request.name}".casefold()
    return record


def _metadata_record(request: ManualAlbumCreate) -> dict[str, Any] | None:
    if not _metadata_slots.acquire(blocking=False):
        logger.info("Skipping manual album metadata lookup while workers are busy")
        return None

    try:
        future = _metadata_executor.submit(
            album_metadata_service.get_album_metadata,
            request.artist,
            request.name,
            spotify_url=request.spotify_url,
        )
    except Exception:
        _metadata_slots.release()
        raise
    future.add_done_callback(lambda _completed: _metadata_slots.release())
    try:
        metadata = future.result(timeout=MANUAL_METADATA_TIMEOUT_SECONDS)
    except TimeoutError:
        # The lookup can continue harmlessly in the bounded executor, but the
        # request must return so the manually supplied album is persisted.
        logger.warning(
            "Manual album metadata lookup timed out for %s - %s after %ss",
            request.artist,
            request.name,
            MANUAL_METADATA_TIMEOUT_SECONDS,
        )
        return None
    except Exception as exc:
        logger.warning(
            "Manual album metadata lookup failed for %s - %s: %s",
            request.artist,
            request.name,
            exc,
        )
        return None

    confidence = album_metadata_service.metadata_match_confidence(metadata)
    if confidence < album_metadata_service.CANONICAL_AUTO_APPLY_CONFIDENCE:
        return None

    metadata["entry_source"] = "manual"
    metadata["_manual_input_identity"] = f"{request.artist}\0{request.name}".casefold()
    return metadata


def create_manual_album(
    repository: SqliteStateRepository,
    request: ManualAlbumCreate,
) -> dict[str, Any]:
    record = _metadata_record(request) or _manual_record(request)
    user = _begin_collection_write(repository)
    result, change = repository.create_completed_album_with_changes(record, listen_date=request.listen_date)
    _emit_change(user, change, _added_events(change))
    return result


def _begin_collection_write(repository: SqliteStateRepository) -> tuple[int, str]:
    # SQLite SELECTs may start a SQLAlchemy transaction without taking a database
    # write lock. Serialize the change check and write after metadata lookup.
    connection = repository.session.connection()
    if connection.dialect.name == "sqlite":
        if connection.connection.driver_connection.in_transaction:
            raise RuntimeError("Manual activity requires a fresh SQLite write transaction")
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    return repository.user.id, repository.user.slug


def _emit_change(user: tuple[int, str], change: AlbumChange, events: list[tuple[str, str | None]]) -> None:
    activity = AlbumActivity(
        user_id=user[0], profile_slug=user[1],
        album_id=change.album_id, album_artist=change.artist, album_title=change.title,
    )
    emit_manual_activity(activity, events)


def _added_events(change: AlbumChange) -> list[tuple[str, str | None]]:
    events = [("album_manually_added", None)] if change.membership_added else []
    events.extend(("album_listen_added", date) for date in change.listens_added)
    return events


def add_manual_album_listen(repository: SqliteStateRepository, album_id: int, listened_at: str) -> dict[str, Any]:
    user = _begin_collection_write(repository)
    result, change = repository.add_album_listen_with_changes(album_id, listened_at)
    _emit_change(user, change, _added_events(change))
    return result


def delete_manual_album_listen(repository: SqliteStateRepository, album_id: int, listened_at: str) -> dict[str, Any]:
    user = _begin_collection_write(repository)
    result, change = repository.delete_album_listen(album_id, listened_at)
    _emit_change(user, change, [("album_listen_removed", listened_at)])
    return result


def delete_manual_album(repository: SqliteStateRepository, album_id: int) -> None:
    user = _begin_collection_write(repository)
    change = repository.delete_completed_album(album_id)
    _emit_change(user, change, [("album_removed", None)])
