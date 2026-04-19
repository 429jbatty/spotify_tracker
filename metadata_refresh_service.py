import copy
import logging
from dataclasses import dataclass

import album_metadata_service as metadata_service
import tracking
import utils

logger = logging.getLogger(__name__)

PRESERVED_FIELDS = {
    "listen_history",
}


@dataclass
class RefreshResult:
    key: str
    artist: str
    album: str
    refreshed: bool
    error: str | None = None


def _album_key(artist: str, album: str) -> str:
    return f"{artist} - {album}"


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

    refreshed = copy.deepcopy(refreshed)
    for field in PRESERVED_FIELDS:
        if field in record:
            refreshed[field] = copy.deepcopy(record[field])

    return refreshed


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
            logger.exception("Failed to refresh metadata for %s", key)
            result = RefreshResult(
                key=key,
                artist=record.get("artist", ""),
                album=record.get("name", ""),
                refreshed=False,
                error=str(exc),
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
    new_key = repository.replace_completed_album_metadata(
        target_key,
        refreshed_record,
    )

    return RefreshResult(
        key=new_key,
        artist=refreshed_record["artist"],
        album=refreshed_record["name"],
        refreshed=True,
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
                logger.exception("Failed to refresh metadata for %s", key)
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
