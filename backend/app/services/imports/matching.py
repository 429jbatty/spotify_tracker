"""Decide whether a session of plays qualifies as an album listen."""

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

import album_metadata_service
from backend.app.album_completion import ALBUM_COMPLETION_THRESHOLD
from backend.app.services.import_parsers import NormalizedImportEvent

from .common import SPOTIFY_IMPORT_SOURCE
from .metadata import ExistingAlbumMatch, album_match_key, resolve_album_metadata
from .progress import ImportMetadataStats
from .spotify_completion import spotify_completion_result
from .track_matching import (
    matched_import_track_count,
    normalize_track_name,
    partially_matched_spotify_split_tracks,
    track_identity,
)


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
    matched_album_id: int | None
    matched_track_count: int
    total_track_count: int
    unique_scrobbled_tracks: int
    status: str
    status_detail: str
    confidence: int
    metadata: dict[str, Any] | None = None


def match_album_session(
    session: Session,
    events: list[NormalizedImportEvent],
    source_user_id: str | None,
    metadata_cache: dict[tuple[str, str], dict[str, Any] | None],
    existing_album_index: dict[tuple[str, str], ExistingAlbumMatch],
    *,
    load_metadata: bool = True,
    allow_remote_metadata: bool = True,
    metadata_stats: ImportMetadataStats | None = None,
) -> AlbumCandidate:
    artist = events[0].artist or "Unknown Artist"
    album = events[0].album or "Unknown Album"
    listened_at = max(event.listened_at for event in events if event.listened_at)
    unique_track_names = {
        normalize_track_name(event.track)
        for event in events
        if normalize_track_name(event.track)
    }
    unique_track_identities = {
        track_identity(event)
        for event in events
        if track_identity(event)
    }
    spotify_completion = spotify_completion_result(events)
    exclusion_reason = spotify_completion.exclusion_reason if spotify_completion else None
    if exclusion_reason:
        return AlbumCandidate(
            candidate_key=_import_candidate_key(
                events[0].source,
                source_user_id,
                artist,
                album,
                events,
            ),
            artist=artist,
            album=album,
            listened_at=listened_at,
            events=events,
            matched_album_id=None,
            matched_track_count=spotify_completion.matched_track_count,
            total_track_count=spotify_completion.total_tracks,
            unique_scrobbled_tracks=len(unique_track_identities),
            status="partial_listen",
            status_detail=exclusion_reason,
            confidence=spotify_completion.confidence,
            metadata=None,
        )

    matched_album = existing_album_index.get(album_match_key(artist, album))
    matched_album_id = matched_album.album_id if matched_album else None
    remote_metadata_allowed = allow_remote_metadata and (
        spotify_completion is not None or _candidate_has_remote_metadata_evidence(events, unique_track_identities)
    )
    metadata = (
        resolve_album_metadata(
            session,
            artist,
            album,
            metadata_cache,
            matched_album_id=matched_album_id,
            matched_album_record=matched_album.record if matched_album else None,
            allow_remote_metadata=remote_metadata_allowed,
            entry_source=events[0].source,
            metadata_stats=metadata_stats,
        )
        if load_metadata
        else None
    )

    matched_track_count = 0
    total_track_count = 0
    confidence = 25
    status = "partial_listen"
    if not load_metadata:
        matched_track_count = len(unique_track_identities)
        confidence = min(80, max(25, matched_track_count * 10))
        status = "preview_candidate"
        detail = (
            f"Fast preview candidate with {matched_track_count} unique scrobbled tracks. "
            "Commit import to store scrobbles and run full album-completion matching."
        )
    elif metadata and metadata.get("tracklist"):
        metadata_track_titles = [
            track.get("title")
            for track in metadata.get("tracklist") or []
            if normalize_track_name(track.get("title"))
        ]
        if spotify_completion is not None:
            matched_track_count = spotify_completion.matched_track_count
            total_track_count = spotify_completion.total_tracks
            confidence = spotify_completion.confidence
            complete = spotify_completion.complete
        else:
            total_track_count = len({normalize_track_name(title) for title in metadata_track_titles})
            matched_track_count = matched_import_track_count(metadata_track_titles, unique_track_names)
            complete = total_track_count > 0 and matched_track_count / total_track_count >= ALBUM_COMPLETION_THRESHOLD
            if total_track_count > 0:
                confidence = round((matched_track_count / total_track_count) * 100)
        partially_matched_split_tracks = (
            partially_matched_spotify_split_tracks(
                metadata_track_titles,
                unique_track_names,
            )
            if events and events[0].source == SPOTIFY_IMPORT_SOURCE
            else []
        )
        if matched_album_id is None and not _is_importable_album_metadata(
            metadata,
            total_track_count,
        ):
            status = "partial_listen"
            detail = (
                "MusicBrainz matched this to a single or short non-album release, "
                "so it does not count as a completed album listen."
            )
        elif partially_matched_split_tracks:
            status = "partial_listen"
            detail = (
                "Spotify matched only part of a combined MusicBrainz track "
                f"({', '.join(partially_matched_split_tracks)}), so this does not "
                "count as a completed album listen."
            )
        elif complete:
            status = "matched_existing" if matched_album_id is not None else "new_album"
            if spotify_completion is not None:
                detail = f"Spotify matched {matched_track_count} of {total_track_count} album tracks. "
            else:
                detail = f"Matched {matched_track_count} of {total_track_count} tracks. "
            detail += "This will count as a completed album listen."
        else:
            status = "partial_listen"
            detail = (
                f"Matched {matched_track_count} of {total_track_count or len(unique_track_names)} tracks. "
                "This does not count as a completed album listen."
            )
    elif spotify_completion is not None:
        matched_track_count = spotify_completion.matched_track_count
        total_track_count = spotify_completion.total_tracks
        confidence = spotify_completion.confidence
        if not allow_remote_metadata:
            status = "pending_metadata"
            detail = (
                f"Spotify matched {matched_track_count} of {total_track_count} album tracks. "
                "MusicBrainz metadata is still needed before creating the album listen."
            )
        else:
            status = "candidate_review"
            detail = (
                "Spotify indicates this is a completed album listen, but MusicBrainz "
                "metadata could not be loaded automatically."
            )
    elif not _candidate_has_remote_metadata_evidence(events, unique_track_identities):
        status = "partial_listen"
        detail = (
            f"Only {len(unique_track_identities)} unique tracks were available; skipped remote metadata "
            "lookup because this is not enough evidence for a full album listen."
        )
    elif not allow_remote_metadata:
        status = "no_tracklist"
        detail = (
            "No local or cached tracklist is available yet, so this scrobble session "
            "does not count as a completed album listen."
        )
    else:
        status = "candidate_review"
        detail = "Could not load album tracklist, so this scrobble session needs review."

    candidate_key = _import_candidate_key(events[0].source, source_user_id, artist, album, events)
    return AlbumCandidate(
        candidate_key=candidate_key,
        artist=artist,
        album=album,
        listened_at=listened_at,
        events=events,
        matched_album_id=matched_album_id,
        matched_track_count=matched_track_count,
        total_track_count=total_track_count,
        unique_scrobbled_tracks=len(unique_track_identities),
        status=status,
        status_detail=detail,
        confidence=confidence,
        metadata=metadata,
    )


