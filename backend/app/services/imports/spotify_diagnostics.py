"""Reconstruct Spotify album-session evidence for an import’s diagnostics."""

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.app.database.models import ImportedListeningEvent
from backend.app.database.repositories import (
    import_event_repository as import_events,
    import_session_repository as import_sessions,
    spotify_import_repository as import_spotify,
)
from backend.app.database.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.schemas import (
    SpotifyImportDiagnosticRawRow,
    SpotifyImportDiagnosticSession,
    SpotifyImportDiagnosticsResponse,
)
from backend.app.services.import_parsers import clean_text

from .events import SPOTIFY_IMPORT_SOURCE, split_listening_sessions
from .metadata import read_album_metadata_cache
from .progress import archive_fields
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
    expected = {normalize_track_name(track): track for track in expected_tracks if normalize_track_name(track)}
    sessions = [_diagnostic_session(group, expected, imported_by_raw_id)
                for group in split_listening_sessions(raw_rows, lambda row: row.played_at)]
    timestamps = [row.played_at for row in raw_rows if row.played_at]
    return SpotifyImportDiagnosticsResponse(
        import_session_id=import_session.id,
        source=import_session.source,
        session_name=import_session.session_name,
        **archive_fields(import_session),
        artist=artist,
        album=album,
        raw_row_count=len(raw_rows),
        timestamp_min=min(timestamps) if timestamps else None,
        timestamp_max=max(timestamps) if timestamps else None,
        expected_tracks=expected_tracks,
        sessions=sessions,
    )


def _diagnostic_session(group, expected, imported_by_raw_id):
    seen = {normalize_track_name(row.track_name) for row in group} - {""}
    imported = {item.id: item for row in group for item in imported_by_raw_id.get(row.id, [])}
    matched = [title for name, title in expected.items() if name in seen]
    return SpotifyImportDiagnosticSession(
        start=group[0].played_at, end=group[-1].played_at, row_count=len(group), unique_track_count=len(seen),
        matched_tracks=matched or sorted({row.track_name for row in group if row.track_name}),
        missing_tracks=[title for name, title in expected.items() if name not in seen],
        rows=[SpotifyImportDiagnosticRawRow.model_validate(row, from_attributes=True) for row in group],
        imported_event_ids=sorted(imported),
        final_statuses=sorted({item.match_status for item in imported.values() if item.match_status}),
        listen_created=any(item.album_id is not None or item.match_status == "processed_album_listen"
                           for item in imported.values()),
    )


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
