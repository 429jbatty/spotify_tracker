"""Reconstruct Spotify album-session evidence for an import’s diagnostics."""

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models import ImportedListeningEvent, SpotifyStreamingEvent
from backend.app.repositories import import_event_repository as import_events
from backend.app.repositories import import_session_repository as import_sessions
from backend.app.repositories import spotify_import_repository as import_spotify
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import (
    SpotifyImportDiagnosticRawRow,
    SpotifyImportDiagnosticSession,
    SpotifyImportDiagnosticsResponse,
)
from backend.app.services.import_parsers import clean_text

from .common import SPOTIFY_IMPORT_SOURCE
from .metadata import read_album_metadata_cache
from .session_window import split_listening_sessions
from .track_matching import normalize_track_name


def spotify_import_diagnostics(
    session: Session,
    repository: SqliteStateRepository,
    import_session_id: int,
    *,
    artist: str,
    album: str,
) -> SpotifyImportDiagnosticsResponse:
    import_session = import_sessions.get_for_user(session, repository.user.id, import_session_id)
    if import_session is None:
        raise KeyError(f"Import session not found: {import_session_id}")
    if import_session.source != SPOTIFY_IMPORT_SOURCE:
        raise ValueError("Diagnostics are only available for Spotify ZIP imports.")

    target_artist = artist.strip().casefold()
    target_album = album.strip().casefold()
    raw_rows = import_spotify.diagnostic_rows(session, repository.user.id, import_session.id, target_artist, target_album)
    imported_rows = import_events.diagnostic_candidates(session, repository.user.id, import_session.id, target_artist, target_album)
    imported_by_raw_id: dict[int, list[ImportedListeningEvent]] = defaultdict(list)
    for imported in imported_rows:
        for raw_id in imported.raw_payload.get("_spotify_streaming_event_ids") or []:
            if raw_id is not None:
                imported_by_raw_id[int(raw_id)].append(imported)

    expected_tracks = _diagnostic_expected_tracks(session, repository, artist, album)
    sessions = _spotify_diagnostic_sessions(
        raw_rows,
        expected_tracks=expected_tracks,
        imported_by_raw_id=imported_by_raw_id,
    )
    timestamps = [row.played_at for row in raw_rows if row.played_at]
    return SpotifyImportDiagnosticsResponse(
        import_session_id=import_session.id,
        source=import_session.source,
        session_name=import_session.session_name,
        original_filename=import_session.original_filename,
        file_size_bytes=import_session.file_size_bytes,
        file_sha256=import_session.file_sha256,
        zip_member_count=import_session.zip_member_count,
        duplicate_of_import_session_id=import_session.duplicate_of_import_session_id,
        artist=artist,
        album=album,
        raw_row_count=len(raw_rows),
        timestamp_min=min(timestamps) if timestamps else None,
        timestamp_max=max(timestamps) if timestamps else None,
        expected_tracks=expected_tracks,
        sessions=sessions,
    )


def _spotify_diagnostic_sessions(
    rows: list[SpotifyStreamingEvent],
    *,
    expected_tracks: list[str],
    imported_by_raw_id: dict[int, list[ImportedListeningEvent]],
) -> list[SpotifyImportDiagnosticSession]:
    if not rows:
        return []

    grouped_rows = split_listening_sessions(rows, lambda row: row.played_at)

    expected_by_normalized = {
        normalize_track_name(track): track
        for track in expected_tracks
        if normalize_track_name(track)
    }
    sessions: list[SpotifyImportDiagnosticSession] = []
    for group in grouped_rows:
        seen_names = {
            normalize_track_name(row.track_name)
            for row in group
            if normalize_track_name(row.track_name)
        }
        matched_tracks = [
            title
            for normalized, title in expected_by_normalized.items()
            if normalized in seen_names
        ]
        missing_tracks = [
            title
            for normalized, title in expected_by_normalized.items()
            if normalized not in seen_names
        ]
        imported_events: dict[int, ImportedListeningEvent] = {}
        for row in group:
            for imported in imported_by_raw_id.get(row.id, []):
                imported_events[imported.id] = imported
        statuses = sorted(
            {
                imported.match_status
                for imported in imported_events.values()
                if imported.match_status
            }
        )
        sessions.append(
            SpotifyImportDiagnosticSession(
                start=group[0].played_at,
                end=group[-1].played_at,
                row_count=len(group),
                unique_track_count=len(seen_names),
                matched_tracks=matched_tracks or sorted(
                    {row.track_name for row in group if row.track_name}
                ),
                missing_tracks=missing_tracks,
                rows=[
                    SpotifyImportDiagnosticRawRow(
                        id=row.id,
                        played_at=row.played_at,
                        track_name=row.track_name,
                        spotify_track_uri=row.spotify_track_uri,
                        source_file=row.source_file,
                        source_index=row.source_index,
                    )
                    for row in group
                ],
                imported_event_ids=sorted(imported_events),
                final_statuses=statuses,
                listen_created=any(
                    imported.album_id is not None
                    or imported.match_status == "processed_album_listen"
                    for imported in imported_events.values()
                ),
            )
        )
    return sessions


def _diagnostic_expected_tracks(
    session: Session,
    repository: SqliteStateRepository,
    artist: str,
    album: str,
) -> list[str]:
    album_metadata = repository.get_library_album_metadata(artist, album)
    if album_metadata is not None:
        tracks = _track_titles_from_metadata(album_metadata)
        if tracks:
            return tracks

    cached = read_album_metadata_cache(session, artist, album)
    if isinstance(cached, dict):
        return _track_titles_from_metadata(cached)
    return []


def _track_titles_from_metadata(metadata: dict[str, Any] | None) -> list[str]:
    return [
        title
        for title in (
            clean_text(track.get("title"))
            for track in (metadata or {}).get("tracklist") or []
            if isinstance(track, dict)
        )
        if title
    ]
