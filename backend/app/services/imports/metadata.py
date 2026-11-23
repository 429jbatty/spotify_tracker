"""Resolve import metadata from the local library, shared cache and MusicBrainz."""

import hashlib
import time
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

import album_metadata_service
import metadata_refresh_service
from backend.app.repositories import album_metadata_cache_repository as metadata_cache_repository
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services.import_parsers import NormalizedImportEvent, clean_text

from .common import utc_now
from .progress import ImportMetadataStats


_ALBUM_METADATA_CACHE_MISS = object()


@dataclass
class ExistingAlbumMatch:
    album_id: int
    record: dict[str, Any]


def resolve_album_metadata(
    session: Session,
    artist: str,
    album: str,
    metadata_cache: dict[tuple[str, str], dict[str, Any] | None],
    *,
    matched_album_id: int | None,
    matched_album_record: dict[str, Any] | None,
    allow_remote_metadata: bool = True,
    entry_source: str = "lastfm",
    metadata_stats: ImportMetadataStats | None = None,
) -> dict[str, Any] | None:
    cache_key = (artist.casefold(), album.casefold())
    if cache_key in metadata_cache:
        if metadata_stats is not None:
            metadata_stats.cache_hits += 1
        return metadata_cache[cache_key]

    if matched_album_id is not None and matched_album_record and matched_album_record.get("tracklist"):
        metadata_cache[cache_key] = matched_album_record
        if metadata_stats is not None:
            metadata_stats.cache_hits += 1
        return matched_album_record

    cached = read_album_metadata_cache(session, artist, album)
    if cached is not _ALBUM_METADATA_CACHE_MISS:
        metadata_cache[cache_key] = cached if isinstance(cached, dict) else None
        if metadata_stats is not None:
            metadata_stats.cache_hits += 1
        return metadata_cache[cache_key]

    if not allow_remote_metadata:
        metadata_cache[cache_key] = None
        return None

    started_at = time.perf_counter()
    if metadata_stats is not None:
        metadata_stats.cache_misses += 1
    try:
        metadata = album_metadata_service.get_album_metadata_for_import_matching(artist, album)
        if metadata:
            metadata["entry_source"] = entry_source
            metadata.pop("_refresh_warnings", None)
    except Exception:
        if metadata_stats is not None:
            metadata_stats.lookup_seconds.append(time.perf_counter() - started_at)
        metadata_cache[cache_key] = None
        return None
    if metadata_stats is not None:
        metadata_stats.lookup_seconds.append(time.perf_counter() - started_at)

    write_album_metadata_cache(session, artist, album, metadata)
    metadata_cache[cache_key] = metadata
    return metadata


def album_match_key(artist: str | None, album: str | None) -> tuple[str, str]:
    return ((artist or "").strip().casefold(), (album or "").strip().casefold())


def load_existing_albums(
    repository: SqliteStateRepository,
) -> dict[tuple[str, str], ExistingAlbumMatch]:
    index: dict[tuple[str, str], ExistingAlbumMatch] = {}
    for album_id, artist, name, record in repository.library_album_records():
        index[album_match_key(artist, name)] = ExistingAlbumMatch(
            album_id=album_id,
            record=record,
        )
    return index


def album_metadata_cache_key(artist: str, album: str) -> str:
    return hashlib.sha256(
        "|".join(
            [
                "musicbrainz-import-v2",
                artist.strip().casefold(),
                album.strip().casefold(),
            ]
        ).encode("utf-8")
    ).hexdigest()


def read_album_metadata_cache(
    session: Session,
    artist: str,
    album: str,
) -> dict[str, Any] | None | object:
    row = metadata_cache_repository.get(session, album_metadata_cache_key(artist, album))
    if row is None:
        return _ALBUM_METADATA_CACHE_MISS
    return row.metadata_json if row.status == "matched" else None


def write_album_metadata_cache(
    session: Session,
    artist: str,
    album: str,
    metadata: dict[str, Any] | None,
) -> None:
    metadata_cache_repository.store(
        session,
        cache_key=album_metadata_cache_key(artist, album),
        artist=artist,
        album=album,
        metadata=metadata,
        updated_at=utc_now(),
    )


def build_album_record(event: NormalizedImportEvent) -> dict[str, Any]:
    record = {
        "artist": event.artist,
        "name": event.album,
        "source": "musicbrainz" if event.source == "lastfm" else event.source,
        "entry_source": event.source,
    }
    if event.notes:
        record["notes"] = event.notes

    try:
        refreshed = metadata_refresh_service.refresh_album_record(record)
        refreshed.pop("_refresh_warnings", None)
        if not _metadata_matches_imported_album(event, refreshed):
            return record
        return refreshed
    except Exception:
        return record


def _metadata_matches_imported_album(
    event: NormalizedImportEvent,
    metadata: dict[str, Any],
) -> bool:
    imported_artist = clean_text(event.artist)
    imported_album = clean_text(event.album)
    metadata_artist = clean_text(metadata.get("artist"))
    metadata_album = clean_text(metadata.get("name"))
    if not imported_artist or not imported_album or not metadata_artist or not metadata_album:
        return False

    artist_score = fuzz.token_set_ratio(imported_artist.casefold(), metadata_artist.casefold())
    album_score = fuzz.token_set_ratio(imported_album.casefold(), metadata_album.casefold())
    return artist_score >= 85 and album_score >= 85
