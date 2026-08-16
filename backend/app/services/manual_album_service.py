import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

import album_metadata_service
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
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
    return repository.create_completed_album(record, listen_date=request.listen_date)
