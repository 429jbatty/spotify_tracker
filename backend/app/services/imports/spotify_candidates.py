"""Build Spotify album-session candidates from raw plays or persisted candidate rows."""

import hashlib
import time
from collections import defaultdict
from itertools import groupby
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models import ImportSession, ImportedListeningEvent, SpotifyStreamingEvent
from backend.app.repositories import import_event_repository as import_events
from backend.app.repositories import spotify_import_repository as import_spotify
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services.import_parsers import NormalizedImportEvent

from .common import SPOTIFY_IMPORT_SOURCE
from .matching import AlbumCandidate, match_album_session
from .metadata import album_match_key, load_existing_albums
from .progress import ImportMetadataStats, append_import_log
from .session_window import split_listening_sessions
from .spotify_completion import spotify_completion_result


SPOTIFY_CANDIDATE_PROGRESS_INTERVAL = 500
SPOTIFY_CANDIDATE_PROGRESS_SECONDS = 2.0


def build_spotify_candidates_from_plays(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    *,
    allow_remote_metadata: bool,
    metadata_stats: ImportMetadataStats | None = None,
    progress_callback: Any | None = None,
) -> list[AlbumCandidate]:
    metadata_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    existing_album_index = load_existing_albums(repository)
    candidates: list[AlbumCandidate] = []
    rows = import_spotify.candidate_source_rows(session, repository.user.id, import_session.id)
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            _spotify_streaming_event_group_key(row),
            row.played_at,
            row.id,
        ),
    )
    event_chunks: list[list[NormalizedImportEvent]] = []
    for _, group in groupby(sorted_rows, key=_spotify_streaming_event_group_key):
        events = (_spotify_streaming_event_to_import_event(row) for row in group)
        event_chunks.extend(split_listening_sessions(events, lambda event: event.listened_at))

    total_candidates = len(event_chunks)
    last_progress_at = 0.0
    partial_short_circuits = 0
    for index, chunk in enumerate(event_chunks, start=1):
        candidate = match_album_session(
            session=session,
            events=chunk,
            source_user_id=None,
            metadata_cache=metadata_cache,
            existing_album_index=existing_album_index,
            load_metadata=True,
            allow_remote_metadata=allow_remote_metadata,
            metadata_stats=metadata_stats,
        )
        if candidate.status == "partial_listen" and spotify_completion_result(chunk) is not None:
            partial_short_circuits += 1
        candidates.append(candidate)
        now = time.perf_counter()
        if progress_callback and (
            index == 1
            or index == total_candidates
            or index % SPOTIFY_CANDIDATE_PROGRESS_INTERVAL == 0
            or now - last_progress_at >= SPOTIFY_CANDIDATE_PROGRESS_SECONDS
        ):
            progress_callback(index, total_candidates, candidates)
            last_progress_at = now

    candidates.sort(key=lambda candidate: candidate.listened_at, reverse=True)
    append_import_log(
        session,
        import_session,
        stage="matching_cached_albums",
        message="Built Spotify album-session candidates.",
        current=total_candidates,
        total=total_candidates,
        metadata={
            "partial_short_circuits": partial_short_circuits,
            "actionable_candidates": sum(
                1 for candidate in candidates if candidate.status != "partial_listen"
            ),
        },
    )
    _persist_spotify_candidate_rows(
        session=session,
        repository=repository,
        import_session=import_session,
        candidates=candidates,
    )
    return candidates


def rebuild_spotify_candidates_from_rows(
    session: Session,
    repository: SqliteStateRepository,
    imported_rows: list[ImportedListeningEvent],
    *,
    allow_remote_metadata: bool,
    metadata_stats: ImportMetadataStats | None = None,
    progress_callback: Any | None = None,
) -> list[AlbumCandidate]:
    metadata_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    existing_album_index = load_existing_albums(repository)
    candidates: list[AlbumCandidate] = []
    grouped_rows: dict[tuple[str, str], list[ImportedListeningEvent]] = defaultdict(list)
    for row in imported_rows:
        grouped_rows[album_match_key(row.artist, row.album)].append(row)

    total = len(grouped_rows)
    for index, rows_for_album in enumerate(grouped_rows.values(), start=1):
        for row in rows_for_album:
            streaming_event_ids = row.raw_payload.get("_spotify_streaming_event_ids") or []
            streaming_events = import_spotify.events_by_id(session, repository.user.id, streaming_event_ids)
            events = [
                _spotify_streaming_event_to_import_event(streaming_event)
                for streaming_event in streaming_events
            ]
            if not events:
                continue
            candidate = match_album_session(
                session=session,
                events=events,
                source_user_id=None,
                metadata_cache=metadata_cache,
                existing_album_index=existing_album_index,
                load_metadata=True,
                allow_remote_metadata=allow_remote_metadata,
                metadata_stats=metadata_stats,
            )
            candidate.candidate_key = row.candidate_key or candidate.candidate_key
            candidates.append(candidate)
        if progress_callback and (index == 1 or index % 5 == 0 or index == total):
            progress_callback(index, total, candidates)

    candidates.sort(key=lambda candidate: candidate.listened_at, reverse=True)
    return candidates


