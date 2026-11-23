import structlog
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextvars import copy_context
from typing import Any

import album_metadata_service
from backend.app.repositories.sqlite_state_repository import AlbumChange, SqliteStateRepository
from backend.app.services.user_activity_logging import AlbumActivity, emit_activity
from backend.app.schemas import ManualAlbumCreate

logger = structlog.get_logger(__name__)

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
        logger.info("manual_metadata_fallback", reason="workers_busy")
        return None

    try:
        # ThreadPoolExecutor does not propagate request context automatically.
        future = _metadata_executor.submit(
            copy_context().run, album_metadata_service.get_album_metadata,
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
        logger.warning("manual_metadata_fallback", reason="timeout", timeout_seconds=MANUAL_METADATA_TIMEOUT_SECONDS)
        return None
    except Exception as exc:
        logger.warning("manual_metadata_fallback", reason="lookup_failed", error_type=type(exc).__name__)
        return None

    confidence = album_metadata_service.metadata_match_confidence(metadata)
    if confidence < album_metadata_service.CANONICAL_AUTO_APPLY_CONFIDENCE:
        logger.info("manual_metadata_fallback", reason="low_confidence" if metadata else "no_match")
        return None

    logger.info("manual_metadata_accepted", match_confidence=confidence)
    metadata["entry_source"] = "manual"
    metadata["_manual_input_identity"] = f"{request.artist}\0{request.name}".casefold()
    return metadata


def create_manual_album(
    repository: SqliteStateRepository,
    request: ManualAlbumCreate,
) -> dict[str, Any]:
    record = _metadata_record(request) or _manual_record(request)
    user = repository.begin_manual_collection_write()
    result, change = repository.create_completed_album_with_changes(record, listen_date=request.listen_date)
    _emit_change(user, change, _added_events(change))
    return result


def _emit_change(user: tuple[int, str], change: AlbumChange, events: list[tuple[str, dict]]) -> None:
    activity = AlbumActivity(
        user_id=user[0], profile_slug=user[1],
        album_id=change.album_id, album_artist=change.artist, album_title=change.title,
    )
    emit_activity(activity, events)


def _added_events(change: AlbumChange) -> list[tuple[str, dict]]:
    events = [("album_manually_added", {})] if change.membership_added else []
    events.extend(("album_listen_added", {"listened_at": date}) for date in change.listens_added)
    return events


def add_manual_album_listen(repository: SqliteStateRepository, album_id: int, listened_at: str) -> dict[str, Any]:
    user = repository.begin_manual_collection_write()
    result, change = repository.add_album_listen_with_changes(album_id, listened_at)
    _emit_change(user, change, _added_events(change))
    return result


def delete_manual_album_listen(repository: SqliteStateRepository, album_id: int, listened_at: str) -> dict[str, Any]:
    user = repository.begin_manual_collection_write()
    result, change = repository.delete_album_listen(album_id, listened_at)
    _emit_change(user, change, [("album_listen_removed", {"listened_at": listened_at})])
    return result


def delete_manual_album(repository: SqliteStateRepository, album_id: int) -> None:
    user = repository.begin_manual_collection_write()
    change = repository.delete_completed_album(album_id)
    _emit_change(user, change, [("album_removed", {})])


def update_manual_album_feedback(
    repository: SqliteStateRepository, album_id: int, *, rating: int | None, notes: str | None,
) -> dict[str, Any]:
    user = repository.begin_manual_collection_write()
    result, album, rating_change, note_change = repository.update_user_album_feedback_with_changes(
        album_id, rating=rating, notes=notes,
    )
    events = []
    if rating_change == "removed":
        events.append(("album_rating_removed", {}))
    elif rating_change:
        events.append(("album_rating_changed", {"rating": rating, "change": rating_change}))
    if note_change == "removed":
        events.append(("album_note_removed", {}))
    elif note_change:
        events.append(("album_note_changed", {"change": note_change}))
    _emit_change(user, album, events)
    return result


def update_manual_album_tags(
    repository: SqliteStateRepository, album_id: int, your_tags: list[str],
) -> dict[str, Any]:
    user = repository.begin_manual_collection_write()
    result, album, added, removed = repository.update_user_album_tags_with_changes(album_id, your_tags)
    events = [("album_tags_changed", {"added_tags": added, "removed_tags": removed})] if added or removed else []
    _emit_change(user, album, events)
    return result
