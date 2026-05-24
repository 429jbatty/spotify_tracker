import logging
from typing import Any

import album_metadata_service
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import ManualAlbumCreate

logger = logging.getLogger(__name__)


def _manual_record(request: ManualAlbumCreate) -> dict[str, Any]:
    record = request.model_dump(exclude={"listen_date"}, exclude_none=True)
    record["source"] = "manual"
    record["entry_source"] = "manual"
    return record


def _metadata_record(request: ManualAlbumCreate) -> dict[str, Any] | None:
    try:
        metadata = album_metadata_service.get_album_metadata(
            request.artist,
            request.name,
            spotify_url=request.spotify_url,
        )
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
    return metadata


def create_manual_album(
    repository: SqliteStateRepository,
    request: ManualAlbumCreate,
) -> dict[str, Any]:
    record = _metadata_record(request) or _manual_record(request)
    return repository.create_completed_album(record, listen_date=request.listen_date)