def _candidate_has_remote_metadata_evidence(
    events: list[NormalizedImportEvent],
    unique_track_identities: set[str],
) -> bool:
    if events and events[0].source == SPOTIFY_IMPORT_SOURCE:
        total_ms_played = sum(
            int(event.raw_payload.get("_spotify_ms_played") or event.raw_payload.get("ms_played") or 0)
            for event in events
        )
        unique_tracks = len(unique_track_identities)
        return unique_tracks >= SPOTIFY_REMOTE_METADATA_ALWAYS_UNIQUE_TRACKS or (
            unique_tracks >= SPOTIFY_REMOTE_METADATA_MIN_UNIQUE_TRACKS
            and total_ms_played >= SPOTIFY_REMOTE_METADATA_MIN_MS_PLAYED
        )
    return len(unique_track_identities) >= LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS


def _is_importable_album_metadata(
    metadata: dict[str, Any],
    total_track_count: int,
) -> bool:
    confidence = album_metadata_service.metadata_match_confidence(metadata)
    if confidence < album_metadata_service.IMPORT_MATCH_CONFIDENCE:
        return False

    primary_type = (metadata.get("primary_type") or "").strip().casefold()
    if primary_type:
        return primary_type == "album"

    return total_track_count >= LASTFM_REMOTE_METADATA_MIN_UNIQUE_TRACKS


def _import_candidate_key(
    source: str,
    source_user_id: str | None,
    artist: str,
    album: str,
    events: list[NormalizedImportEvent],
) -> str:
    payload = "|".join(
        [
            source,
            source_user_id or "",
            artist.casefold(),
            album.casefold(),
            events[0].listened_at or "",
            events[-1].listened_at or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
