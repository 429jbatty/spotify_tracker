"""Log a metadata refresh at the boundary that persists its result."""
import structlog

import metadata_refresh_service

logger = structlog.get_logger(__name__)


def refresh_album(repository, album_id: int, spotify_url: str | None = None) -> dict:
    existing = repository.get_completed_album_record_by_id(album_id)
    try:
        refreshed = metadata_refresh_service.refresh_album_record(existing, spotify_url=spotify_url)
        warnings = refreshed.pop("_refresh_warnings", [])
        result = repository.replace_completed_album_metadata_by_id_or_merge_duplicate(album_id, refreshed)
    except Exception as exc:
        reason = metadata_refresh_service.classify_refresh_error(exc)
        logger.warning("album_metadata_refresh_failed", album_id=album_id, reason=reason, error_type=type(exc).__name__)
        raise
    logger.info("album_metadata_refreshed", album_id=album_id, warning_count=len(warnings))
    return result
