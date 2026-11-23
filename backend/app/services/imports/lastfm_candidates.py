"""Group Last.fm scrobbles and link each persisted row to its candidate."""

import hashlib
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models import ImportedListeningEvent
from backend.app.repositories.sqlite_state_repository import SqliteStateRepository
from backend.app.services.import_parsers import NormalizedImportEvent

from .common import parse_timestamp
from .matching import AlbumCandidate, match_album_session
from .metadata import load_existing_albums
from .progress import ImportMetadataStats
from .session_window import split_listening_sessions


def build_lastfm_candidates_from_rows(
    session: Session,
    repository: SqliteStateRepository,
    imported_rows: list[ImportedListeningEvent],
    *,
    allow_remote_metadata: bool = True,
    metadata_stats: ImportMetadataStats | None = None,
    progress_callback: Any | None = None,
) -> list[AlbumCandidate]:
    events = [
        NormalizedImportEvent(
            listened_at=row.listened_at,
            artist=row.artist,
            album=row.album,
            track=row.track,
            source=row.source,
            source_user_id=row.source_user_id,
            source_event_id=row.source_event_id,
            source_label=row.source_label,
            rating=row.rating,
            notes=row.notes,
            raw_payload=row.raw_payload or {},
        )
        for row in imported_rows
    ]
    candidates = build_lastfm_candidates(
        session=session,
        repository=repository,
        rows=events,
        source_user_id=imported_rows[0].source_user_id if imported_rows else None,
        load_metadata=True,
        allow_remote_metadata=allow_remote_metadata,
        metadata_stats=metadata_stats,
        progress_callback=progress_callback,
    )
    imported_lookup = {
        scrobble_fingerprint(event): row
        for event, row in zip(events, imported_rows)
    }
    for candidate in candidates:
        for event in candidate.events:
            imported_row = imported_lookup.get(scrobble_fingerprint(event))
            if imported_row is not None:
                imported_row.candidate_key = candidate.candidate_key
    return candidates


def build_lastfm_candidates(
    session: Session,
    repository: SqliteStateRepository,
    rows: list[NormalizedImportEvent],
    source_user_id: str | None,
    *,
    load_metadata: bool = True,
    allow_remote_metadata: bool = True,
    metadata_stats: ImportMetadataStats | None = None,
    progress_callback: Any | None = None,
) -> list[AlbumCandidate]:
    grouped: dict[tuple[str, str], list[NormalizedImportEvent]] = defaultdict(list)
    for row in rows:
        if not row.artist or not row.album or not row.listened_at:
            continue
        grouped[(row.artist.casefold(), row.album.casefold())].append(row)

    metadata_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    existing_album_index = load_existing_albums(repository)
    candidate_event_chunks: list[list[NormalizedImportEvent]] = []
    for event_group in grouped.values():
        event_group.sort(key=lambda row: parse_timestamp(row.listened_at))
        candidate_event_chunks.extend(split_listening_sessions(event_group, lambda event: event.listened_at))

    candidates: list[AlbumCandidate] = []
    total_candidates = len(candidate_event_chunks)
    for index, chunk in enumerate(candidate_event_chunks, start=1):
        candidate = match_album_session(
            session=session,
            events=chunk,
            source_user_id=source_user_id,
            metadata_cache=metadata_cache,
            existing_album_index=existing_album_index,
            load_metadata=load_metadata,
            allow_remote_metadata=allow_remote_metadata,
            metadata_stats=metadata_stats,
        )
        candidates.append(candidate)
        if progress_callback and (index == 1 or index % 5 == 0 or index == total_candidates):
            progress_callback(index, total_candidates, candidates)
    candidates.sort(key=lambda candidate: candidate.listened_at, reverse=True)
    return candidates


def scrobble_fingerprint(event: NormalizedImportEvent) -> str:
    payload = "|".join(
        [
            event.listened_at or "",
            (event.artist or "").casefold(),
            (event.album or "").casefold(),
            (event.track or "").casefold(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
