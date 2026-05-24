import copy
import logging
from dataclasses import dataclass, field

import musicbrainzngs

import album_metadata_service as metadata_service
import tracking
import utils

logger = logging.getLogger(__name__)

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


def _album_key(artist: str, album: str) -> str:
    return f"{artist} - {album}"


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
    if status == "failed":
        logger.exception("Failed to refresh metadata for %s", key)
    else:
        logger.warning(
            "Skipped metadata refresh for %s [%s]: %s",
            key,
            status,
            exc,
        )
        logger.debug("Refresh skip details for %s", key, exc_info=True)
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


def _find_album_key(completed_albums: dict, artist: str | None, album: str | None):
    if artist and album:
        exact_key = _album_key(artist, album)
        if exact_key in completed_albums:
            return exact_key

    normalized_artist = artist.casefold() if artist else None
    normalized_album = album.casefold() if album else None

    matches = []
    for key, record in completed_albums.items():
        record_artist = str(record.get("artist", "")).casefold()
        record_album = str(record.get("name", "")).casefold()

        if normalized_artist and record_artist != normalized_artist:
            continue
        if normalized_album and record_album != normalized_album:
            continue
        matches.append(key)

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise KeyError("No matching album found.")

    raise ValueError(
        "Multiple matching albums found. Provide both artist and album exactly."
    )


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


def refresh_album_in_state(
    state: dict,
    *,
    artist: str | None = None,
    album: str | None = None,
    key: str | None = None,
    spotify_url: str | None = None,
):
    completed_albums = state.get("completed_albums", {})
    target_key = key or _find_album_key(completed_albums, artist, album)

    if target_key not in completed_albums:
        raise KeyError(f"Album key not found: {target_key}")

    existing_record = completed_albums[target_key]
    refreshed_record = refresh_album_record(existing_record, spotify_url=spotify_url)
    warnings = refreshed_record.pop("_refresh_warnings", [])

    new_key = _album_key(refreshed_record["artist"], refreshed_record["name"])
    if new_key != target_key:
        del completed_albums[target_key]

    completed_albums[new_key] = refreshed_record
    state["most_recently_listened"] = tracking.get_most_recently_listened(
        state,
        num=10,
    )

    return RefreshResult(
        key=new_key,
        artist=refreshed_record["artist"],
        album=refreshed_record["name"],
        refreshed=True,
        status="refreshed_with_warnings" if warnings else "refreshed",
        warnings=warnings,
    )


def refresh_all_albums_in_state(state: dict, continue_on_error: bool = True):
    results = []
    original_keys = list(state.get("completed_albums", {}).keys())

    for key in original_keys:
        if key not in state.get("completed_albums", {}):
            continue

        record = state["completed_albums"][key]
        try:
            result = refresh_album_in_state(state, key=key)
        except Exception as exc:
            status = _log_refresh_error(key, exc)
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

    state["most_recently_listened"] = tracking.get_most_recently_listened(
        state,
        num=10,
    )

    return results


def _refresh_album_in_sqlite_repository(
    repository,
    *,
    artist: str | None = None,
    album: str | None = None,
    key: str | None = None,
    spotify_url: str | None = None,
):
    target_key = repository.find_completed_album_key(
        artist=artist,
        album=album,
        key=key,
    )
    existing_record = repository.get_completed_album_record(target_key)
    refreshed_record = refresh_album_record(existing_record, spotify_url=spotify_url)
    warnings = refreshed_record.pop("_refresh_warnings", [])
    new_key = repository.replace_completed_album_metadata(
        target_key,
        refreshed_record,
    )

    return RefreshResult(
        key=new_key,
        artist=refreshed_record["artist"],
        album=refreshed_record["name"],
        refreshed=True,
        status="refreshed_with_warnings" if warnings else "refreshed",
        warnings=warnings,
    )


def _refresh_album_and_save_sqlite(
    *,
    artist: str | None = None,
    album: str | None = None,
    key: str | None = None,
    spotify_url: str | None = None,
):
    with utils.sqlite_state_repository() as repository:
        return _refresh_album_in_sqlite_repository(
            repository,
            artist=artist,
            album=album,
            key=key,
            spotify_url=spotify_url,
        )


def _refresh_all_albums_and_save_sqlite(continue_on_error: bool = True):
    results = []

    with utils.sqlite_state_repository() as repository:
        original_keys = repository.completed_album_keys()

        for key in original_keys:
            try:
                result = _refresh_album_in_sqlite_repository(repository, key=key)
            except Exception as exc:
                status = _log_refresh_error(key, exc)
                try:
                    record = repository.get_completed_album_record(key)
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


def refresh_album_and_save(
    *,
    artist: str | None = None,
    album: str | None = None,
    key: str | None = None,
    spotify_url: str | None = None,
):
    if utils.use_sqlite_state():
        return _refresh_album_and_save_sqlite(
            artist=artist,
            album=album,
            key=key,
            spotify_url=spotify_url,
        )

    state = utils.load_state()
    result = refresh_album_in_state(
        state,
        artist=artist,
        album=album,
        key=key,
        spotify_url=spotify_url,
    )
    utils.save_state(state)
    return result


def refresh_all_albums_and_save(continue_on_error: bool = True):
    if utils.use_sqlite_state():
        return _refresh_all_albums_and_save_sqlite(
            continue_on_error=continue_on_error,
        )

    state = utils.load_state()
    results = refresh_all_albums_in_state(
        state,
        continue_on_error=continue_on_error,
    )
    utils.save_state(state)
    return results