def _spotify_streaming_event_group_key(row: SpotifyStreamingEvent) -> tuple[str, str, str]:
    if row.spotify_album_id and row.spotify_album_total_tracks:
        return ("spotify_album", row.spotify_album_id.casefold(), "")
    return (
        "name",
        (row.artist_name or "").casefold(),
        (row.album_name or "").casefold(),
    )


def _persist_spotify_candidate_rows(
    session: Session,
    repository: SqliteStateRepository,
    import_session: ImportSession,
    candidates: list[AlbumCandidate],
) -> None:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.status == "partial_listen":
            continue
        representative = candidate.events[-1]
        streaming_event_ids = [
            event.raw_payload.get("_spotify_streaming_event_id")
            for event in candidate.events
            if event.raw_payload.get("_spotify_streaming_event_id") is not None
        ]
        rows.append(
            {
                "user_id": repository.user.id,
                "import_session_id": import_session.id,
                "album_id": None,
                "source": SPOTIFY_IMPORT_SOURCE,
                "source_user_id": None,
                "source_event_id": candidate.candidate_key,
                "event_fingerprint": _spotify_candidate_fingerprint(candidate),
                "candidate_key": candidate.candidate_key,
                "listened_at": candidate.listened_at,
                "artist": candidate.artist,
                "album": candidate.album,
                "track": f"{candidate.unique_scrobbled_tracks} unique Spotify tracks",
                "source_label": SPOTIFY_IMPORT_SOURCE,
                "rating": None,
                "notes": None,
                "match_status": "raw_imported",
                "match_confidence": None,
                "error_message": None,
                "raw_payload": {
                    "_spotify_streaming_event_ids": streaming_event_ids,
                    "_representative_track": representative.track,
                    "_track_count": len(streaming_event_ids),
                    "_spotify_album_id": representative.raw_payload.get("_spotify_album_id"),
                    "_spotify_album_total_tracks": representative.raw_payload.get(
                        "_spotify_album_total_tracks"
                    ),
                    "_spotify_album_type": representative.raw_payload.get("_spotify_album_type"),
                    "_spotify_completion_authority": (
                        "spotify_catalog"
                        if representative.raw_payload.get("_spotify_album_total_tracks")
                        else "metadata_tracklist"
                    ),
                },
            }
        )
    if not rows:
        return

    import_events.insert_spotify_candidates(session, rows)
    append_import_log(
        session,
        import_session,
        stage="matching_cached_albums",
        message="Persisted actionable Spotify album-session candidates.",
        current=len(rows),
        total=len(rows),
    )


def _spotify_streaming_event_to_import_event(
    row: SpotifyStreamingEvent,
) -> NormalizedImportEvent:
    return NormalizedImportEvent(
        listened_at=row.played_at,
        artist=row.spotify_album_artist_name or row.artist_name,
        album=row.spotify_album_name or row.album_name,
        track=row.track_name,
        source=SPOTIFY_IMPORT_SOURCE,
        source_user_id=None,
        source_event_id=str(row.id),
        source_label=SPOTIFY_IMPORT_SOURCE,
        rating=None,
        notes=None,
        raw_payload={
            **(row.raw_payload or {}),
            "_spotify_streaming_event_id": row.id,
            "_spotify_source_file": row.source_file,
            "_spotify_source_index": row.source_index,
            "_spotify_track_uri": row.spotify_track_uri,
            "_spotify_track_id": row.spotify_track_id,
            "_spotify_album_id": row.spotify_album_id,
            "_spotify_album_name": row.spotify_album_name,
            "_spotify_album_artist_name": row.spotify_album_artist_name,
            "_spotify_album_total_tracks": row.spotify_album_total_tracks,
            "_spotify_album_type": row.spotify_album_type,
            "_spotify_disc_number": row.spotify_disc_number,
            "_spotify_track_number": row.spotify_track_number,
            "_spotify_catalog_status": row.spotify_catalog_status,
            "_spotify_track_name": row.track_name,
            "_spotify_ms_played": row.ms_played,
        },
    )


def _spotify_candidate_fingerprint(candidate: AlbumCandidate) -> str:
    return hashlib.sha256(
        "|".join(
            [
                SPOTIFY_IMPORT_SOURCE,
                candidate.candidate_key,
            ]
        ).encode("utf-8")
    ).hexdigest()
