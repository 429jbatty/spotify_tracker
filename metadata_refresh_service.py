import copy
import structlog
from dataclasses import dataclass, field

import musicbrainzngs

from backend.app.persistence_logging import database_error_fields

import album_metadata_service as metadata_service
from backend.app.database.repositories.album_library import AlbumLibrary
from backend.app.database.repositories.user_repository import UserRepository
from backend.app.job_database import job_session

logger = structlog.get_logger(__name__)

PRESERVED_FIELDS = {
    "listen_history",
    "local_image_path",
}

IGNORED_MERGE_FIELDS = {
    "id",
    "album_key",
}


@dataclass
class RefreshResult:
    key: str
    artist: str
    album: str
    refreshed: bool
    error: str | None = None
    status: str = ""
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.status:
            self.status = "refreshed" if self.refreshed else "failed"


class LowConfidenceMetadataError(LookupError):
    pass


def classify_refresh_error(exc: Exception) -> str:
    if isinstance(exc, LowConfidenceMetadataError):
        return "skipped_low_confidence"
    if isinstance(exc, LookupError):
        return "skipped_no_match"
    if isinstance(exc, ValueError) and "Album key already exists" in str(exc):
        return "skipped_duplicate_key"
    if isinstance(exc, musicbrainzngs.NetworkError):
        return "failed_network"
    return "failed"


def _log_refresh_error(key: str, exc: Exception) -> str:
    status = classify_refresh_error(exc)
    database_fields = database_error_fields(exc)
    logger.warning(
        "album_metadata_refresh_failed", album_key=key, reason=status,
        error_type=type(exc).__name__, exc_info=status == "failed" and not database_fields,
        **database_fields,
    )
    return status


def _merge_refreshed_metadata(record: dict, refreshed: dict) -> dict:
    merged = {
        key: copy.deepcopy(value)
        for key, value in record.items()
        if key not in IGNORED_MERGE_FIELDS
    }
    warnings = []

    for key, value in refreshed.items():
        if key in IGNORED_MERGE_FIELDS:
            continue
        if value is None and merged.get(key) is not None:
            warnings.append(f"Preserved existing {key}; refreshed value was null.")
            continue
        merged[key] = copy.deepcopy(value)
        if (
            key == "image_url"
            and value is not None
            and "remote_image_url" not in refreshed
        ):
            merged["remote_image_url"] = copy.deepcopy(value)

    for field_name in PRESERVED_FIELDS:
        if field_name in record:
            merged[field_name] = copy.deepcopy(record[field_name])

    if warnings:
        merged["_refresh_warnings"] = warnings

    return merged


def refresh_album_record(record: dict, spotify_url: str | None = None):
    artist = record.get("artist")
    album = record.get("name")

    if not artist or not album:
        raise ValueError("Album record must include artist and name.")

    refreshed = metadata_service.get_album_metadata(
        artist,
        album,
        spotify_url=spotify_url,
    )

    if not refreshed:
        raise LookupError(f"No metadata returned for {artist} - {album}.")

    confidence = metadata_service.metadata_match_confidence(refreshed)
    if confidence < metadata_service.CANONICAL_AUTO_APPLY_CONFIDENCE:
        raise LowConfidenceMetadataError(
            f"Metadata confidence {confidence} is below automatic refresh threshold "
            f"for {artist} - {album}."
        )

    return _merge_refreshed_metadata(record, refreshed)


def _refresh_catalog_album(
    library: AlbumLibrary,
    *,
    artist: str | None = None,
    album: str | None = None,
    key: str | None = None,
    spotify_url: str | None = None,
):
    target = library.catalog.find_for_refresh(artist=artist, title=album, key=key)
    library.require_member(target.id)
    target_key = target.album_key
    existing_record = library.record_for(target)
    refreshed_record = refresh_album_record(existing_record, spotify_url=spotify_url)
    warnings = refreshed_record.pop("_refresh_warnings", [])
    new_key = library.replace_catalog_metadata_for_refresh(target_key, refreshed_record)

    logger.info("album_metadata_refreshed", album_id=existing_record.get("id"), warning_count=len(warnings))

    return RefreshResult(
        key=new_key,
        artist=refreshed_record["artist"],
        album=refreshed_record["name"],
        refreshed=True,
        status="refreshed_with_warnings" if warnings else "refreshed",
        warnings=warnings,
    )


def refresh_album_and_save(
    *,
    user_slug: str,
    artist: str | None = None,
    album: str | None = None,
    key: str | None = None,
    spotify_url: str | None = None,
):
    with job_session() as session:
        user = UserRepository(session).require_user_by_slug(user_slug)
        return _refresh_catalog_album(
            AlbumLibrary(session, user),
            artist=artist,
            album=album,
            key=key,
            spotify_url=spotify_url,
        )


def refresh_all_albums_and_save(user_slug: str, continue_on_error: bool = True):
    results = []

    with job_session() as session:
        user = UserRepository(session).require_user_by_slug(user_slug)
        library = AlbumLibrary(session, user)
        original_keys = list(library.list_records())

        for key in original_keys:
            try:
                result = _refresh_catalog_album(library, key=key)
            except Exception as exc:
                status = _log_refresh_error(key, exc)
                try:
                    record = library.record_for(library.catalog.require_by_key(key))
                except Exception:
                    record = {}

                result = RefreshResult(
                    key=key,
                    artist=record.get("artist", ""),
                    album=record.get("name", ""),
                    refreshed=False,
                    error=str(exc),
                    status=status,
                )
                results.append(result)

                if not continue_on_error:
                    raise
            else:
                results.append(result)

    return results
