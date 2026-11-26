"""Decide whether a session is a completed album listen, pending, partial or reviewable."""

from dataclasses import dataclass
from typing import Any

import album_metadata_service
from backend.app.album_completion import ALBUM_COMPLETION_THRESHOLD
from backend.app.services.import_parsers import NormalizedImportEvent

from .events import SPOTIFY_IMPORT_SOURCE, fingerprint
from .metadata import AlbumLookup, album_match_key
from .spotify_completion import spotify_completion_result
from .track_matching import compare_tracklist, normalize_track_name, track_identity


LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS = 3
SPOTIFY_REMOTE_METADATA_MIN_UNIQUE_TRACKS = 5
SPOTIFY_REMOTE_METADATA_MIN_MS_PLAYED = 20 * 60 * 1000
SPOTIFY_REMOTE_METADATA_ALWAYS_UNIQUE_TRACKS = 8


@dataclass
class AlbumCandidate:
    candidate_key: str
    artist: str
    album: str
    listened_at: str
    events: list[NormalizedImportEvent]
    unique_scrobbled_tracks: int
    matched_album_id: int | None = None
    matched_track_count: int = 0
    total_track_count: int = 0
    confidence: int = 25
    metadata: dict[str, Any] | None = None
    status: str = "partial_listen"
    status_detail: str = ""

    def decide(self, status: str, detail: str) -> "AlbumCandidate":
        self.status = status
        self.status_detail = detail
        return self


def match_album_session(
    lookup: AlbumLookup, events: list[NormalizedImportEvent], source_user_id: str | None, *, remote: bool,
) -> AlbumCandidate:
    first = events[0]
    artist, album = first.artist or "Unknown Artist", first.album or "Unknown Album"
    key = fingerprint(first.source, source_user_id or "", artist.casefold(), album.casefold(),
                      first.listened_at or "", events[-1].listened_at or "")
    unique = len({track_identity(event) for event in events} - {""})
    candidate = AlbumCandidate(key, artist, album, max(e.listened_at for e in events if e.listened_at), events, unique)

    spotify = spotify_completion_result(events)
    if spotify:
        candidate.matched_track_count = spotify.matched_track_count
        candidate.total_track_count = spotify.total_tracks
        candidate.confidence = spotify.confidence
        if spotify.exclusion_reason:
            return candidate.decide("partial_listen", spotify.exclusion_reason)

    existing = lookup.albums.get(album_match_key(artist, album))
    candidate.matched_album_id = existing.album_id if existing else None
    fetch = remote and (bool(spotify) or _has_remote_evidence(events, unique))
    candidate.metadata = lookup.resolve(artist, album, existing, remote=fetch, source=first.source)
    if candidate.metadata and candidate.metadata.get("tracklist"):
        return _match_tracklist(candidate, spotify)
    if spotify:
        if remote:
            return candidate.decide("candidate_review", "Spotify indicates this is a completed album listen, but "
                                    "MusicBrainz metadata could not be loaded automatically.")
        return candidate.decide("pending_metadata", f"Spotify matched {spotify.matched_track_count} of "
                                f"{spotify.total_tracks} album tracks. MusicBrainz metadata is still needed before "
                                "creating the album listen.")
    if not _has_remote_evidence(events, unique):
        return candidate.decide("partial_listen", f"Only {unique} unique tracks were available; skipped remote metadata "
                                "lookup because this is not enough evidence for a full album listen.")
    if not remote:
        return candidate.decide("no_tracklist", "No local or cached tracklist is available yet, so this scrobble session "
                                "does not count as a completed album listen.")
    return candidate.decide("candidate_review", "Could not load album tracklist, so this scrobble session needs review.")


def _match_tracklist(candidate, spotify):
    names = {normalize_track_name(event.track) for event in candidate.events} - {""}
    matched, total, partial_titles = compare_tracklist(candidate.metadata["tracklist"], names)
    if spotify:
        matched, total = spotify.matched_track_count, spotify.total_tracks
    candidate.matched_track_count = matched
    candidate.total_track_count = total
    if total:
        candidate.confidence = round(100 * (matched / total))
    if candidate.matched_album_id is None and not _importable_album(candidate.metadata, total):
        return candidate.decide("partial_listen", "MusicBrainz matched this to a single or short non-album release, "
                                "so it does not count as a completed album listen.")
    if partial_titles and candidate.events[0].source == SPOTIFY_IMPORT_SOURCE:
        return candidate.decide("partial_listen", f"Spotify matched only part of a combined MusicBrainz track "
                                f"({', '.join(partial_titles)}), so this does not count as a completed album listen.")
    if not total or matched / total < ALBUM_COMPLETION_THRESHOLD:
        return candidate.decide("partial_listen", f"Matched {matched} of {total or len(names)} tracks. "
                                "This does not count as a completed album listen.")
    detail = f"Spotify matched {matched} of {total} album tracks." if spotify else f"Matched {matched} of {total} tracks."
    status = "matched_existing" if candidate.matched_album_id is not None else "new_album"
    return candidate.decide(status, detail + " This will count as a completed album listen.")


def _has_remote_evidence(events, unique):
    if events[0].source != SPOTIFY_IMPORT_SOURCE:
        return unique >= LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS
    milliseconds = sum(int(e.raw_payload.get("_spotify_ms_played") or e.raw_payload.get("ms_played") or 0) for e in events)
    return unique >= SPOTIFY_REMOTE_METADATA_ALWAYS_UNIQUE_TRACKS or (
        unique >= SPOTIFY_REMOTE_METADATA_MIN_UNIQUE_TRACKS and milliseconds >= SPOTIFY_REMOTE_METADATA_MIN_MS_PLAYED
    )


def _importable_album(metadata, total):
    if album_metadata_service.metadata_match_confidence(metadata) < album_metadata_service.IMPORT_MATCH_CONFIDENCE:
        return False
    primary_type = (metadata.get("primary_type") or "").strip().casefold()
    return primary_type == "album" if primary_type else total >= LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS
