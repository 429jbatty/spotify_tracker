"""Log a metadata refresh at the boundary that persists its result."""
import structlog

import metadata_refresh_service
from backend.app.database.models import Album
from backend.app.database.repositories.album_library import AlbumLibrary

logger = structlog.get_logger(__name__)


def refresh_album(library: AlbumLibrary, album: Album, spotify_url: str | None = None) -> dict:
    album_id = album.id
    existing = library.record_for(album)
    try:
        refreshed = metadata_refresh_service.refresh_album_record(existing, spotify_url=spotify_url)
        warnings = refreshed.pop("_refresh_warnings", [])
        result = library.replace_metadata(album_id, refreshed)
    except Exception as exc:
        reason = metadata_refresh_service.classify_refresh_error(exc)
        logger.warning("album_metadata_refresh_failed", album_id=album_id, reason=reason, error_type=type(exc).__name__)
        raise
    logger.info("album_metadata_refreshed", album_id=album_id, warning_count=len(warnings))
    return result
