"""Match against the user's library, persistent cache and MusicBrainz, in that order."""

import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

import album_metadata_service
from backend.app.database.repositories import album_metadata_cache_repository as cache
from backend.app.database.repositories.album_library import AlbumLibrary

from .events import fingerprint, utc_now
from .progress import ImportMetadataStats


_MISS = object()


@dataclass
class ExistingAlbumMatch:
    album_id: int
    record: dict


def album_match_key(artist, album):
    return (artist or "").strip().casefold(), (album or "").strip().casefold()


def load_existing_albums(repository: AlbumLibrary) -> dict[tuple[str, str], ExistingAlbumMatch]:
    return {album_match_key(artist, name): ExistingAlbumMatch(album_id, record)
            for album_id, artist, name, record in repository.matching_albums()}


def album_metadata_cache_key(artist, album):
    return fingerprint("musicbrainz-import-v2", *album_match_key(artist, album))


def read_album_metadata_cache(session, artist, album):
    row = cache.get(session, album_metadata_cache_key(artist, album))
    if row is None:
        return _MISS
    return row.metadata_json if row.status == "matched" else None


def write_album_metadata_cache(session, artist, album, metadata):
    cache.store(session, cache_key=album_metadata_cache_key(artist, album), artist=artist, album=album,
                metadata=metadata, updated_at=utc_now())


class AlbumLookup:
    """In-memory cache for one matching pass. A local-only miss expires before the remote pass."""

    def __init__(self, session: Session, repository: AlbumLibrary, stats: ImportMetadataStats | None = None):
        self.session = session
        self.albums = load_existing_albums(repository)
        self.stats = stats or ImportMetadataStats()
        self.cache = {}

    def resolve(self, artist: str, album: str, existing: ExistingAlbumMatch | None, *, remote: bool, source: str) -> dict | None:
        key = artist.casefold(), album.casefold()
        if key in self.cache:
            self.stats.cache_hits += 1
            return self.cache[key]
        result = existing.record if existing and existing.record.get("tracklist") else _MISS
        if result is _MISS:
            result = read_album_metadata_cache(self.session, artist, album)
        if result is not _MISS:
            self.stats.cache_hits += 1
        elif remote:
            result = self._fetch(artist, album, source)
        self.cache[key] = result if isinstance(result, dict) else None
        return self.cache[key]

    def _fetch(self, artist, album, source):
        started = time.perf_counter()
        self.stats.cache_misses += 1
        try:
            result = album_metadata_service.get_album_metadata_for_import_matching(artist, album)
            if result:
                result["entry_source"] = source
                result.pop("_refresh_warnings", None)
        except Exception:
            return None  # Transient failures must not enter the persistent negative cache.
        finally:
            self.stats.lookup_seconds.append(time.perf_counter() - started)
        write_album_metadata_cache(self.session, artist, album, result)
        return result
